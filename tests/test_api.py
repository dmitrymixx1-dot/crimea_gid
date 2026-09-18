import re
import urllib.parse

from app import main
from app.config import APP_VERSION


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


def test_attractions_carry_the_machine_price(client):
    """`price` — машинная цена входа рядом с человеческой `price_hint`:
    её читает матч-мейкер, чтобы «дорого» звучало только там, где за вход
    правда нужно платить больше бюджета."""
    items = client.get("/api/attractions").json()["items"]
    assert items
    for a in items:
        assert isinstance(a["price"], int) and a["price"] >= 0, a["id"]
        assert 1 <= a["budget"] <= 3, a["id"]


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
    r = client.post(
        "/api/quiz/evaluate",
        json={
            "purpose": ["beach", "photo"],
            "season": "summer",
            "tempo": "relax",
            "budget": "comfort",
            "party": "couple",
            "duration": "3-5",
            "transport": "car",
        },
    )
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
    # «Об источниках» (1.12.0): карточки блока строятся из этих полей,
    # без подписи и адреса блок деградирует до голых вывесок.
    for s in d["sources"]:
        assert set(s) >= {"id", "name", "description", "url", "type"}
        assert s["description"], f"источник {s['id']} пришёл без подписи"


def test_weather_endpoint(client):
    r = client.get("/api/weather")
    assert r.status_code == 200
    d = r.json()
    assert "cities" in d
    assert "online" in d
    assert d["cities"]  # города возвращаются всегда (хотя бы available=false)


def test_unknown_api_route_404(client):
    assert client.get("/api/definitely-not-here").status_code == 404


def test_attraction_detail(client):
    body = client.get("/api/attractions").json()
    some_id = body["items"][0]["id"]
    r = client.get(f"/api/attractions/{some_id}")
    assert r.status_code == 200
    d = r.json()
    assert d["id"] == some_id
    assert d["type_meta"]["emoji"]
    assert isinstance(d["lat"], (int, float))


def test_attraction_detail_404(client):
    r = client.get("/api/attractions/no-such-place-42")
    assert r.status_code == 404
    assert "не найдено" in r.json()["detail"]


def test_service_worker_from_root(client):
    r = client.get("/sw.js")
    assert r.status_code == 200
    assert "javascript" in r.headers["content-type"]
    assert r.headers.get("Service-Worker-Allowed") == "/"
    assert "crimea-gid" in r.text


def test_pwa_manifest_and_icons(client):
    r = client.get("/static/manifest.webmanifest")
    assert r.status_code == 200
    m = r.json()
    assert m["display"] == "standalone"
    assert m["theme_color"]
    for icon in m["icons"]:
        assert client.get(icon["src"]).status_code == 200


def test_index_links_manifest(client):
    r = client.get("/")
    assert "manifest.webmanifest" in r.text
    assert "theme-color" in r.text


# ---------------- расширенный каталог (0.10.0) ----------------


def test_catalog_grew_to_fifty(client):
    body = client.get("/api/attractions").json()
    assert body["count"] >= 50


def test_extreme_tag_filter(client):
    body = client.get("/api/attractions?tag=extreme").json()
    assert body["count"] >= 3
    assert all("extreme" in a["tags"] for a in body["items"])
    assert "extreme" in client.get("/api/tags").json()["tags"]


def test_western_area_filter(client):
    body = client.get("/api/attractions?area=" + urllib.parse.quote("Западный")).json()
    assert body["count"] >= 5
    ids = {a["id"] for a in body["items"]}
    assert {"tarkhankut", "olenivka", "atlesh"} <= ids


def test_single_attraction_has_real_coordinates(client):
    body = client.get("/api/attractions/tarkhankut").json()
    assert body["name"] == "Тарханкутский маяк"
    assert abs(body["lat"] - 45.3473) < 0.02
    assert abs(body["lng"] - 32.4936) < 0.02


def test_quiz_offers_extreme_interest(client):
    body = client.get("/api/quiz").json()
    purpose = next(q for q in body["questions"] if q["id"] == "purpose")
    assert any(o["id"] == "extreme" for o in purpose["options"])


def test_quiz_evaluate_extreme_profile(client):
    r = client.post(
        "/api/quiz/evaluate",
        json={
            "purpose": ["extreme"],
            "season": "summer",
            "tempo": "active",
            "budget": "comfort",
            "party": "friends",
            "duration": "3-5",
            "transport": "car",
        },
    )
    assert r.status_code == 200
    d = r.json()
    assert d["profile"]["title"] == "Крым на адреналине"
    assert any("extreme" in x["tags"] for x in d["recommendations"][:3])


def test_health_reports_new_version(client):
    assert client.get("/api/health").json()["version"] == APP_VERSION


# ---------------- контракт API (0.11.0) ----------------


def test_quiz_evaluate_rejects_garbage_values(client):
    r = client.post(
        "/api/quiz/evaluate",
        json={
            "purpose": ["beach"],
            "season": "never",
            "budget": "free",
            "tempo": "turbo",
            "party": "aliens",
            "duration": "100",
            "transport": "teleport",
        },
    )
    assert r.status_code == 422


