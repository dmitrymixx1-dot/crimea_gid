"""Ограничение частоты запросов: `app/ratelimit.py` и middleware 429.

Сеть не используется: сервисы новостей, погоды и моря подменяются
заглушками там, где тест доходит до самой ручки.
"""

import logging

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


def test_headers_name_the_rule_but_do_not_invent_it():
    """Бюджетов больше одного: без имени правила клиент не понял бы,
    чей остаток он прочитал."""
    named = ratelimit.Decision(True, 6, 5, 0, 40, rule="news")
    assert ratelimit.headers(named)["X-RateLimit-Rule"] == "news"
    assert "X-RateLimit-Rule" not in ratelimit.headers(
        ratelimit.Decision(True, 6, 5, 0, 40)
    )


def test_decision_carries_the_rule_from_the_key():
    limiter = ratelimit.RateLimiter(now=Clock())
    assert limiter.check("news:1.1.1.1", 2, 60).rule == "news"
    assert limiter.check("quiz:1.1.1.1", 2, 60).rule == "quiz"


# ---------------- счётчики нагрузки ----------------


def test_stats_count_allowed_and_denied_per_rule():
    limiter = ratelimit.RateLimiter(now=Clock())
    limiter.check("news:1.1.1.1", 1, 60)
    limiter.check("news:1.1.1.1", 1, 60)  # отказ
    limiter.check("news:2.2.2.2", 1, 60)
    limiter.check("sea:2.2.2.2", 5, 60)
    assert limiter.stats() == {
        "news": {"allowed": 2, "denied": 1},
        "sea": {"allowed": 1, "denied": 0},
    }


def test_stats_survive_eviction_but_not_reset():
    """Вытеснение старых клиентов не должно обнулять нагрузку: иначе
    на общем NAT статистика обнулялась бы сама собой."""
    limiter = ratelimit.RateLimiter(now=Clock(), max_keys=2)
    for i in range(5):
        limiter.check(f"news:10.0.0.{i}", 5, 60)
    assert limiter.stats()["news"]["allowed"] == 5
    limiter.reset()
    assert limiter.stats() == {}


def test_stats_count_requests_when_budget_is_switched_off():
    """`RATE_LIMIT_NEWS=0` — бюджет выключен: запросы идут и считаются."""
    limiter = ratelimit.RateLimiter(now=Clock())
    for _ in range(3):
        assert limiter.check("news:1.1.1.1", 0, 60).allowed
    assert limiter.stats() == {"news": {"allowed": 3, "denied": 0}}


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
    assert {rule.name for rule in rules} == {"quiz", "news", "weather", "sea"}
    assert {rule.path for rule in rules} == {
        "/api/quiz/evaluate",
        "/api/news",
        "/api/weather",
        "/api/sea",
    }
    # У каждой ручки пара «лимит/окно» своя: общее число на всех было
    # ровно тем, что эта фаза и убирает.
    assert len({(rule.limit, rule.window) for rule in rules}) == 4


def test_rules_read_budgets_from_config_at_call_time(monkeypatch):
    """Правило не кэширует значения: env-переопределение (и подмена
    в тестах) обязано быть видно сразу."""
    monkeypatch.setattr(config, "RATE_LIMIT_NEWS", 11)
    monkeypatch.setattr(config, "RATE_LIMIT_NEWS_WINDOW", 42)
    monkeypatch.setattr(config, "RATE_LIMIT_WEATHER", 7)
    monkeypatch.setattr(config, "RATE_LIMIT_WEATHER_WINDOW", 900)
    monkeypatch.setattr(config, "RATE_LIMIT_SEA", 2)
    monkeypatch.setattr(config, "RATE_LIMIT_SEA_WINDOW", 1800)
    monkeypatch.setattr(config, "RATE_LIMIT_QUIZ", 5)
    monkeypatch.setattr(config, "RATE_LIMIT_QUIZ_WINDOW", 30)
    budgets = {rule.name: (rule.limit, rule.window) for rule in ratelimit.rules()}
    assert budgets == {
        "quiz": (5, 30),
        "news": (11, 42),
        "weather": (7, 900),
        "sea": (2, 1800),
    }


def test_rules_describe_themselves_for_the_limits_endpoint():
    rows = {rule.name: rule.as_dict() for rule in ratelimit.rules()}
    assert rows["quiz"] == {
        "name": "quiz",
        "method": "POST",
        "path": "/api/quiz/evaluate",
        "limit": config.RATE_LIMIT_QUIZ,
        "window": config.RATE_LIMIT_QUIZ_WINDOW,
        "hint": rows["quiz"]["hint"],
    }
    # Подсказка — не пустая строка: она объясняет, откуда взялся бюджет.
    assert all(row["hint"] for row in rows.values())
    assert rows["news"]["path"] == "/api/news"


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

