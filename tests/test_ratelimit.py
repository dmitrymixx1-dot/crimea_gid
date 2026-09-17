"""Ограничение частоты запросов: `app/ratelimit.py` и middleware 429.

Сеть не используется: сервисы новостей, погоды и моря подменяются
заглушками там, где тест доходит до самой ручки.
"""

import pytest
from starlette.datastructures import URL, Headers, QueryParams

from app import config, ratelimit


@pytest.fixture(autouse=True)
def _clean_limiter():
    """Счётчики — общие на процесс: между тестами их надо забывать."""
    ratelimit.limiter.reset()
    yield
    ratelimit.limiter.reset()


class Clock:
    """Ручные часы: окно лимита двигаем сами, не ждём секундами."""

    def __init__(self, start=1000.0):
        self.t = start

    def __call__(self):
        return self.t

    def tick(self, seconds):
        self.t += seconds


class FakeClient:
    def __init__(self, host):
        self.host = host


class FakeRequest:
    """Минимум, что нужно `match_rule` и `client_ip`."""

    def __init__(
        self,
        method="GET",
        path="/api/health",
        query="",
        headers=None,
        host="203.0.113.7",
    ):
        self.method = method
        self.url = URL(path + (f"?{query}" if query else ""))
        self.query_params = QueryParams(query)
        self.headers = Headers(headers or {})
        self.client = FakeClient(host)


class FakeService:
    """Сервис-заглушка: считает вызовы, в сеть не ходит."""

    def __init__(self, payload=None):
        self.calls = []
        self.payload = payload or {"online": True, "items": []}

    async def get(self, **kwargs):
        self.calls.append(kwargs)
        return self.payload


# ---------------- окно и счётчики ----------------


def test_allows_up_to_limit():
    clock = Clock()
    limiter = ratelimit.RateLimiter(now=clock)
    for expected in (2, 1, 0):
        decision = limiter.check("quiz:1.2.3.4", 3, 60)
        assert decision.allowed
        assert decision.remaining == expected
        assert decision.retry_after == 0
    assert len(limiter) == 1


def test_denies_over_limit_and_says_how_long_to_wait():
    clock = Clock()
    limiter = ratelimit.RateLimiter(now=clock)
    for _ in range(2):
        assert limiter.check("quiz:1.2.3.4", 2, 60).allowed
    clock.tick(10)
    denied = limiter.check("quiz:1.2.3.4", 2, 60)
    assert not denied.allowed
    assert denied.remaining == 0
    # Окно 60 с, первый запрос был 10 с назад — ждать 50 с.
    assert denied.retry_after == 50


def test_window_slides_requests_come_back():
    clock = Clock()
    limiter = ratelimit.RateLimiter(now=clock)
    assert limiter.check("k", 1, 60).allowed
    assert not limiter.check("k", 1, 60).allowed
    clock.tick(59)
    assert not limiter.check("k", 1, 60).allowed, "окно ещё не закрылось"
    clock.tick(1)
    assert limiter.check("k", 1, 60).allowed, "старый запрос вышел из окна"


def test_keys_are_independent():
    limiter = ratelimit.RateLimiter(now=Clock())
    assert limiter.check("quiz:1.1.1.1", 1, 60).allowed
    assert not limiter.check("quiz:1.1.1.1", 1, 60).allowed
    assert limiter.check("quiz:2.2.2.2", 1, 60).allowed


def test_zero_limit_disables_counting():
    limiter = ratelimit.RateLimiter(now=Clock())
    for _ in range(10):
        decision = limiter.check("k", 0, 60)
        assert decision.allowed
        assert decision.remaining == 0


def test_memory_is_bounded():
    clock = Clock()
    limiter = ratelimit.RateLimiter(now=clock, max_keys=3)
    for i in range(10):
        limiter.check(f"quiz:10.0.0.{i}", 5, 60)
    assert len(limiter) <= 3


