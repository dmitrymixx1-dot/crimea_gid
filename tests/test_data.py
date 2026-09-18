import re
from pathlib import Path

from app.services.load import get_attractions, get_quiz, get_snapshot, get_sources
from app.services.recommend import (
    AREA_LABEL,
    BUDGET_CEILING,
    DAYS_BY_DURATION,
    ITINERARY_DAYS,
    PROFILES,
    PURPOSE_TOPICS,
    TAGS,
    TYPE_META,
)


def test_attractions_have_coordinates():
    for a in get_attractions():
        assert isinstance(a.get("lat"), (int, float)), a["id"]
        assert isinstance(a.get("lng"), (int, float)), a["id"]
        # Реальные границы полуострова: Тарханкут (32.49) — Керчь (36.47),
        # Форос (44.39) — Бакальская коса (45.75, самая северная точка каталога).
        assert 44.3 <= a["lat"] <= 45.8, a["id"]
        assert 32.4 <= a["lng"] <= 36.7, a["id"]


def test_attractions_schema():
    required = {
        "id",
        "name",
        "type",
        "region",
        "area",
        "description",
        "tags",
        "season",
        "budget",
        "duration_h",
        "rating",
        "price",
        "price_hint",
        "tips",
        "access",
        "lat",
        "lng",
    }
    optional = {"hours", "schedule"}
    for a in get_attractions():
        missing = required - set(a)
        assert not missing, f"{a.get('id')}: нет полей {missing}"
        extra = set(a) - required - optional
        assert not extra, f"{a['id']}: неизвестные поля {extra}"
        assert a["access"] in ("car", "transit", "both")
        assert 1 <= a["budget"] <= 3


def test_quiz_questions_shape():
    quiz = get_quiz()
    assert len(quiz["questions"]) == 7
    for q in quiz["questions"]:
        assert q["id"] and q["title"] and q["options"]
        for o in q["options"]:
            assert o["id"] and o["label"]


def test_sources_urls_unique():
    urls = [s["url"] for s in get_sources()]
    assert len(urls) == len(set(urls))


def test_snapshot_items_shape():
    snap = get_snapshot()
    assert snap["items"]
    for it in snap["items"]:
        assert it["title"] and it["link"] and it["source"]


# ---------------- согласованность данных со словарями кода ----------------


def test_attraction_ids_unique_and_slug():
    ids = [a["id"] for a in get_attractions()]
    assert len(ids) == len(set(ids)), "дубликаты id в каталоге"
    for i in ids:
        assert i == i.lower() and " " not in i


def test_attraction_tags_known():
    for a in get_attractions():
        unknown = set(a["tags"]) - set(TAGS)
        assert not unknown, f"{a['id']}: неизвестные теги {unknown}"


def test_attraction_types_known():
    for a in get_attractions():
        assert a["type"] in TYPE_META, f"{a['id']}: тип {a['type']}"


def test_attraction_areas_have_labels():
    for a in get_attractions():
        assert a["area"] in AREA_LABEL, f"{a['id']}: район «{a['area']}»"


def test_attraction_value_ranges():
    for a in get_attractions():
        assert 0 < a["duration_h"] <= 12, a["id"]
        assert 0.0 <= a["rating"] <= 5.0, a["id"]
        assert a["season"], f"{a['id']}: пустой season"
        assert a["tags"], f"{a['id']}: пустой tags"
        valid = {"summer", "spring", "autumn", "winter"}
        assert set(a["season"]) <= valid, a["id"]


def test_region_mentions_crimea_places():
    """region не пустой и выглядит как локация (без заглушек)."""
    for a in get_attractions():
        assert len(a["region"]) >= 3, a["id"]
        assert "lorem" not in a["description"].lower(), a["id"]


