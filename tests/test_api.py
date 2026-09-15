import urllib.parse


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["version"]


def test_security_headers(client):
    r = client.get("/api/health")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert "Referrer-Policy" in r.headers


def test_index_serves_spa(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Крым.Гид" in r.text
    assert "app.js" in r.text


def test_attractions_catalog(client):
    r = client.get("/api/attractions")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 30
    assert all("name" in a and "tags" in a and "area" in a for a in body["items"])


def test_attractions_tag_filter(client):
    body = client.get("/api/attractions?tag=wine").json()
    assert body["count"] >= 3
    assert all("wine" in a["tags"] for a in body["items"])


def test_attractions_area_filter(client):
    area = urllib.parse.quote("Восточный")
    body = client.get(f"/api/attractions?area={area}").json()
    assert body["count"] >= 3
    assert all(a["area"] == "Восточный" for a in body["items"])


def test_attractions_search(client):
    needle = "пляж"
    body = client.get(f"/api/attractions?q={urllib.parse.quote(needle)}").json()
    assert body["count"] >= 1
    assert all(
        needle in a["name"].lower() or needle in a["description"].lower()
        for a in body["items"]
    )


def test_areas_nonempty(client):
    body = client.get("/api/areas").json()
    assert len(body["areas"]) >= 3


def test_tags_dictionary(client):
    body = client.get("/api/tags").json()
    assert "beach" in body["tags"]
    assert "beach" in body["types"]


def test_quiz_content(client):
    body = client.get("/api/quiz").json()
    assert len(body["questions"]) == 7
    assert body["questions"][0]["type"] == "multi"


def test_quiz_evaluate_full(client):
    r = client.post("/api/quiz/evaluate", json={
        "purpose": ["beach", "photo"], "season": "summer", "tempo": "relax",
        "budget": "comfort", "party": "couple", "duration": "3-5", "transport": "car",
    })
    assert r.status_code == 200
    d = r.json()
    assert d["profile"]["title"]
    assert d["recommendations"]
    assert d["itinerary"]["days"]
    assert d["transport_hint"]
    # план покрывает все рекомендации
    day_ids = {s["id"] for day in d["itinerary"]["days"] for s in day["stops"]}
    res_ids = {s["id"] for s in d["itinerary"]["reserve"]}
    rec_ids = {x["id"] for x in d["recommendations"]}
    assert day_ids | res_ids == rec_ids


def test_quiz_evaluate_minimal_payload(client):
    r = client.post("/api/quiz/evaluate", json={})
    assert r.status_code == 200
    assert r.json()["recommendations"]


def test_news_endpoint(client):
    r = client.get("/api/news?limit=5")
    assert r.status_code == 200
    d = r.json()
    assert isinstance(d["items"], list)
    assert len(d["items"]) <= 5
    assert d["online"] in (True, False)
    assert d["crimea_total"] >= 0


def test_weather_endpoint(client):
    r = client.get("/api/weather")
    assert r.status_code == 200
    d = r.json()
    assert "cities" in d
    assert "online" in d
    assert d["cities"]  # города возвращаются всегда (хотя бы available=false)


def test_unknown_api_route_404(client):
    assert client.get("/api/definitely-not-here").status_code == 404
