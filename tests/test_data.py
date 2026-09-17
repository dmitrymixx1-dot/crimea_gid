import re

from app.services.load import get_attractions, get_quiz, get_snapshot, get_sources
from app.services.recommend import (
    AREA_LABEL,
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
    required = {"id", "name", "type", "region", "area", "description",
                "tags", "season", "budget", "duration_h", "rating",
                "price_hint", "tips", "access", "lat", "lng"}
    optional = {"hours"}
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

    options = {q["id"]: {o["id"] for o in q["options"]}
               for q in get_quiz()["questions"]}
    assert set(QuizIn.model_fields) == set(options), \
        "поля QuizIn и вопросы quiz.json разошлись"
    for name, allowed in options.items():
        assert literal_values(QuizIn.model_fields[name].annotation) == allowed, \
            f"поле {name}: Literal не совпадает с quiz.json"
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
    честнее отсутствие поля, чем выдуманный график."""
    items = {a["id"]: a for a in get_attractions()}
    for pid in ("lastochino", "vorontsov", "livadia", "massandra", "khan",
                "hersonesus", "nikitsky", "marble", "taygan", "chufut-kale"):
        assert items[pid].get("hours"), f"{pid}: нет часов работы"
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


def test_price_hints_are_informative():
    """Цена — либо сумма в рублях, либо честное «бесплатно»."""
    for a in get_attractions():
        hint = a["price_hint"].lower()
        assert "₽" in hint or "бесплат" in hint, f"{a['id']}: {a['price_hint']}"


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