def test_eviction_keeps_the_client_just_served():
    """Вытеснение не должно обнулять только что учтённый запрос."""
    clock = Clock()
    limiter = ratelimit.RateLimiter(now=clock, max_keys=2)
    limiter.check("quiz:10.0.0.1", 5, 60)
    limiter.check("quiz:10.0.0.2", 5, 60)
    decision = limiter.check("quiz:10.0.0.3", 5, 60)
    assert decision.allowed
    assert decision.remaining == 4, "свежий ключ не должен вытесняться собой"


def test_reset_forgets_counters():
    limiter = ratelimit.RateLimiter(now=Clock())
    assert limiter.check("k", 1, 60).allowed
    assert not limiter.check("k", 1, 60).allowed
    limiter.reset()
    assert len(limiter) == 0
    assert limiter.check("k", 1, 60).allowed


# ---------------- заголовки и текст ----------------


def test_headers_expose_limit_and_remaining():
    decision = ratelimit.Decision(True, 30, 12, 0, 40)
    assert ratelimit.headers(decision) == {
        "X-RateLimit-Limit": "30",
        "X-RateLimit-Remaining": "12",
        "X-RateLimit-Reset": "40",
    }


def test_detail_text_is_human():
    assert ratelimit.detail(5) == "слишком часто: попробуйте через 5 с"
    assert ratelimit.detail(120) == "слишком часто: попробуйте через 2 мин"


# ---------------- кто клиент и какие ручки дорогие ----------------


def test_client_ip_ignores_forwarded_header_by_default(monkeypatch):
    monkeypatch.setattr(config, "TRUST_PROXY", False)
    request = FakeRequest(headers={"x-forwarded-for": "9.9.9.9"})
    assert ratelimit.client_ip(request) == "203.0.113.7"


def test_client_ip_trusts_proxy_when_asked(monkeypatch):
    monkeypatch.setattr(config, "TRUST_PROXY", True)
    request = FakeRequest(headers={"x-forwarded-for": "9.9.9.9, 10.0.0.1"})
    assert ratelimit.client_ip(request) == "9.9.9.9"


def test_client_ip_falls_back_on_broken_header(monkeypatch):
    monkeypatch.setattr(config, "TRUST_PROXY", True)
    assert ratelimit.client_ip(FakeRequest(headers={"x-forwarded-for": ", ,"})) == (
        "203.0.113.7"
    )


def test_client_ip_without_socket():
    request = FakeRequest()
    request.client = None
    assert ratelimit.client_ip(request) == "unknown"


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_is_refresh_understands_truthy(value):
    assert ratelimit.is_refresh(FakeRequest(path="/api/news", query=f"refresh={value}"))


@pytest.mark.parametrize("value", ["", "0", "false", "no", "maybe", "-1"])
def test_is_refresh_rejects_the_rest(value):
    assert not ratelimit.is_refresh(
        FakeRequest(path="/api/news", query=f"refresh={value}")
    )


def test_match_rule_covers_expensive_routes():
    cases = [
        FakeRequest(method="POST", path="/api/quiz/evaluate"),
        FakeRequest(path="/api/news", query="refresh=1"),
        FakeRequest(path="/api/weather", query="refresh=1&city=yalta"),
        FakeRequest(path="/api/sea", query="refresh=1"),
    ]
    rules = [ratelimit.match_rule(r) for r in cases]
    assert all(rule is not None for rule in rules)
    assert {rule[0] for rule in rules} == {
        "quiz",
        "refresh:/api/news",
        "refresh:/api/weather",
        "refresh:/api/sea",
    }


def test_match_rule_ignores_the_rest():
    free = [
        FakeRequest(path="/api/health"),
        FakeRequest(path="/api/news", query="limit=5"),
        FakeRequest(path="/api/weather", query="city=yalta"),
        FakeRequest(path="/api/attractions", query="tag=wine"),
        FakeRequest(method="GET", path="/api/quiz/evaluate"),
        FakeRequest(method="POST", path="/api/quiz"),
    ]
    assert all(ratelimit.match_rule(r) is None for r in free)