def test_descriptions_are_fleshed_out():
    """Описание — не строка-питч, а то, что читают в модалке (1.12.0).

    Карточка обрезана CSS line-clamp'ом, поэтому длина не ломает сетку;
    короткая же «цитата» делала модалку тоньше карточки. Разбег символов
    и минимум предложений тест читает из строки `description` в
    [docs/data.md](../docs/data.md) — копия чисел в тесте однажды
    разъехалась бы с правилом (тот же приём, что у границ координат).
    Дубликаты описаний запрещены: копипаста «интересное место для всех»
    проскакивает незаметно. Числа (цены, часы) живут в `price_hint`
    и `hours` — описание с ними не соревнуется, «₽» в тексте считается
    симптомом расхождения.
    """
    doc = Path(__file__).resolve().parents[1] / "docs" / "data.md"
    row = re.search(r"^\|\s*`description`\s*\|.*$", doc.read_text("utf-8"), re.M)
    assert row, "в docs/data.md нет строки `description`"
    rng = re.search(r"(\d+)\s*[–-]\s*(\d+)", row.group(0))
    min_sent = re.search(r"≥\s*(\d+)", row.group(0))
    assert rng and min_sent, f"в строке `description` нет правил: {row.group(0)}"
    low, high = (int(x) for x in rng.groups())
    least = int(min_sent.group(1))
    seen = {}
    for a in get_attractions():
        d = a["description"]
        assert low <= len(d) <= high, f"{a['id']}: {len(d)} символов не в {low}–{high}"
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", d) if s.strip()]
        assert len(sentences) >= least, f"{a['id']}: предложений {len(sentences)}"
        assert d.rstrip().endswith((".", "!", "?", "»")), a["id"]
        assert "…" not in d, f"{a['id']}: описание похоже на обрезанный текст"
        assert "₽" not in d, f"{a['id']}: цена в описании — у неё своё поле"
        if d in seen:
            raise AssertionError(f"дубль описания: {a['id']} == {seen[d]}")
        seen[d] = a["id"]


def test_quiz_purpose_options_are_tags():
    quiz = get_quiz()
    for q in quiz["questions"]:
        if q["id"] == "purpose":
            for o in q["options"]:
                assert o["id"] in TAGS, f"квиз: опция {o['id']} не тег"


def test_quiz_purpose_options_cover_all_tags():
    purpose = next(q for q in get_quiz()["questions"] if q["id"] == "purpose")
    purpose_ids = {o["id"] for o in purpose["options"]}
    assert purpose_ids == set(TAGS), "квиз должен покрывать все теги каталога"


def test_profiles_and_news_topics_cover_all_purposes():
    from app.services.news import TOPIC_RULES

    purpose = next(q for q in get_quiz()["questions"] if q["id"] == "purpose")
    purpose_ids = {o["id"] for o in purpose["options"]}
    news_topics = {topic for topic, _ in TOPIC_RULES}
    assert set(PROFILES) == purpose_ids
    assert set(PURPOSE_TOPICS) == purpose_ids
    for tag, topics in PURPOSE_TOPICS.items():
        assert topics, tag
        assert topics <= news_topics, f"{tag}: неизвестные темы новостей {topics}"


def test_quiz_duration_options_have_planner_entry():
    quiz = get_quiz()
    for q in quiz["questions"]:
        if q["id"] == "duration":
            for o in q["options"]:
                assert o["id"] in DAYS_BY_DURATION
                assert o["id"] in ITINERARY_DAYS


def test_quiz_option_ids_unique_per_question():
    for q in get_quiz()["questions"]:
        ids = [o["id"] for o in q["options"]]
        assert len(ids) == len(set(ids)), q["id"]


