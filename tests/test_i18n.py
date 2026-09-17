"""Контракт английской локали (фаза 1.8.0).

Смотрит то, что глазами не проверить: словарь обязан покрывать интерфейс,
не иметь мёртвых ключей, переводить каждый объект каталога и быть
собранным из `tools/i18n_en/` ровно так, как лежит в репозитории. Сеть не
нужна: бандл — статика, `tools/i18n_extract.py` читает файлы.
"""

import json
import re
import subprocess
import sys

import pytest

from app.config import BASE_DIR, STATIC_DIR

ROOT = BASE_DIR.parent  # app/config.py: BASE_DIR — это app/
BUNDLE_PATH = STATIC_DIR / "i18n" / "en.json"
# Поля места, которые переводятся: тот же список, что и во фронте
# (`PLACE_FIELDS` в app.js) — сверяем его отдельно, ниже.
PLACE_FIELDS = ["name", "region", "description", "tips", "price_hint", "hours"]
BUNDLE_LIMIT = 140_000  # байт: EN-пакет качает только англичанин, но и ему не за что


@pytest.fixture(scope="module")
def bundle():
    assert BUNDLE_PATH.exists(), f"нет бандла: {BUNDLE_PATH}"
    return json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def report():
    sys.path.insert(0, str(ROOT / "tools"))
    import i18n_extract  # noqa: PLC0415

    return i18n_extract.collect()


def load_attractions():
    data = json.loads((ROOT / "app" / "data" / "attractions.json").read_text("utf-8"))
    return data


# ---------------- структура бандла ----------------


def test_bundle_shape(bundle):
    assert bundle["lang"] == "en"
    assert bundle["name"] == "English"
    for section in ("ui", "labels", "places"):
        assert isinstance(bundle[section], dict), section
        assert bundle[section], f"секция {section} пуста"
    for section in ("ui", "labels"):
        for key, value in bundle[section].items():
            assert key.strip() == key, f"ключ с крапками пробелов: {key!r}"
            assert isinstance(value, str) and value.strip(), f"пустой перевод: {key!r}"
    # Секции `ui` и `labels` не должны пересекаться: `ui` главнее, и дубль
    # означал бы, что кто-то не разобрался, где живёт строка.
    overlap = set(bundle["ui"]) & set(bundle["labels"])
    assert not overlap, f"ключ в двух секциях сразу: {sorted(overlap)[:5]}"


def test_bundle_is_json_of_reasonable_size():
    size = BUNDLE_PATH.stat().st_size
    assert size < BUNDLE_LIMIT, f"бандл раздут: {size} байт"


def test_bundle_is_served_from_static(client):
    """Отдаёт его уже `StaticFiles` — отдельного роута локализации нет."""
    response = client.get("/static/i18n/en.json")
    assert response.status_code == 200
    body = response.json()
    assert body["lang"] == "en"
    assert "ui" in body and "places" in body


def test_english_text_has_no_cyrillic(bundle):
    """Кроме товарного знака: «Крым.Гид» остаётся собой в любой речи."""
    brand = "Крым.Гид"
    bad = []
    for section in ("ui", "labels"):
        for key, value in bundle[section].items():
            if re.search(r"[а-яё]", value) and brand not in value:
                bad.append((section, key, value))
    for pid, record in bundle["places"].items():
        for field, value in record.items():
            if re.search(r"[а-яё]", value):
                bad.append((pid, field, value))
    assert not bad, f"кириллица в английском тексте: {bad[:5]}"


def test_number_fold_is_shared_with_the_tool():
    """`I18n.fold` и `fold_key` из инструмента — одна регулярка.

    Разъедутся — и ключи, которые сборщик записал свёрнутыми, на живом
    экране перестанут находиться: молча, без единой ошибки в консоли.
    """
    js = (STATIC_DIR / "i18n.js").read_text(encoding="utf-8")
    py = (ROOT / "tools" / "i18n_extract.py").read_text(encoding="utf-8")
    js_re = re.search(r"const NUMBER_RE = /(.+?)/g;", js)
    py_re = re.search(r'NUMBER_RE = re\.compile\(r"(.+?)"\)', py)
    assert js_re and py_re, "NUMBER_RE пропал из одного из файлов"
    assert js_re.group(1) == py_re.group(1), f"{js_re.group(1)} != {py_re.group(1)}"


