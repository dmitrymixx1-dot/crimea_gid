from app.services.load import get_attractions, get_quiz, get_snapshot, get_sources
from app.services.recommend import (AREA_LABEL, DAYS_BY_DURATION,
                                    ITINERARY_DAYS, PROFILES, TAGS, TYPE_META)


def test_attractions_have_coordinates():
    for a in get_attractions():
        assert isinstance(a.get("lat"), (int, float)), a["id"]
        assert isinstance(a.get("lng"), (int, float)), a["id"]
        assert 44.0 <= a["lat"] <= 45.6, a["id"]
        assert 33.0 <= a["lng"] <= 37.0, a["id"]


def test_attractions_schema():
    required = {"id", "name", "type", "region", "area", "description",
                "tags", "season", "budget", "duration_h", "rating",
                "price_hint", "tips", "access", "lat", "lng"}
    for a in get_attractions():
        missing = required - set(a)
        assert not missing, f"{a.get('id')}: нет полей {missing}"
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


def test_profiles_have_all_fields():
    for key, p in PROFILES.items():
        assert p["title"] and p["emoji"] and p["summary"], key
        assert key in TAGS, f"профиль {key} без тега"


def test_type_meta_images_exist():
    """Картинки, названные в TYPE_META, лежат в static/img."""
    from app.config import STATIC_DIR
    for t, meta in TYPE_META.items():
        assert (STATIC_DIR / "img" / meta["img"]).exists(), f"{t}: {meta['img']}"
