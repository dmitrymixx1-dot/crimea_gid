from app.services.recommend import PROFILES, evaluate, plan_itinerary


def _ans(**kw):
    base = dict(purpose=["beach"], season="any", tempo="medium", budget="comfort",
                party="solo", duration="3-5", transport="car")
    base.update(kw)
    return base


def test_purpose_match_ranks_wine_winery_high():
    r = evaluate(_ans(purpose=["wine"]), [])
    names = [x["name"] for x in r["recommendations"][:3]]
    assert any("Винзавод" in n or "погреб" in n.lower() for n in names) or \
        any("вин" in x["tags"] for x in r["recommendations"][:3])


def test_no_car_excludes_car_only_places():
    r = evaluate(_ans(transport="transit"), [])
    assert r["recommendations"]
    assert all(x["access"] != "car" for x in r["recommendations"])


def test_profiles_by_main_purpose():
    assert evaluate(_ans(purpose=["wine"]), [])["profile"]["title"] == "Винная карта Крыма"
    assert evaluate(_ans(purpose=["beach"]), [])["profile"]["title"] == "Море, солнце и спокойствие"
    assert evaluate(_ans(purpose=["history"]), [])["profile"]["title"] == "Исследователь прошлого"


def test_empty_purpose_falls_back_to_beach():
    r = evaluate(_ans(purpose=[]), [])
    assert r["answers"]["purpose"] == ["beach"]
    assert r["recommendations"]


def test_duration_limits_recommendations():
    short = evaluate(_ans(duration="1-2"), [])
    long = evaluate(_ans(duration="10+"), [])
    assert len(short["recommendations"]) <= 5
    assert len(long["recommendations"]) >= len(short["recommendations"])


def test_recommendations_have_reasons_when_matched():
    r = evaluate(_ans(purpose=["beach"]), [])
    with_reasons = [x for x in r["recommendations"] if x["reasons"]]
    assert with_reasons


# ---------------- itinerary ----------------

def test_itinerary_single_rec_one_day():
    rec = [{"area": "Южный берег", "duration_h": 2, "tags": ["beach"], "id": "a", "name": "X"}]
    r = plan_itinerary(rec, "1-2")
    assert len(r["days"]) == 1
    assert r["days"][0]["stops"][0]["slot"] in ("morning", "evening")
    assert r["reserve"] == []


def test_itinerary_full_day_places_are_alone():
    rec = [{"area": "Центральный", "duration_h": 7, "tags": ["active"], "id": f"a{i}", "name": f"A{i}"}
           for i in range(4)]
    r = plan_itinerary(rec, "3-5")
    assert len(r["days"]) == 4
    for d in r["days"]:
        assert len(d["stops"]) == 1
        assert d["stops"][0]["slot"] == "full"


def test_itinerary_days_within_budget_and_single_area():
    r = evaluate(_ans(duration="10+"), [])
    it = r["itinerary"]
    assert len(it["days"]) <= it["n_days"]
    for d in it["days"]:
        assert len(d["stops"]) <= 3


def test_itinerary_covers_all_recommendations():
    r = evaluate(_ans(duration="10+"), [])
    it = r["itinerary"]
    day_ids = {s["id"] for d in it["days"] for s in d["stops"]}
    res_ids = {s["id"] for s in it["reserve"]}
    rec_ids = {x["id"] for x in r["recommendations"]}
    assert day_ids | res_ids == rec_ids
    assert day_ids & res_ids == set()


def test_itinerary_slots_are_known():
    r = evaluate(_ans(purpose=["beach", "history"], duration="6-10"), [])
    known = {"morning", "afternoon", "evening", "full"}
    for d in r["itinerary"]["days"]:
        for s in d["stops"]:
            assert s["slot"] in known


def test_profiles_cover_all_quiz_purposes():
    for purpose in ("beach", "nature", "history", "food", "family", "photo"):
        assert purpose in PROFILES