# ---------------- middleware: 429 на живых ручках ----------------


@pytest.fixture()
def quiz_limit(monkeypatch):
    """Квиз: лимит 2 в минуту, сеть новостей не нужна."""
    monkeypatch.setattr(config, "RATE_LIMIT_QUIZ", 2)
    monkeypatch.setattr(config, "RATE_LIMIT_QUIZ_WINDOW", 60)
    news = FakeService({"items": [], "online": True})
    monkeypatch.setattr("app.main.news_service", news)
    return news


def test_quiz_evaluate_is_limited(client, quiz_limit, monkeypatch):
    payload = {"purpose": ["beach"], "season": "summer"}
    first = client.post("/api/quiz/evaluate", json=payload)
    assert first.status_code == 200
    assert first.headers["X-RateLimit-Limit"] == "2"
    assert first.headers["X-RateLimit-Remaining"] == "1"

    second = client.post("/api/quiz/evaluate", json=payload)
    assert second.status_code == 200
    assert second.headers["X-RateLimit-Remaining"] == "0"

    third = client.post("/api/quiz/evaluate", json=payload)
    assert third.status_code == 429
    assert third.headers["Retry-After"].isdigit()
    assert "через" in third.json()["detail"]
    assert third.headers["X-RateLimit-Remaining"] == "0"
    # До ручки запрос не дошёл: источники не дёргаем.
    assert len(quiz_limit.calls) == 2


def test_429_keeps_security_headers(client, quiz_limit):
    payload = {"purpose": ["beach"]}
    for _ in range(3):
        r = client.post("/api/quiz/evaluate", json=payload)
    assert r.status_code == 429
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert "Content-Security-Policy" in r.headers


SERVICE_BY_PATH = {
    "/api/news": "news_service",
    "/api/weather": "weather_service",
    "/api/sea": "sea_service",
}


@pytest.mark.parametrize("path", sorted(SERVICE_BY_PATH))
def test_refresh_is_limited_but_cache_hits_are_free(client, monkeypatch, path):
    monkeypatch.setattr(config, "RATE_LIMIT_REFRESH", 1)
    monkeypatch.setattr(config, "RATE_LIMIT_REFRESH_WINDOW", 300)
    service = FakeService()
    monkeypatch.setattr(f"app.main.{SERVICE_BY_PATH[path]}", service)

    assert client.get(f"{path}?refresh=1").status_code == 200
    limited = client.get(f"{path}?refresh=1")
    assert limited.status_code == 429
    assert len(service.calls) == 1

    # Без refresh ручка бесплатна: кэш и чтение каталога не считаем.
    for _ in range(5):
        assert client.get(path).status_code == 200


def test_cheap_routes_have_no_counters(client):
    r = client.get("/api/attractions?tag=wine")
    assert r.status_code == 200
    assert "X-RateLimit-Limit" not in r.headers
    assert "X-RateLimit-Limit" not in client.get("/api/health").headers


def test_limits_can_be_switched_off(client, monkeypatch, quiz_limit):
    monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", False)
    payload = {"purpose": ["beach"]}
    for _ in range(5):
        assert client.post("/api/quiz/evaluate", json=payload).status_code == 200


def test_clients_are_counted_separately(client, monkeypatch, quiz_limit):
    monkeypatch.setattr(config, "TRUST_PROXY", True)
    payload = {"purpose": ["beach"]}
    for _ in range(2):
        client.post(
            "/api/quiz/evaluate", json=payload, headers={"X-Forwarded-For": "1.1.1.1"}
        )
    blocked = client.post(
        "/api/quiz/evaluate", json=payload, headers={"X-Forwarded-For": "1.1.1.1"}
    )
    assert blocked.status_code == 429
    # Сосед за тем же прокси — другой клиент, его лимит цел.
    neighbour = client.post(
        "/api/quiz/evaluate", json=payload, headers={"X-Forwarded-For": "8.8.8.8"}
    )
    assert neighbour.status_code == 200