# ---------------- покрытие интерфейса ----------------


def test_bundle_covers_every_frontend_string(report):
    assert report["missing"] == [], f"нет перевода для: {report['missing'][:10]}"
    # `needs_template` — фразы, в которых вставка стоит внутри предложения:
    # их нельзя положить в словарь, только вынести в `t()` шаблоном.
    assert report["needs_template"] == [], (
        f"надо вынести в t() шаблоном: {report['needs_template'][:6]}"
    )


def test_bundle_has_no_dead_ui_keys(report):
    assert report["unused"] == [], f"мёртвые ключи в ui: {report['unused'][:10]}"


def test_exemptions_are_deliberate():
    """Каждое исключение — с причиной, и их не должно стать больше молча."""
    sys.path.insert(0, str(ROOT / "tools"))
    import i18n_extract  # noqa: PLC0415

    assert set(i18n_extract.EXEMPT) == {
        "Крым.",
        "Гид",
        "Крым.Гид",
        "Рус",
        "Крым,",
    }
    assert all(i18n_extract.EXEMPT.values())
    for key in i18n_extract.EXEMPT:
        assert re.search(r"[а-яё]", key), f"в исключения попала латиница: {key!r}"


def test_bundle_is_up_to_date_with_its_sources():
    """en.json генерируется; правка перевода руками = рассинхрон источника."""
    result = subprocess.run(  # noqa: S603
        [sys.executable, "tools/i18n_en/build.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_served_shell_is_translatable(client):
    """Каркас таким, каким его отдал сервер (с подставленным origin).

    Сверка со статикой файлов не то же самое: `GET /` подменяет
    `__ORIGIN__`, правит OG-теги — и именно этот HTML получает человек.
    """
    sys.path.insert(0, str(ROOT / "tools"))
    import i18n_extract  # noqa: PLC0415

    ui = {**bundle_labels_and_ui()}
    nodes = [
        node
        for node in map(
            i18n_extract.normalize,
            i18n_extract.runs_of(
                i18n_extract.COMMENT_RE.sub(" ", client.get("/").text)
            ),
        )
        if node and i18n_extract.has_cyrillic(node)
    ]
    assert len(nodes) >= 10, (
        "в каркасе почти не осталось русской речи — тест надо сверить"
    )
    untranslated = [
        node
        for node in nodes
        if node not in ui
        and i18n_extract.fold_key(node) not in ui
        and node not in i18n_extract.EXEMPT
    ]
    assert not untranslated, f"каркас без перевода: {untranslated[:5]}"


def bundle_labels_and_ui():
    bundle = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
    return {**bundle["labels"], **bundle["ui"]}


# ---------------- каталог ----------------


def test_places_cover_the_catalogue(bundle):
    places = bundle["places"]
    assert set(places) == {a["id"] for a in load_attractions()}, (
        "places и каталог разошлись по id"
    )


def test_place_fields_mirror_the_russian_records(bundle):
    """Что есть по-русски, есть и по-английски — и наоборот.

    Английская карточка не должна быть длиннее русской: поле, которого в
    данных нет, перевод не выдумывает (`applyLabels` это проверяет, здесь —
    что словарь не подбрасывает лишнего).
    """
    app_js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    declared = re.search(r"const PLACE_FIELDS = \[(.*?)\]", app_js, re.S)
    assert declared, "app.js больше не объявляет PLACE_FIELDS"
    fields = re.findall(r'"([^"]+)"', declared.group(1))
    assert fields == PLACE_FIELDS, f"список полей разошёлся с фронтом: {fields}"

    for record in load_attractions():
        translated = bundle["places"][record["id"]]
        for field in PLACE_FIELDS:
            has_russian = bool(str(record.get(field) or "").strip())
            has_english = bool(str(translated.get(field) or "").strip())
            assert has_russian == has_english, (
                f"{record['id']}.{field}: ru={has_russian}, en={has_english}"
            )


def test_places_are_actually_translated(bundle):
    """Проверка на «значение = ключ»: сборщик не обязан угадывать дыры.

    Название вполне может остаться латиницей («Koktebel»), поэтому смотрим
    длинные поля: описание или совет совпасть с русским не могут.
    """
    russian = {a["id"]: a for a in load_attractions()}
    same = [
        f"{pid}.{field}"
        for pid, record in bundle["places"].items()
        for field, value in record.items()
        if field in ("description", "tips")
        and str(value).strip() == str(russian[pid].get(field, "")).strip()
    ]
    assert not same, f"перевод совпадает с оригиналом: {same[:5]}"


# ---------------- подписи, которые собирает сервер ----------------


def test_reasons_are_translatable(bundle):
    """Чипы «почему это место» приходят из Python списком тем.

    Фронт разбирает такую причину по запятым (`tReason`), поэтому в словаре
    обязаны быть и голова списка, и каждая тема, и готовые фразы.
    """
    sys.path.insert(0, str(ROOT))
    from app.services import recommend  # noqa: PLC0415

    ui = {**bundle["labels"], **bundle["ui"]}
    assert ui.get("Совпадает"), "голова причины «Совпадает» не переведена"
    for label in recommend.TAGS.values():
        assert label in ui, f"тема {label!r} не найдена в словаре"
    # `any` причину не строит (`_score_attraction` пропускает его), поэтому
    # «в любое время года» в словаре не нужно.
    for season in recommend.SEASON_LABEL.values():
        if season == recommend.SEASON_LABEL["any"]:
            continue
        key = f"Отличное место {season}"
        assert key in ui, f"нет перевода для {key!r}"
    for phrase in (
        "Дороже, чем ваш бюджет",
        "Отличный вариант с детьми",
        "Тихий и неспешный отдых",
    ):
        assert ui.get(phrase), f"нет перевода для {phrase!r}"


def test_source_badges_are_translatable(bundle):
    """Вывески изданий приходят из данных, а печатает их бейдж новости.

    Английский экран без перевода оставил бы «РБК» и «Крым.Цифровой»
    кириллицей посреди переведённой ленты — ровно та «половина экрана»,
    из-за которой покрытие локали сделано тестом.
    """
    data = ROOT / "app" / "data"
    sources = json.loads((data / "sources.json").read_text("utf-8"))
    snapshot = json.loads((data / "news_snapshot.json").read_text("utf-8"))
    names = {s["name"] for s in sources} | {i["source"] for i in snapshot["items"]}
    ui = {**bundle["labels"], **bundle["ui"]}
    translated = []
    for name in sorted(names):
        if not re.search(r"[а-яёА-ЯЁ]", name):
            continue  # латинскую вывеску («News.ru») переводить нечего
        assert name in ui, f"вывеска {name!r} не переведена"
        assert not re.search(r"[а-яё]", ui[name]), f"в переводе {name!r} кириллица"
        translated.append(name)
    assert len(translated) >= 5, f"вывесок подозрительно мало: {translated}"

    # Покрытие держит инструмент: новые источники попадают в список ключей
    # сами, без правки теста.
    sys.path.insert(0, str(ROOT / "tools"))
    import i18n_extract  # noqa: PLC0415

    assert {"РБК", "Крым.Цифровой"} <= i18n_extract.source_labels()
    assert "News.ru" not in i18n_extract.source_labels(), "латиница не ключ"


def test_module_labels_are_present(bundle):
    """Подписи модулей фронта: их не видит статический сбор ключей.

    Здесь — только те, что собраны из кусков с числами и потому не могут быть
    проверены по исходнику; поведение функций покрывает
    `tests/js/i18n-labels.test.js`.
    """
    ui = {**bundle["labels"], **bundle["ui"]}
    for key in (
        "Ничего не найдено",
        "Найдено: {n}",
        "Показано {n} из {n}",
        "через {n} с",
        "осталось {n} обновление из {n}",
        "🟢 Сейчас открыто · до {n}",
        "🔴 Сегодня выходной",
        "🔴 Закрыто · открывается {n} мая",
        "🔴 Закрыто · открывается в мае",
        "🔴 Закрыто в этом сезоне",
        "🔴 Сейчас закрыто · c {n}",
        "Слишком часто. Попробуйте через {n} с.",
        "Слишком часто. Попробуйте позже.",
        "сейчас",
    ):
        assert ui.get(key), f"нет ключа {key!r}"
