from app.services.load import get_attractions, get_quiz, get_snapshot, get_sources


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
