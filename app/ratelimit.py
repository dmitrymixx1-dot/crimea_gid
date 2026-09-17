"""Ограничение частоты запросов к дорогим ручкам.

Счётчики живут в памяти процесса: базы и внешних сервисов у проекта нет
(см. [docs/architecture.md](../docs/architecture.md)), а задача узкая —
закрыть квиз и принудительное обновление ленты/погоды/моря от петель
в браузере и слишком усердных клиентов. Рестарт счётчики обнуляет;
для защиты этого уровня это допустимая цена.

Окно **скользящее** (журнал времён запросов), а не фиксированное: на
границе окна клиент не получает «внезапный» второй лимит подряд.

Лимитируются только дорогие ручки — остальные (каталог, health, статика)
ходят без счётчиков, чтобы не наказывать обычный просмотр.
"""

from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass

from . import config

# Заголовки ответа: де-факто стандарт X-RateLimit-* плюс Retry-After,
# который понимают и браузеры, и curl.
HEADER_LIMIT = "X-RateLimit-Limit"
HEADER_REMAINING = "X-RateLimit-Remaining"
HEADER_RESET = "X-RateLimit-Reset"
HEADER_RETRY_AFTER = "Retry-After"

# Ручки, у которых `refresh=1` означает поход в сеть (и только он).
REFRESH_PATHS = ("/api/news", "/api/weather", "/api/sea")

# Что считаем «правдой» в refresh: то же, что понимает FastAPI.
_TRUTHY = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Decision:
    """Результат проверки: пустить запрос или нет.

    `retry_after` — секунд до освобождения слота (0, если пустили);
    `reset` — секунд до полного очищения окна.
    """

    allowed: bool
    limit: int
    remaining: int
    retry_after: int
    reset: int


class RateLimiter:
    """Скользящее окно на ключ (обычно «ручка:адрес клиента»).

    Блокировки не нужны: uvicorn крутит корутины в одном потоке событий,
    а обращение к словарю — атомарная для интерпретатора операция.
    """

    def __init__(self, now=time.monotonic, max_keys: int | None = None) -> None:
        self._now = now
        self._max_keys = config.RATE_LIMIT_MAX_KEYS if max_keys is None else max_keys
        self._hits: dict[str, deque[float]] = {}
        self._seen: dict[str, float] = {}

    def check(self, key: str, limit: int, window: float) -> Decision:
        """Учесть запрос и вернуть решение.

        `limit <= 0` или `window <= 0` — лимит выключен значением:
        пускаем всех, но честно сообщаем лимит в заголовках.
        """
        now = self._now()
        if limit <= 0 or window <= 0:
            return Decision(True, max(limit, 0), max(limit, 0), 0, 0)

        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] >= window:
            hits.popleft()
        self._seen[key] = now

        allowed = len(hits) < limit
        if allowed:
            hits.append(now)
        reset = (
            max(1, math.ceil(window - (now - hits[0]))) if hits else max(1, int(window))
        )
        self._evict(now, keep=key)
        return Decision(
            allowed=allowed,
            limit=limit,
            remaining=max(0, limit - len(hits)),
            retry_after=0 if allowed else reset,
            reset=reset,
        )

    def reset(self) -> None:
        """Забыть все счётчики (тесты, «разогнать» лимит вручную)."""
        self._hits.clear()
        self._seen.clear()

    def __len__(self) -> int:
        return len(self._hits)

    def _evict(self, now: float, keep: str) -> None:
        """Держать не больше `max_keys` клиентов: сначала выбрасываем
        опустевшие окна, потом — самых давних."""
        if len(self._hits) <= self._max_keys:
            return
        for key in [k for k, h in self._hits.items() if not h]:
            self._drop(key)
        overflow = len(self._hits) - self._max_keys
        if overflow <= 0:
            return
        oldest = sorted(self._seen.items(), key=lambda kv: kv[1])
        for key, _ in oldest[:overflow]:
            if key != keep:
                self._drop(key)

    def _drop(self, key: str) -> None:
        self._hits.pop(key, None)
        self._seen.pop(key, None)


# Один Limiter на процесс: счётчики общие для всех воркеров uvicorn,
# пока он запущен в один процесс (штатный режим — см. docs/deploy.md).
limiter = RateLimiter()


def client_ip(request) -> str:
    """Кого считаем клиентом.

    За своим прокси (Caddy из compose) адрес соединения — сам прокси,
    поэтому берём первый адрес из `X-Forwarded-For`. Чужому клиенту
    заголовок верить нельзя — он подделывается одной строкой, поэтому
    по умолчанию (`TRUST_PROXY=0`) считаем адрес соединения.
    """
    if config.TRUST_PROXY:
        first = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if first:
            return first
    client = getattr(request, "client", None)
    return client.host if client and client.host else "unknown"


def is_refresh(request) -> bool:
    """`refresh=1` — то же понимание «правды», что у параметров FastAPI."""
    return request.query_params.get("refresh", "").strip().lower() in _TRUTHY


def match_rule(request) -> tuple[str, int, int] | None:
    """Правило для запроса: `(имя, лимит, окно в секундах)` или `None`,
    если ручка не лимитируется."""
    path = request.url.path
    if request.method == "POST" and path == "/api/quiz/evaluate":
        return "quiz", config.RATE_LIMIT_QUIZ, config.RATE_LIMIT_QUIZ_WINDOW
    if request.method == "GET" and path in REFRESH_PATHS and is_refresh(request):
        return (
            f"refresh:{path}",
            config.RATE_LIMIT_REFRESH,
            config.RATE_LIMIT_REFRESH_WINDOW,
        )
    return None


def headers(decision: Decision) -> dict[str, str]:
    """Заголовки лимита: их видно и на успехе, и на 429."""
    return {
        HEADER_LIMIT: str(decision.limit),
        HEADER_REMAINING: str(decision.remaining),
        HEADER_RESET: str(decision.reset),
    }


def detail(retry_after: int) -> str:
    """Текст `detail` для 429: человеку важно знать, сколько ждать."""
    if retry_after >= 60:
        minutes = math.ceil(retry_after / 60)
        return f"слишком часто: попробуйте через {minutes} мин"
    return f"слишком часто: попробуйте через {retry_after} с"