def test_quiz_options_match_quiz_model():
    """Literal в QuizIn — в точности id опций из quiz.json.

    Иначе API либо отвергнет честные ответы фронта (422),
    либо пропустит мусор, который evaluate() молча отбросит.
    """
    from typing import get_args

    from app.main import QuizIn

    def literal_values(ann) -> set:
        vals = set()
        for a in get_args(ann):
            if isinstance(a, str):
                vals.add(a)
            else:
                vals |= literal_values(a)
        return vals

    options = {
        q["id"]: {o["id"] for o in q["options"]} for q in get_quiz()["questions"]
    }
    assert set(QuizIn.model_fields) == set(options), (
        "поля QuizIn и вопросы quiz.json разошлись"
    )
    for name, allowed in options.items():
        assert literal_values(QuizIn.model_fields[name].annotation) == allowed, (
            f"поле {name}: Literal не совпадает с quiz.json"
        )
    # Дефолты модели — тоже честные значения.
    defaults = QuizIn()
    for name, allowed in options.items():
        value = getattr(defaults, name)
        if isinstance(value, list):
            assert set(value) <= allowed, name
        else:
            assert value in allowed, name


def test_profiles_have_all_fields():
    for key, p in PROFILES.items():
        assert p["title"] and p["emoji"] and p["summary"], key
        assert key in TAGS, f"профиль {key} без тега"


def test_type_meta_images_exist():
    """Картинки, названные в TYPE_META, лежат в static/img."""
    from app.config import STATIC_DIR

    for t, meta in TYPE_META.items():
        assert (STATIC_DIR / "img" / meta["img"]).exists(), f"{t}: {meta['img']}"


# ---------------- объём каталога и географическая достоверность ----------------


def test_catalog_size_and_area_coverage():
    """Каталог вырос до 60 точек, и в каждом районе есть что показать."""
    items = get_attractions()
    assert len(items) >= 60, f"в каталоге {len(items)} мест"
    for area in AREA_LABEL:
        n = sum(1 for a in items if a["area"] == area)
        assert n >= 10, f"район «{area}»: всего {n} мест"


def test_western_crimea_is_no_longer_the_thin_one():
    """Фаза 1.0: Западный Крым перестал быть «районом на восемь точек» —
    добираем до уровня остальных, иначе планировщик не соберёт там день."""
    items = get_attractions()
    west = [a for a in items if a["area"] == "Западный"]
    assert len(west) >= 15, f"Западный Крым: {len(west)} точек"
    # Планировщик кластеризует день по району: на 3 остановки в день
    # нужен разнообразный набор типов, а не пять пляжей подряд.
    assert len({a["type"] for a in west}) >= 5, "Западный Крым однотипен"
    # Без машины на запад тоже должно быть что предложить.
    assert sum(1 for a in west if a["access"] in ("transit", "both")) >= 4


# ---------------- часы работы ----------------


def test_hours_present_for_ticketed_landmarks():
    """Часы работы указываем там, где график стабилен и публикуется музеем:
    дворцы, пещеры, парки. У «природных» точек их быть не должно —
    честнее отсутствие поля, чем выдуманный график. Второй фильтр —
    круглогодичность: `schedule` обязан покрывать все 12 месяцев, поэтому
    место, закрытое на зиму (Старокрымская крепость), или объект с
    плавающим графиком погоды (канатки Ай-Петри и Демерджи) остаются
    без поля, пока оператор не опубликует годовой режим.
    """
    items = {a["id"]: a for a in get_attractions()}
    for pid in (
        "lastochino",
        "vorontsov",
        "livadia",
        "massandra",
        "khan",
        "hersonesus",
        "nikitsky",
        "marble",
        "taygan",
        "chufut-kale",
        "trip-trentyakov",
        "kenasy",
    ):
        assert items[pid].get("hours"), f"{pid}: нет часов работы"
    for pid in ("koktebel", "tarkhankut", "kazantip", "aipetri", "demerdji"):
        assert not items[pid].get("hours"), (
            f"{pid}: открытой территории или плавающему объекту часы не нужны"
        )
    assert sum(1 for a in items.values() if a.get("hours")) >= 10


def test_hours_look_like_schedules():
    for a in get_attractions():
        hours = a.get("hours")
        if hours is None:
            continue
        assert isinstance(hours, str) and hours.strip() == hours, a["id"]
        assert 5 <= len(hours) <= 200, f"{a['id']}: {len(hours)} символов"
        # В строке обязано быть время вида 9:00 / 18:00.
        assert re.search(r"\d{1,2}:\d{2}", hours), f"{a['id']}: {hours}"


