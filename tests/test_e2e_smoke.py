"""Сквозные smoke-сценарии (фаза 1.0): квиз → план → ссылка.

Проверяем путь пользователя целиком, но на уровне HTTP и контрактов
сериализации — без браузера. Playwright сюда не тянем сознательно:
он требует npm и браузерные бинарники, а проект держится принципа
«фронт без сборки, тесты без сети» (docs/architecture.md).

Граница проверки: всё, что делает сервер, плюс формат ссылки, который
фронт кладёт в адрес (`static/plan-link.js`, свой свит в `tests/js/`).
Тем самым ломающее изменение в любом звене — порядок полей ссылки,
контракт `QuizIn`, планировщик — валит именно этот файл.
"""
import json
import re
import shutil
import subprocess
import urllib.parse

import pytest

from app.config import APP_VERSION, STATIC_DIR

# Порядок полей ссылки живёт в static/plan-link.js — дублировать его
# в тестах нельзя, иначе свит разъедется с фронтом. Читаем из модуля.
PLAN_ORDER_RE = re.compile(r"const ORDER = \[([^\]]+)\]")


def plan_order() -> list[str]:
    src = (STATIC_DIR / "plan-link.js").read_text(encoding="utf-8")
    raw = PLAN_ORDER_RE.search(src).group(1)
    return [p.strip().strip('"') for p in raw.split(",") if p.strip()]


def build_plan_string(answers: dict) -> str:
    """Python-двойник buildPlanString из plan-link.js."""
    return "~".join(
        ",".join(answers["purpose"]) if k == "purpose" else answers[k]
        for k in plan_order()
    )


def parse_plan_param(value: str) -> dict | None:
    """Python-двойник parsePlanParam: то, что фронт достаёт из ссылки."""
    order = plan_order()
    parts = value.split("~")
    if len(parts) != len(order):
        return None
    purpose = [p for p in parts[0].split(",") if p]
    if not purpose:
        return None
    out: dict = {"purpose": purpose}
    out.update(dict(zip(order[1:], parts[1:], strict=True)))
    return out


# Три сценария из чек-листа бета-тестирования в README.
SCENARIOS = {
    "пляж/пара/лето": {
        "purpose": ["beach", "romance"], "season": "summer", "tempo": "relax",
        "budget": "comfort", "party": "couple", "duration": "3-5",
        "transport": "car",
    },
    "вино/осень/без машины": {
        "purpose": ["wine", "food"], "season": "autumn", "tempo": "medium",
        "budget": "comfort", "party": "friends", "duration": "1-2",
        "transport": "transit",
    },
    "с детьми/экономия": {
        "purpose": ["family", "free"], "season": "summer", "tempo": "medium",
        "budget": "economy", "party": "family", "duration": "6-10",
        "transport": "car",
    },
}


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_quiz_to_plan_to_link_roundtrip(client, name):
    """Полный путь: прошли квиз → получили план → поделились ссылкой →
    получатель открыл её и увидел тот же план."""
    answers = SCENARIOS[name]

    # 1. Квиз отдаёт контент, и наши ответы — валидные опции.
    quiz = client.get("/api/quiz").json()
    options = {q["id"]: {o["id"] for o in q["options"]} for q in quiz["questions"]}
    for field, value in answers.items():
        allowed = options[field]
        chosen = value if isinstance(value, list) else [value]
        assert set(chosen) <= allowed, f"{name}: {field}={value}"

    # 2. Оценка: профиль, рекомендации и план по дням.
    first = client.post("/api/quiz/evaluate", json=answers)
    assert first.status_code == 200, first.text
    result = first.json()
    assert result["profile"]["title"], name
    assert result["recommendations"], f"{name}: пустая подборка"
    days = result["itinerary"]["days"]
    assert days, f"{name}: план не собрался"

    # 3. Ссылка: сериализация → URL → разбор у получателя.
    shared = urllib.parse.quote(build_plan_string(answers))
    restored = parse_plan_param(urllib.parse.unquote(shared))
    assert restored == answers, f"{name}: ссылка потеряла ответы"

    # 4. Получатель отправляет разобранные ответы — результат тот же.
    second = client.post("/api/quiz/evaluate", json=restored)
    assert second.status_code == 200
    again = second.json()
    assert [a["id"] for a in again["recommendations"]] == \
           [a["id"] for a in result["recommendations"]], f"{name}: выдача поехала"


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_plan_days_are_actually_walkable(client, name):
    """План должен быть выполнимым: не больше трёх остановок в день,
    один район на день и вменяемая загрузка по часам."""
    result = client.post("/api/quiz/evaluate", json=SCENARIOS[name]).json()
    for day in result["itinerary"]["days"]:
        stops = day["stops"]
        assert 1 <= len(stops) <= 3, \
            f"{name}, день {day['day']}: {len(stops)} остановок"
        assert len({s["area"] for s in stops}) == 1, "день скачет между районами"
        assert day["area_label"], name
        hours = sum(s["duration_h"] for s in stops)
        assert hours <= 12, f"{name}, день {day['day']}: {hours} ч"
        slots = [s["slot"] for s in stops]
        assert all(s in ("morning", "afternoon", "evening", "full") for s in slots)
        if "full" in slots:
            assert len(stops) == 1, "«целый день» не делят с другими точками"


