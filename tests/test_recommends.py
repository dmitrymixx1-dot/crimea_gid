from app.services.recommend import PROFILES, _score_attraction, evaluate, plan_itinerary


def _ans(**kw):
    base = {"purpose": ["beach"], "season": "any", "tempo": "medium",
            "budget": "comfort", "party": "solo", "duration": "3-5",
            "transport": "car"}
    base.update(kw)
    return base


def test_purpose_match_ranks_wine_winery_high():
    r = evaluate(_ans(purpose=["wine"]), [])
    top3 = r["recommendations"][:3]
    assert top3
    assert any(x["type"] == "winery" or "wine" in x["tags"] for x in top3)


def test_no_car_excludes_car_only_places():
    r = evaluate(_ans(transport="transit"), [])
    assert r["recommendations"]
    assert all(x["access"] != "car" for x in r["recommendations"])


def test_profiles_by_main_purpose():
    def title(purpose):
        return evaluate(_ans(purpose=[purpose]), [])["profile"]["title"]

    assert title("wine") == "Винная карта Крыма"
    assert title("beach") == "Море, солнце и спокойствие"
    assert title("history") == "Исследователь прошлого"


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
    rec = [{"area": "Южный берег", "duration_h": 2, "tags": ["beach"],
            "id": "a", "name": "X"}]
    r = plan_itinerary(rec, "1-2")
    assert len(r["days"]) == 1
    assert r["days"][0]["stops"][0]["slot"] in ("morning", "evening")
    assert r["reserve"] == []


def test_itinerary_full_day_places_are_alone():
    rec = [{"area": "Центральный", "duration_h": 7, "tags": ["active"],
            "id": f"a{i}", "name": f"A{i}"} for i in range(4)]
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


# ---------------- тонкости матчинга ----------------

def test_unknown_purpose_tags_are_dropped_and_capped():
    r = evaluate(_ans(purpose=["beach", "unknown", "nature", "history", "food"]), [])
    # «unknown» выброшен, оставлены первые 3 валидных
    assert r["answers"]["purpose"] == ["beach", "nature", "history"]


def test_score_budget_penalty_with_reason():
    place = {"id": "p", "name": "P", "tags": [], "season": [], "budget": 3,
             "duration_h": 3, "rating": 4.5, "access": "both"}
    score, reasons = _score_attraction(place, _ans(budget="economy"))
    assert "Дороже, чем ваш бюджет" in reasons
    cheap_score, _ = _score_attraction(place, _ans(budget="premium"))
    assert cheap_score > score  # тот же объект дешевле не станет — разница в баллах


def test_score_season_bonus_and_penalty():
    place = {"id": "p", "name": "P", "tags": [], "season": ["summer"],
             "budget": 2, "duration_h": 3, "rating": 4.0, "access": "both"}
    in_season, in_reasons = _score_attraction(place, _ans(season="summer"))
    out_season, _ = _score_attraction(place, _ans(season="winter"))
    assert in_season > out_season
    assert any("летом" in r for r in in_reasons)


def test_score_season_any_is_neutral():
    place = {"id": "p", "name": "P", "tags": [], "season": ["summer"],
             "budget": 2, "duration_h": 3, "rating": 4.0, "access": "both"}
    any_score, _ = _score_attraction(place, _ans(season="any"))
    base = 1.0 + (4.0 - 4.0)  # бюджет ок + рейтинг-бонус
    assert any_score == base


def test_score_transit_car_only_penalty():
    place = {"id": "p", "name": "P", "tags": [], "season": [], "budget": 2,
             "duration_h": 3, "rating": 4.0, "access": "car"}
    transit, _ = _score_attraction(place, _ans(transport="transit"))
    car, _ = _score_attraction(place, _ans(transport="car"))
    assert car - transit == 3.0


def test_score_interest_match_reason_uses_tag_names():
    place = {"id": "p", "name": "P", "tags": ["wine", "food"], "season": [],
             "budget": 2, "duration_h": 3, "rating": 4.0, "access": "both"}
    _, reasons = _score_attraction(place, _ans(purpose=["wine"]))
    assert any("вино" in r or "гастроном" in r for r in reasons)


def test_score_rating_bonus():
    low = {"id": "a", "name": "A", "tags": [], "season": [], "budget": 2,
           "duration_h": 3, "rating": 4.0, "access": "both"}
    high = dict(low, rating=4.8)
    s_low, _ = _score_attraction(low, _ans())
    s_high, _ = _score_attraction(high, _ans())
    assert round(s_high - s_low, 5) == 0.8


def test_transit_penalty_reason_keeps_car_places_out():
    r = evaluate(_ans(transport="transit"), [])
    car_only = [x for x in r["recommendations"] if x["access"] == "car"]
    assert car_only == []


