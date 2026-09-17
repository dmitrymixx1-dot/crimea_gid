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

Бюджет у каждой ручки **свой** (`rules()`): лента, погода и море стоят
по-разному, и общее число на всех заставляло равняться на самую дорогую.
Сколько запросов пустили и сколько отбили — видно в `stats()`
и в `GET /api/limits`: настраивать бюджет вслепую нельзя.
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
# Имя правила: у каждой ручки свой бюджет, и клиенту нужно знать, чей он
# прочитал (иначе остаток лимита квиза лёг бы на кнопку «Обновить» ленты).
HEADER_RULE = "X-RateLimit-Rule"

# Что считаем «правдой» в refresh: то же, что понимает FastAPI.
_TRUTHY = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Rule:
    """Бюджет одной ручки.

    `name` — короткое имя правила: из него собирается ключ счётчика
    (`news:203.0.113.7`), по нему же сходятся счётчики в `stats()`
    и строка правила в `GET /api/limits`. Отсюда требование — без `:`.
    """

    name: str
    method: str
    path: str
    limit: int
    window: int
    hint: str = ""
    # Дорогая не вся ручка, а только `?refresh=1`: обычное чтение — из кэша
    # и бесплатно.
    refresh_only: bool = False

    def as_dict(self) -> dict[str, object]:
        """Строка для `GET /api/limits` — тот же факт, что в докладе."""
        return {
            "name": self.name,
            "method": self.method,
            "path": self.path,
            "limit": self.limit,
            "window": self.window,
            "hint": self.hint,
        }


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
    # Имя правила, к которому относится бюджет; пусто — у решения нет
    # правила (например, собранное вручную в тестах).
    rule: str = ""


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
        self._stats: dict[str, dict[str, int]] = {}

    def check(self, key: str, limit: int, window: float) -> Decision:
        """Учесть запрос и вернуть решение.

        `limit <= 0` или `window <= 0` — лимит выключен значением:
        пускаем всех, но честно сообщаем лимит в заголовках.

        Ключ обязан начинаться с имени правила (`news:203.0.113.7`) —
        по этому префиксу ведутся счётчики нагрузки.
        """
        rule = key.split(":", 1)[0]
        now = self._now()
        if limit <= 0 or window <= 0:
            self._count(rule, allowed=True)
            return Decision(True, max(limit, 0), max(limit, 0), 0, 0, rule=rule)

        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] >= window:
            hits.popleft()
        self._seen[key] = now

        allowed = len(hits) < limit
        if allowed:
            hits.append(now)
        self._count(rule, allowed)
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
            rule=rule,
        )

    def stats(self) -> dict[str, dict[str, int]]:
        """Сколько запросов к каждой ручке пустили и сколько отбили.

        Метрик и БД у проекта нет, а бюджет нужно настраивать по факту,
        а не на глаз: эти числа отдаёт `GET /api/limits`. Счётчики
        складываются по всем клиентам — адреса наружу не уходят.
        """
        return {
            rule: {"allowed": c["allowed"], "denied": c["denied"]}
            for rule, c in sorted(self._stats.items())
        }

    def reset(self) -> None:
        """Забыть все счётчики (тесты, «разогнать» лимит вручную)."""
        self._hits.clear()
        self._seen.clear()
        self._stats.clear()

    def __len__(self) -> int:
        return len(self._hits)

    def _count(self, rule: str, allowed: bool) -> None:
        entry = self._stats.setdefault(rule, {"allowed": 0, "denied": 0})
        entry["allowed" if allowed else "denied"] += 1

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


def rules() -> list[Rule]:
    """Бюджеты всех дорогих ручек — на момент вызова.

    Значения читаются из `config` каждый раз, а не один раз при импорте:
    тесты и `--reload` подменяют переменные окружения, и правило обязано
    видеть новое значение. Этот же список — источник правды для
    `GET /api/limits` и для таблицы в [docs/api.md](../docs/api.md).
    """
    return [
        Rule(
            name="quiz",
            method="POST",
            path="/api/quiz/evaluate",
            limit=config.RATE_LIMIT_QUIZ,
            window=config.RATE_LIMIT_QUIZ_WINDOW,
            hint="оценка перебирает весь каталог",
        ),
        Rule(
            name="news",
            method="GET",
            path="/api/news",
            limit=config.RATE_LIMIT_NEWS,
            window=config.RATE_LIMIT_NEWS_WINDOW,
            hint="11 источников на запрос, кнопка «Обновить» у человека",
            refresh_only=True,
        ),
        Rule(
            name="weather",
            method="GET",
            path="/api/weather",
            limit=config.RATE_LIMIT_WEATHER,
            window=config.RATE_LIMIT_WEATHER_WINDOW,
            hint="18 городов на запрос, модель обновляется раз в час",
            refresh_only=True,
        ),
        Rule(
            name="sea",
            method="GET",
            path="/api/sea",
            limit=config.RATE_LIMIT_SEA,
            window=config.RATE_LIMIT_SEA_WINDOW,
            hint="15 точек на запрос, волновую модель обновляют раз в 12 часов",
            refresh_only=True,
        ),
    ]


def match_rule(request) -> Rule | None:
    """Правило для запроса или `None`, если ручка не лимитируется."""
    path = request.url.path
    for rule in rules():
        if request.method != rule.method or path != rule.path:
            continue
        if rule.refresh_only and not is_refresh(request):
            return None  # обычное чтение — из кэша и бесплатно
        return rule
    return None


def headers(decision: Decision) -> dict[str, str]:
    """Заголовки лимита: их видно и на успехе, и на 429.

    `X-RateLimit-Rule` называет бюджет, к которому относятся числа, —
    без него клиент не отличил бы остаток ленты от остатка квиза.
    """
    out = {
        HEADER_LIMIT: str(decision.limit),
        HEADER_REMAINING: str(decision.remaining),
        HEADER_RESET: str(decision.reset),
    }
    if decision.rule:
        out[HEADER_RULE] = decision.rule
    return out


def detail(retry_after: int) -> str:
    """Текст `detail` для 429: человеку важно знать, сколько ждать."""
    if retry_after >= 60:
        minutes = math.ceil(retry_after / 60)
        return f"слишком часто: попробуйте через {minutes} мин"
    return f"слишком часто: попробуйте через {retry_after} с"