def test_schedule_accompanies_hours():
    """`schedule` — машинная проекция `hours` для фильтра «открыто сейчас».
    Одно без другого бессмысленно: текст без структуры не фильтруется,
    структура без текста лишает человека точных оговорок."""
    for a in get_attractions():
        assert ("hours" in a) == ("schedule" in a), a["id"]


def test_schedule_rules_are_well_formed():
    """Правила должны разбираться тем же способом, что и в open-now.js."""
    days = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
    for a in get_attractions():
        rules = a.get("schedule")
        if rules is None:
            continue
        assert isinstance(rules, list) and rules, a["id"]
        for r in rules:
            m = re.fullmatch(r"(\d{1,2})-(\d{1,2})", r["months"])
            assert m, f"{a['id']}: months={r['months']}"
            start, end = int(m.group(1)), int(m.group(2))
            assert 1 <= start <= 12 and 1 <= end <= 12, a["id"]
            for key in ("from", "to"):
                assert re.fullmatch(r"\d{1,2}:\d{2}", r[key]), f"{a['id']}: {key}"
            open_min = _minutes(r["from"])
            close_min = _minutes(r["to"])
            assert open_min < close_min, f"{a['id']}: {r['from']}–{r['to']}"
            assert set(r.get("closed", [])) <= days, a["id"]
            for key in ("firstDay", "lastDay"):
                if key in r:
                    assert isinstance(r[key], int) and 1 <= r[key] <= 31, (
                        f"{a['id']}: {key}={r[key]!r}"
                    )
            assert set(r) <= {
                "months",
                "from",
                "to",
                "closed",
                "firstDay",
                "lastDay",
            }, set(r)


def test_schedule_covers_every_month():
    """Дыра в месяцах означала бы «закрыто навсегда» в этот период —
    чаще это забытое правило, чем реальная зимовка."""
    for a in get_attractions():
        rules = a.get("schedule")
        if rules is None:
            continue
        for month in range(1, 13):
            covered = any(_month_in_range(month, r["months"]) for r in rules)
            assert covered, f"{a['id']}: месяц {month} не покрыт расписанием"


SEASON_MONTHS = {
    "winter": {12, 1, 2},
    "spring": {3, 4, 5},
    "summer": {6, 7, 8},
    "autumn": {9, 10, 11},
}


def test_season_agrees_with_published_schedule():
    """У места с расписанием `season` — не «красивое время года», а когда
    оно работает: дворец с часами «9:00–17:00 (ноябрь–март)» обязан быть
    в списке зимой. Иначе наши же данные спорят друг с другом — карточка
    говорит «открыто», а квиз штрафует место на балл за несезон
    (`recommend.py`: `score -= 1.0`) и зимой выдаёт пустой результат.

    Правило двустороннее: сезона нет в расписании — нет его и в `season`
    (обещать визит в закрытые месяцы нельзя). Места без `schedule` —
    пляжи, мысы, водопады — остаются на совести редактора: сверять их
    не с чем, публикуемого графика у них нет.
    """
    for a in get_attractions():
        rules = a.get("schedule")
        if rules is None:
            continue
        open_months = {
            month
            for r in rules
            for month in range(1, 13)
            if _month_in_range(month, r["months"])
        }
        covered = {s for s, months in SEASON_MONTHS.items() if months & open_months}
        missing = covered - set(a["season"])
        assert not missing, (
            f"{a['id']}: по расписанию работает в {sorted(missing)}, "
            f"а season={a['season']}"
        )
        extra = set(a["season"]) - covered
        assert not extra, (
            f"{a['id']}: season обещает {sorted(extra)}, "
            f"но расписание в эти месяцы молчит"
        )