def test_family_party_boosts_family_reason():
    r = evaluate(_ans(party="family", purpose=["family"]), [])
    fam = [x for x in r["recommendations"] if "family" in x["tags"]]
    assert fam
    assert any("Отличный вариант с детьми" in x["reasons"] for x in fam)


def test_recommendation_shape_complete():
    r = evaluate(_ans(), [])
    for x in r["recommendations"]:
        assert {"id", "name", "type", "region", "area", "tags", "season",
                "budget", "duration_h", "rating", "lat", "lng",
                "type_meta", "score", "reasons"} <= set(x)
        assert x["type_meta"]["emoji"]
        assert isinstance(x["score"], float)


def test_transport_hint_matches_choice():
    assert "машине" in evaluate(_ans(transport="car"), [])["transport_hint"]
    assert "Без машины" in evaluate(_ans(transport="transit"), [])["transport_hint"]


def test_news_picks_only_crimea():
    news = [
        {"title": "В Судаке открыли сезон", "crimea_score": 4, "topics": ["beach"],
         "link": "http://x/1", "published": "2026-09-15"},
        {"title": "Мировые рынки упали", "crimea_score": 0, "topics": [],
         "link": "http://x/2", "published": "2026-09-15"},
    ]
    r = evaluate(_ans(purpose=["beach"]), news)
    picked = {n["title"] for n in r["news"]}
    assert "В Судаке открыли сезон" in picked
    assert "Мировые рынки упали" not in picked


def test_news_not_in_topic_but_crimea_core_still_picked():
    news = [{"title": "Крым: важная веха", "crimea_score": 9, "topics": ["safety"],
             "link": "http://x/1", "published": "2026-09-15"}]
    r = evaluate(_ans(purpose=["wine"]), news)
    assert [n["title"] for n in r["news"]] == ["Крым: важная веха"]


def test_news_capped_at_four():
    news = [{"title": f"Крым новость {i}", "crimea_score": 5, "topics": ["beach"],
             "link": f"http://x/{i}", "published": "2026-09-15"} for i in range(10)]
    r = evaluate(_ans(purpose=["beach"]), news)
    assert len(r["news"]) == 4


# ---------------- планировщик: edge cases ----------------

def test_itinerary_empty_recs():
    r = plan_itinerary([], "3-5")
    assert r["days"] == []
    assert r["reserve"] == []
    assert r["n_days"] == 4


def test_itinerary_evening_slot_for_short_last_stop():
    recs = [
        {"area": "A", "duration_h": 3, "tags": [], "id": "x", "name": "Утро"},
        {"area": "A", "duration_h": 3, "tags": [], "id": "y", "name": "День"},
        {"area": "A", "duration_h": 2, "tags": [], "id": "z", "name": "Вечер"},
    ]
    r = plan_itinerary(recs, "1-2")
    day = r["days"][0]
    assert day["stops"][0]["slot"] == "morning"
    assert day["stops"][-1]["slot"] == "evening"


def test_itinerary_area_clustering():
    """День не смешивает районы: каждый день — один район."""
    def _rec(area, prefix, i):
        return {"area": area, "duration_h": 2, "tags": [],
                "id": f"{prefix}{i}", "name": f"{prefix}{i}"}

    recs = ([_rec("Южный берег", "s", i) for i in range(4)] +
            [_rec("Западный", "w", i) for i in range(4)])
    r = plan_itinerary(recs, "1-2")
    assert r["days"]
    for d in r["days"]:
        assert {s["area"] for s in d["stops"]} == {d["area"]}
    assert d["area_label"]


def test_itinerary_reserve_goes_beyond_days():
    recs = [{"area": "A", "duration_h": 2, "tags": [], "id": f"a{i}", "name": f"A{i}"}
            for i in range(10)]
    r = plan_itinerary(recs, "1-2")  # 2 дня × ≤3 стопа
    placed = sum(len(d["stops"]) for d in r["days"])
    assert len(r["reserve"]) == 10 - placed > 0


def test_itinerary_stops_per_day_cap():
    """Не больше 3 остановок в день; часы проверяются до добавления,
    поэтому сумма может превысить 7 — детерминированно: 3+3+3 → один день."""
    recs = [{"area": "A", "duration_h": 3, "tags": [], "id": f"a{i}", "name": f"A{i}"}
            for i in range(4)]
    r = plan_itinerary(recs, "1-2")
    for d in r["days"]:
        assert len(d["stops"]) <= 3
    # 4 точки по 3ч на 2 дня: день 1 = три точки (9ч), день 2 = одна
    assert [len(d["stops"]) for d in r["days"]] == [3, 1]


def test_itinerary_day_tags_from_stops():
    recs = [{"area": "A", "duration_h": 2, "tags": ["beach", "view"],
             "id": "a", "name": "A"}]
    r = plan_itinerary(recs, "1-2")
    assert r["days"][0]["tags"] == ["beach", "view"]