def test_quiz_evaluate_rejects_bad_purpose(client):
    r = client.post("/api/quiz/evaluate", json={"purpose": ["teleport"]})
    assert r.status_code == 422


def test_quiz_evaluate_empty_purpose_defaults_to_beach(client):
    r = client.post("/api/quiz/evaluate", json={"purpose": []})
    assert r.status_code == 200
    d = r.json()
    assert d["answers"]["purpose"] == ["beach"]
    assert d["recommendations"]


def test_weather_unknown_city_404(client):
    r = client.get("/api/weather?city=gotham")
    assert r.status_code == 404
    assert "не найден" in r.json()["detail"]


def test_weather_single_city_filter(client):
    d = client.get("/api/weather?city=yalta").json()
    assert [c["id"] for c in d["cities"]] == ["yalta"]


# ---------------- почасовой прогноз (1.4.0) ----------------


class _FakeWeather:
    """Заглушка погодного сервиса: HTTP-тесты не ходят в сеть."""

    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    async def get(self, city=None, refresh=False):
        self.calls.append((city, refresh))
        return self.payload


WEATHER_PAYLOAD = {
    "online": True,
    "updated_at": "2026-09-17T12:00:00+03:00",
    "cities": [
        {
            "id": "yalta",
            "name": "Ялта",
            "available": True,
            "current": {"temp": 22, "emoji": "🌤️", "label": "ясно", "wind": 12},
            "forecast": [{"day": "Ср", "emoji": "🌤️", "max": 26, "min": 17}],
            "hourly": [
                {"t": "2026-09-17T12:00", "temp": 22, "emoji": "🌤️", "precip": 5},
                {"t": "2026-09-17T13:00", "temp": 23, "emoji": "⛅", "precip": 40},
            ],
        }
    ],
}


def test_weather_payload_includes_hourly(client, monkeypatch):
    fake = _FakeWeather(WEATHER_PAYLOAD)
    monkeypatch.setattr(main, "weather_service", fake)
    d = client.get("/api/weather?city=yalta").json()
    hourly = d["cities"][0]["hourly"]
    assert len(hourly) == 2
    assert set(hourly[0]) == {"t", "temp", "emoji", "precip"}
    assert hourly[0]["t"].startswith("2026-09-17T12")
    assert fake.calls == [("yalta", False)]


def test_weather_refresh_passes_through(client, monkeypatch):
    fake = _FakeWeather(WEATHER_PAYLOAD)
    monkeypatch.setattr(main, "weather_service", fake)
    client.get("/api/weather?refresh=1")
    assert fake.calls == [(None, True)]


# ---------------- море и купальный индекс (1.3.0) ----------------


class _FakeSea:
    """Заглушка морского сервиса: HTTP-тесты не ходят в сеть."""

    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    async def get(self, city=None, refresh=False):
        self.calls.append((city, refresh))
        return self.payload


SEA_PAYLOAD = {
    "online": True,
    "updated_at": "2026-09-17T12:00:00+03:00",
    "warmest": {"id": "kerch", "name": "Керчь", "temp": 24},
    "points": [
        {
            "id": "yalta",
            "name": "Ялта",
            "available": True,
            "water_temp": 23,
            "wave_height": 0.3,
            "wave_label": "лёгкая рябь",
            "verdict": {
                "code": "comfort",
                "emoji": "🏊",
                "label": "купаться комфортно",
            },
        },
        {"id": "kerch", "name": "Керчь", "available": False},
    ],
}


def test_sea_endpoint_returns_bathing_verdicts(client, monkeypatch):
    fake = _FakeSea(SEA_PAYLOAD)
    monkeypatch.setattr(main, "sea_service", fake)
    r = client.get("/api/sea")
    assert r.status_code == 200
    d = r.json()
    assert d["online"] is True
    assert d["warmest"]["name"] == "Керчь"
    point = next(p for p in d["points"] if p["id"] == "yalta")
    assert point["verdict"]["code"] == "comfort"
    assert point["water_temp"] == 23
    assert fake.calls == [(None, False)]


def test_sea_city_filter_and_refresh_pass_through(client, monkeypatch):
    fake = _FakeSea({"online": True, "updated_at": "x", "warmest": None, "points": []})
    monkeypatch.setattr(main, "sea_service", fake)
    client.get("/api/sea?city=yalta&refresh=1")
    assert fake.calls == [("yalta", True)]


def test_sea_unknown_city_404(client):
    r = client.get("/api/sea?city=gotham")
    assert r.status_code == 404
    assert "морская точка" in r.json()["detail"]


def test_sea_inland_city_404_explains_why(client):
    """У Симферополя моря нет — 404 должен объяснять причину, а не
    притворяться, что города не существует."""
    r = client.get("/api/sea?city=simferopol")
    assert r.status_code == 404
    assert "без выхода к морю" in r.json()["detail"]