def test_every_season_and_area_has_something_to_offer():
    """Квиз спрашивает сезон и не должен отвечать пустотой: на каждый
    сезон — десятки мест, и в каждом районе хотя бы пара. Зимой так было
    не всегда (8 мест на весь полуостров, Восточный — ноль), пока `season`
    не начали выводить из расписания."""
    for season in SEASON_MONTHS:
        picks = [a for a in get_attractions() if season in a["season"]]
        assert len(picks) >= 20, f"{season}: всего {len(picks)} мест"
        areas = {a["area"] for a in picks}
        assert areas == set(AREA_LABEL), (
            f"{season}: нет мест в {set(AREA_LABEL) - areas}"
        )


def test_schedule_times_appear_in_the_human_text():
    """Главный риск расхождения: поправили текст, забыли структуру
    (или наоборот). Любое время из `schedule` обязано встречаться
    в `hours` — иначе бейдж «открыто» противоречит карточке."""
    for a in get_attractions():
        rules = a.get("schedule")
        if rules is None:
            continue
        text = a["hours"].replace("–", "-")
        for rule in rules:
            for key in ("from", "to"):
                stamp = rule[key]
                variants = {stamp, stamp.lstrip("0")}
                assert variants & {v for v in variants if v in text}, (
                    f"{a['id']}: {stamp} из schedule нет в hours «{a['hours']}»"
                )


MONTH_GENITIVE = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}
_DAYS_IN_MONTH = {
    1: 31,
    2: 28,
    3: 31,
    4: 30,
    5: 31,
    6: 30,
    7: 31,
    8: 31,
    9: 30,
    10: 31,
    11: 30,
    12: 31,
}
_GEN = "|".join(MONTH_GENITIVE.values())
_DAY_MONTH = re.compile(rf"\b(\d{{1,2}})\s+({_GEN})\b")
_MONTH_DAY = re.compile(rf"\b({_GEN})\s+(\d{{1,2}})\b")


def _text_boundaries(text: str) -> set[tuple[int, int]]:
    """Пары (месяц, число) вида «16 июня» / «15 октября» из текста hours."""
    found: set[tuple[int, int]] = set()
    for m in _DAY_MONTH.finditer(text):
        day, month = (
            int(m.group(1)),
            next(k for k, v in MONTH_GENITIVE.items() if v == m.group(2)),
        )
        if 1 <= day <= 31:
            found.add((month, day))
    for m in _MONTH_DAY.finditer(text):
        day, month = (
            int(m.group(2)),
            next(k for k, v in MONTH_GENITIVE.items() if v == m.group(1)),
        )
        if 1 <= day <= 31:
            found.add((month, day))
    return found


def _struct_boundaries(rules: list[dict]) -> set[tuple[int, int]]:
    """Дневные границы из schedule: (месяц, число) для firstDay/lastDay."""
    out: set[tuple[int, int]] = set()
    for r in rules:
        start, end = (int(x) for x in r["months"].split("-"))
        if "firstDay" in r:
            out.add((start, r["firstDay"]))
        if "lastDay" in r and r["lastDay"] < _DAYS_IN_MONTH[end]:
            out.add((end, r["lastDay"]))
    return out


def test_schedule_day_boundaries_match_the_human_text():
    """Дневные границы schedule и «16 июня»-детали в hours обязаны
    совпадать — по тому же правилу, что и времена. Исключение: старт
    окна может быть неявным, как день после конца соседнего окна в том
    же месяце («16 июня–15 октября» + зимнее окно с 16 октября)."""
    for a in get_attractions():
        rules = a.get("schedule")
        if rules is None:
            continue
        in_text = _text_boundaries(a["hours"])
        in_struct = _struct_boundaries(rules)
        for month, day in in_text:
            assert (month, day) in in_struct, (
                f"{a['id']}: «{day} {MONTH_GENITIVE[month]}» в hours, "
                f"но нет границы в schedule"
            )
        for month, day in in_struct:
            if (month, day) in in_text:
                continue
            adjacent = any(m2 == month and abs(d2 - day) == 1 for m2, d2 in in_struct)
            assert adjacent, (
                f"{a['id']}: граница {day} {MONTH_GENITIVE[month]} в "
                f"schedule не отражена в hours и не граничит с окном"
            )