# Бюджет каждой refresh-ручки: имя правила, переменные лимита и окна.
BUDGET_BY_PATH = {
    "/api/news": ("news", "RATE_LIMIT_NEWS", "RATE_LIMIT_NEWS_WINDOW"),
    "/api/weather": ("weather", "RATE_LIMIT_WEATHER", "RATE_LIMIT_WEATHER_WINDOW"),
    "/api/sea": ("sea", "RATE_LIMIT_SEA", "RATE_LIMIT_SEA_WINDOW"),
}


@pytest.mark.parametrize("path", sorted(SERVICE_BY_PATH))
def test_refresh_is_limited_but_cache_hits_are_free(client, monkeypatch, path):
    name, limit_var, window_var = BUDGET_BY_PATH[path]
    monkeypatch.setattr(config, limit_var, 1)
    monkeypatch.setattr(config, window_var, 300)
    service = FakeService()
    monkeypatch.setattr(f"app.main.{SERVICE_BY_PATH[path]}", service)

    first = client.get(f"{path}?refresh=1")
    assert first.status_code == 200
    # Заголовки называют правило: без этого клиент не отличил бы бюджеты.
    assert first.headers["X-RateLimit-Rule"] == name
    assert first.headers["X-RateLimit-Limit"] == "1"

    limited = client.get(f"{path}?refresh=1")
    assert limited.status_code == 429
    assert limited.headers["X-RateLimit-Rule"] == name
    assert len(service.calls) == 1

    # Без refresh ручка бесплатна: кэш и чтение каталога не считаем.
    for _ in range(5):
        assert client.get(path).status_code == 200


def test_budgets_are_spent_apart_from_each_other(client, monkeypatch):
    """Ради этого фаза и делалась: исчерпанная лента больше не занимает
    бюджет у погоды и моря — у каждой ручки своё окно."""
    monkeypatch.setattr(config, "RATE_LIMIT_NEWS", 1)
    monkeypatch.setattr(config, "RATE_LIMIT_NEWS_WINDOW", 300)
    monkeypatch.setattr(config, "RATE_LIMIT_WEATHER", 2)
    monkeypatch.setattr(config, "RATE_LIMIT_WEATHER_WINDOW", 900)
    monkeypatch.setattr(config, "RATE_LIMIT_SEA", 1)
    monkeypatch.setattr(config, "RATE_LIMIT_SEA_WINDOW", 1800)
    for attr in SERVICE_BY_PATH.values():
        monkeypatch.setattr(f"app.main.{attr}", FakeService())

    assert client.get("/api/news?refresh=1").status_code == 200
    assert client.get("/api/news?refresh=1").status_code == 429, "лента кончилась"

    # Чужой исчерпанный бюджет погоде не мешает и считается по своему окну.
    assert client.get("/api/weather?refresh=1").status_code == 200
    assert client.get("/api/weather?refresh=1").status_code == 200
    assert client.get("/api/weather?refresh=1").status_code == 429
    assert client.get("/api/sea?refresh=1").status_code == 200


def test_429_is_logged_for_the_operator(client, quiz_limit, caplog):
    """Строка на отказ — та самая «статистика нагрузки» из docker logs,
    по которой потом настраивают бюджеты."""
    payload = {"purpose": ["beach"]}
    with caplog.at_level(logging.WARNING, logger="crimea_gid.ratelimit"):
        for _ in range(3):
            client.post("/api/quiz/evaluate", json=payload)
    assert "429 quiz" in caplog.text
    # Адрес клиента в логе есть — иначе непонятно, кого именно ограничили.
    assert "testclient" in caplog.text


# ---------------- GET /api/limits ----------------


def test_limits_endpoint_tells_budgets_and_is_free(client):
    r = client.get("/api/limits")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True
    names = {rule["name"] for rule in body["rules"]}
    assert names == {"quiz", "news", "weather", "sea"}
    quiz = next(rule for rule in body["rules"] if rule["name"] == "quiz")
    assert quiz["method"] == "POST" and quiz["path"] == "/api/quiz/evaluate"
    assert quiz["limit"] == config.RATE_LIMIT_QUIZ
    assert quiz["window"] == config.RATE_LIMIT_QUIZ_WINDOW
    # Ручка бесплатная: узнать бюджет не значит потратить его.
    assert "X-RateLimit-Limit" not in r.headers


def test_limits_endpoint_shows_the_load_of_this_process(client, quiz_limit):
    payload = {"purpose": ["beach"]}
    for _ in range(3):
        client.post("/api/quiz/evaluate", json=payload)
    body = client.get("/api/limits").json()
    assert body["stats"] == {"quiz": {"allowed": 2, "denied": 1}}
    assert body["clients"] == 1


def test_limits_endpoint_reports_disabled_limits(client, monkeypatch):
    monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", False)
    body = client.get("/api/limits").json()
    assert body["enabled"] is False
    # Таблица бюджетов остаётся: видно, что именно выключено.
    assert len(body["rules"]) == 4


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