# ---------------- фронт, доступность, безопасность (0.12.0) ----------------


def _csp(client, path="/"):
    return client.get(path).headers.get("content-security-policy", "")


def test_csp_header_on_all_responses(client):
    for path in ("/", "/api/health", "/static/app.js", "/sw.js"):
        csp = _csp(client, path)
        assert "default-src 'self'" in csp, path
        assert "object-src 'none'" in csp, path


def test_csp_scripts_strict_no_unsafe_inline(client):
    csp = _csp(client)
    directives = [d.strip() for d in csp.split(";")]
    script_src = next(d for d in directives if d.startswith("script-src"))
    assert script_src == "script-src 'self'"
    style_src = next(d for d in directives if d.startswith("style-src"))
    assert "'unsafe-inline'" in style_src  # inline остаются только у стилей


def test_csp_frame_ancestors_default_self(client):
    assert "frame-ancestors 'self'" in _csp(client)


def test_index_has_open_graph_and_twitter_cards(client):
    html = client.get("/").text
    for needle in (
        'property="og:type" content="website"',
        'property="og:title"',
        'property="og:description"',
        'property="og:image"',
        'name="twitter:card" content="summary_large_image"',
        'name="twitter:image"',
    ):
        assert needle in html, needle


def test_index_og_urls_rendered_absolute(client):
    html = client.get("/").text
    assert "__ORIGIN__" not in html
    meta_re = r'<meta (?:property|name)="(og:[^"]+|twitter:[^"]+)" content="([^"]*)"'
    og = dict(re.findall(meta_re, html))
    assert og["og:image"].endswith("/static/img/hero.jpg")
    assert og["og:image"].startswith("http")
    assert og["og:url"].startswith("http")
    assert og["twitter:image"] == og["og:image"]


def test_index_og_honours_forwarded_headers(client):
    html = client.get(
        "/",
        headers={
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "gid.example.ru, proxy.internal",
        },
    ).text
    assert 'property="og:url" content="https://gid.example.ru/"' in html
    assert 'content="https://gid.example.ru/static/img/hero.jpg"' in html


def test_index_og_site_origin_env_wins_over_headers(client, monkeypatch):
    monkeypatch.setattr(main, "SITE_ORIGIN", "https://crimea.gid/")
    html = client.get("/", headers={"X-Forwarded-Host": "evil.example"}).text
    assert 'property="og:url" content="https://crimea.gid/"' in html


def test_index_a11y_landmarks_and_live_regions(client):
    html = client.get("/").text
    assert 'class="skip-link"' in html  # skip-link «к содержимому»
    assert 'id="toast-root" role="status" aria-live="polite"' in html
    assert 'id="route-status" class="sr-only" role="status"' in html
    assert '<nav class="nav" aria-label="Основные разделы">' in html
    assert '<main id="view" class="wrap" tabindex="-1">' in html


# ---------------- расширение каталога, фаза 1.0 ----------------


def test_catalog_grew_to_sixty(client):
    body = client.get("/api/attractions").json()
    assert body["count"] >= 60


def test_western_area_is_a_full_region_now(client):
    """Западный Крым дорос до самостоятельного направления: на него
    планировщик должен собирать полноценные дни, а не один заезд."""
    body = client.get("/api/attractions?area=" + urllib.parse.quote("Западный")).json()
    assert body["count"] >= 15
    ids = {a["id"] for a in body["items"]}
    assert {
        "belyaus",
        "donuzlav",
        "sasyk-sivash",
        "kenasy",
        "bakalskaya-kosa",
        "mezhvodnoe",
    } <= ids


def test_attraction_detail_exposes_opening_hours(client):
    body = client.get("/api/attractions/vorontsov").json()
    assert "hours" in body and ":" in body["hours"]
    # У природных точек графика нет — поле просто отсутствует.
    assert "hours" not in client.get("/api/attractions/fiolent").json()


def test_new_western_points_are_reachable_by_id(client):
    for pid in (
        "belyaus",
        "donuzlav",
        "sasyk-sivash",
        "okunevka",
        "krym-miniature",
        "kenasy",
        "mezhvodnoe",
        "bakalskaya-kosa",
    ):
        r = client.get(f"/api/attractions/{pid}")
        assert r.status_code == 200, pid
        body = r.json()
        assert body["area"] == "Западный"
        assert body["type_meta"]["img"], pid


def test_quiz_plans_a_western_trip(client):
    """Пляж + экстрим без машины на западе теперь даёт живой план."""
    r = client.post(
        "/api/quiz/evaluate",
        json={
            "purpose": ["beach", "extreme"],
            "season": "summer",
            "tempo": "medium",
            "budget": "economy",
            "party": "friends",
            "duration": "3-5",
            "transport": "car",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["itinerary"]["days"]
    picked = {a["id"] for a in body["recommendations"]}
    assert picked & {"belyaus", "donuzlav", "okunevka", "atlesh", "olenivka"}