def _minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def _month_in_range(month: int, spec: str) -> bool:
    start, end = (int(x) for x in spec.split("-"))
    return start <= month <= end if start <= end else (month >= start or month <= end)


def test_price_hints_are_informative():
    """Цена — либо сумма в рублях, либо честное «бесплатно»."""
    for a in get_attractions():
        hint = a["price_hint"].lower()
        assert "₽" in hint or "бесплат" in hint, f"{a['id']}: {a['price_hint']}"


# Цена и уровень бюджета — две машинные проекции одной человеческой строки,
# как `schedule` для `hours`. Правило живёт в docs/data.md, а здесь оно
# проверяется в обе стороны: поменяли подсказку, не тронув числа, — тест
# показывает место. Раньше `budget` был оценкой редактора: 42 места из 60
# стояли в «экономе», среди них билеты по 600 ₽, а уровень 3 был один —
# и ответ «премиум» в квизе не менял ничего.
PRICE_RE = re.compile(
    r"(\d[\d\s\u00a0]*\d|\d)\s*(?:[–—]\s*(\d[\d\s\u00a0]*\d|\d)\s*)?₽"
)


def hinted_prices(hint: str) -> list[int]:
    """Все цены из подсказки: «300–500 ₽» — это и 300, и 500."""
    out: list[int] = []
    for match in PRICE_RE.finditer(hint):
        out.extend(int(re.sub(r"[\s\u00a0]", "", g)) for g in match.groups() if g)
    return out


def test_price_is_the_lowest_price_of_the_place():
    """`price` — минимум, за который место доступно: 0, если в подсказке
    есть бесплатный вариант, иначе самая низкая цена оттуда."""
    for a in get_attractions():
        nums = hinted_prices(a["price_hint"])
        free = "бесплат" in a["price_hint"].lower()
        assert nums or free, f"{a['id']}: в подсказке нет ни цены, ни «бесплатно»"
        expected = 0 if free else min(nums)
        assert isinstance(a["price"], int) and a["price"] >= 0, a["id"]
        assert a["price"] == expected, (
            f"{a['id']}: {a['price']} ≠ {expected} ({a['price_hint']})"
        )


def test_budget_level_follows_the_highest_price():
    """`budget` — полоса самой дорогой цены из подсказки, по порогам квиза:
    ≤1 000 ₽ → 1, ≤3 000 ₽ → 2, дороже → 3. Это «сколько место может
    вместить», а не «сколько стоит прийти» (то — `price`)."""
    for a in get_attractions():
        nums = hinted_prices(a["price_hint"])
        top = max(nums) if nums else 0
        expected = 1 if top <= 1000 else (2 if top <= 3000 else 3)
        assert a["budget"] == expected, (
            f"{a['id']}: {a['budget']} ≠ {expected} ({a['price_hint']})"
        )


def test_budget_levels_use_the_whole_scale():
    """Каждый уровень кому-то адресован: пустая полоса — это ответ квиза,
    который ничего не решает."""
    items = get_attractions()
    for level in (1, 2, 3):
        assert [a for a in items if a["budget"] == level], f"уровень {level} пуст"
    assert len([a for a in items if a["budget"] == 3]) >= 3
    # Потолок эконома обязан что-то отсекать, иначе он не потолок.
    assert [a for a in items if a["price"] > BUDGET_CEILING["economy"]]


def test_budget_thresholds_match_the_quiz():
    """Числа в подсказках квиза — те же, что в баллах матч-мейкера."""
    options = {
        o["id"]: o.get("hint", "")
        for q in get_quiz()["questions"]
        if q["id"] == "budget"
        for o in q["options"]
    }
    for answer, ceiling in BUDGET_CEILING.items():
        text = re.sub(r"[\s\u00a0]+", " ", options[answer])
        spelled = f"{ceiling:,}".replace(",", " ")
        assert spelled in text, f"{answer}: порога {spelled} нет в «{options[answer]}»"
    # «Премиум» — единственный ответ без потолка: числа в подсказке нет.
    assert not re.search(r"\d", options["premium"])