def test_shared_plan_link_survives_the_browser(client):
    """Ссылка переживает адресную строку: кириллица и спецсимволы
    в ответах не ломают round-trip (их нет, но кодирование проверим)."""
    answers = SCENARIOS["пляж/пара/лето"]
    url = f"/#/quiz?plan={urllib.parse.quote(build_plan_string(answers))}"
    param = urllib.parse.parse_qs(url.split("?", 1)[1])["plan"][0]
    assert parse_plan_param(param) == answers


def test_broken_share_link_degrades_to_422_not_500(client):
    """Битую ссылку сервер отвергает контрактом, а не падает."""
    for junk in ("", "beach~summer", "~".join(["мусор"] * 7)):
        parsed = parse_plan_param(junk)
        if parsed is None:
            continue                      # фронт даже не отправит такое
        r = client.post("/api/quiz/evaluate", json=parsed)
        assert r.status_code == 422, junk


def test_place_deep_link_opens_a_real_card(client):
    """Второй сценарий шаринга: «🔗 Поделиться» из карточки места.
    Ссылка #/place/<id> обслуживается тем же SPA, данные — из API."""
    catalog = client.get("/api/attractions").json()["items"]
    for place in (catalog[0], catalog[-1]):
        r = client.get(f"/api/attractions/{place['id']}")
        assert r.status_code == 200
        body = r.json()
        assert body["name"] == place["name"]
        assert body["type_meta"]["img"]
        assert (STATIC_DIR / "img" / body["type_meta"]["img"]).exists()
    # Сам SPA-каркас отдаётся на любой хеш-маршрут — хеш на сервер не уходит.
    assert client.get("/").status_code == 200


def test_catalog_filter_link_reproduces_the_selection(client):
    """Третий сценарий: «🔗 Ссылка на подборку» — фильтры каталога в URL
    должны давать у получателя ту же выборку, что у отправителя."""
    filters = {"tag": "beach", "area": "Западный", "q": "пляж"}
    query = urllib.parse.urlencode(filters)
    body = client.get(f"/api/attractions?{query}").json()
    assert body["count"] >= 1
    for a in body["items"]:
        assert "beach" in a["tags"]
        assert a["area"] == "Западный"
        assert "пляж" in (a["name"] + a["description"]).lower()


def test_offline_shell_has_everything_the_scenarios_need(client):
    """Смоук PWA: всё, что нужно сценариям выше, лежит в precache SW."""
    sw = (STATIC_DIR / "sw.js").read_text(encoding="utf-8")
    shell = set(re.findall(r'"(/[^"]*)"', sw))
    assert {"/", "/static/app.js", "/static/plan-link.js",
            "/static/catalog-link.js", "/static/style.css"} <= shell
    for path in ("/static/app.js", "/static/plan-link.js",
                 "/static/catalog-link.js", "/static/style.css"):
        assert client.get(path).status_code == 200, path
    assert client.get("/sw.js").headers["Service-Worker-Allowed"] == "/"


def test_health_and_version_are_the_release_contract(client):
    """То, что мониторит healthcheck compose-стека."""
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["name"] == "Крым.Гид"
    assert body["version"] == APP_VERSION
    assert re.fullmatch(r"\d+\.\d+\.\d+", body["version"]), body["version"]


@pytest.mark.skipif(shutil.which("node") is None, reason="нужен Node.js")
def test_python_twin_matches_the_real_frontend_module():
    """Страховка от расхождения: двойники выше обязаны давать тот же
    результат, что настоящий static/plan-link.js в Node."""
    answers = SCENARIOS["вино/осень/без машины"]
    script = (
        f'const P = require({str(STATIC_DIR / "plan-link.js")!r});'
        f'const a = {json.dumps(answers)};'
        'const s = P.buildPlanString(a);'
        'process.stdout.write(JSON.stringify([s, P.parsePlanParam(s)]));'
    )
    out = subprocess.run(  # noqa: S603
        [shutil.which("node"), "-e", script],
        capture_output=True, text=True, check=True,
    ).stdout
    js_string, js_parsed = json.loads(out)
    assert js_string == build_plan_string(answers)
    assert js_parsed == parse_plan_param(js_string) == answers