# Координаты сверены с OpenStreetMap/Википедией: якоря не дают «уплыть»
# точкам обратно в приблизительные значения.
ANCHORS = {
    "lastochino": (44.4306, 34.1286),
    "vorontsov": (44.4198, 34.0558),
    "hersonesus": (44.6117, 33.4933),
    "sudak": (44.8506, 34.9761),
    "feodosia": (45.0489, 35.3792),
    "koktebel": (44.9597, 35.2403),
    "mangup": (44.5931, 33.8014),
    "tarkhankut": (45.3473, 32.4936),
    "kazantip": (45.4610, 35.8458),
    "meganom": (44.7939, 35.0807),
}


def test_anchor_coordinates_are_real():
    items = {a["id"]: a for a in get_attractions()}
    for pid, (lat, lng) in ANCHORS.items():
        a = items[pid]
        assert abs(a["lat"] - lat) < 0.02, f"{pid}: широта {a['lat']}"
        assert abs(a["lng"] - lng) < 0.02, f"{pid}: долгота {a['lng']}"


def test_coordinate_bounds_in_docs_cover_the_catalog():
    """Границы координат объявлены в `docs/data.md` и обязаны покрывать
    каталог: заявленные когда-то 33.0–37.0 в. д. не включали Тарханкут
    (32.49), и редактор принял бы верную точку за ошибку. Тест читает
    документ, а не держит копию чисел — иначе сверять нечего."""
    doc = Path(__file__).resolve().parents[1] / "docs" / "data.md"
    bounds = {}
    for field in ("lat", "lng"):
        row = re.search(
            rf"^\|\s*`{field}`\s*\|.*$", doc.read_text(encoding="utf-8"), re.M
        )
        assert row, f"в docs/data.md нет строки `{field}`"
        found = re.search(r"(\d+(?:[.,]\d+)?)\s*[–-]\s*(\d+(?:[.,]\d+)?)", row.group(0))
        assert found, f"в строке `{field}` нет диапазона: {row.group(0)}"
        bounds[field] = tuple(float(x.replace(",", ".")) for x in found.groups())
    for a in get_attractions():
        for field, (low, high) in bounds.items():
            assert low <= a[field] <= high, (
                f"{a['id']}: {field}={a[field]} вне {low}–{high} из docs/data.md"
            )


def test_western_crimea_reaches_tarkhankut():
    """Самая западная точка каталога — Тарханкут (≈32.49 в. д.)."""
    west = min(a["lng"] for a in get_attractions())
    assert west < 32.6, f"западная граница каталога {west}"


# ---------------- новый тег «экстрим и дайвинг» ----------------


def test_extreme_tag_wired_everywhere():
    from app.services.recommend import PROFILES, TAG_EMOJI

    quiz = get_quiz()
    purpose = next(q for q in quiz["questions"] if q["id"] == "purpose")
    assert "extreme" in TAGS and "extreme" in TAG_EMOJI
    assert "extreme" in PROFILES
    assert any(o["id"] == "extreme" for o in purpose["options"])
    assert sum("extreme" in a["tags"] for a in get_attractions()) >= 3


# ---------------- источники новостей ----------------


def test_sources_counts_and_urls():
    sources = get_sources()
    rss = [s for s in sources if s["type"] == "rss"]
    tg = [s for s in sources if s["type"] == "telegram"]
    assert len(rss) >= 7, f"RSS-лент {len(rss)}"
    assert len(tg) >= 4, f"телеграм-каналов {len(tg)}"
    for s in sources:
        assert s["url"].startswith("https://"), s["id"]
        assert s["name"] and s["description"], s["id"]
    for s in tg:
        assert s["url"].startswith("https://t.me/s/"), s["id"]
