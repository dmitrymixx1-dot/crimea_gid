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

Поверх раздельных бюджетов лежит **общий бюджет клиента** (`total_rule()`):
ручка защищена своим окном, а процесс — нет, и клиент, который берёт
«по чуть-чуть» с каждой ручки, в сумме нагружает сервер заметно. Один
запрос считается в обоих счётчиках сразу (`reserve()`), и решение
принимает самый тесный из них: отказ общего бюджета не съедает слот ручки,
потому что запрос в этом случае не проходит вовсе.
"""

from __future__ import annotations

import math
import time
from collections import deque
from collections.abc import Collection
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
# Общий бюджет клиента: он один на все ручки, поэтому живёт в своих
# заголовках — иначе «остаток» ленты и потолка процесса смешались бы.
HEADER_TOTAL_LIMIT = "X-RateLimit-Total-Limit"
HEADER_TOTAL_REMAINING = "X-RateLimit-Total-Remaining"
HEADER_TOTAL_RESET = "X-RateLimit-Total-Reset"
# Имя общего счётчика: он не привязан к ручке, поэтому и в `stats()`,
# и в `X-RateLimit-Rule` (когда отказал именно он) виден отдельно.
TOTAL = "total"

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
class Budget:
    """Один счётчик: ключ, лимит и окно.

    Запрос может стоить сразу в нескольких (`check_rule()` — ручка плюс
    общий потолок клиента), поэтому `reserve()` принимает список бюджетов
    и решает по самому тесному.
    """

    key: str
    limit: int
    window: float

    @property
    def rule(self) -> str:
        """Имя правила из префикса ключа (`news:203.0.113.7` → `news`)."""
        return self.key.split(":", 1)[0]

    @property
    def enabled(self) -> bool:
        """`limit <= 0` или `window <= 0` — счётчик выключен значением."""
        return self.limit > 0 and self.window > 0


@dataclass(frozen=True)
class Decision:
    """Результат проверки: пустить запрос или нет.

    `retry_after` — секунд до освобождения слота (0, если пустили);
    `reset` — секунд до полного очищения окна; `window` — длина окна
    (по ней строка отказа в логе называет бюджет целиком).

    Когда запрос считался в нескольких бюджетах сразу (`reserve`),
    `allowed` — общий исход запроса, а `retry_after > 0` стоит только
    у того бюджета, который и стал причиной отказа: по нему
    `Verdict.binding` понимает, чьи числа показывать клиенту.
    """

    allowed: bool
    limit: int
    remaining: int
    retry_after: int
    reset: int
    # Имя правила, к которому относится бюджет; пусто — у решения нет
    # правила (например, собранное вручную в тестах).
    rule: str = ""
    # Длина окна в секундах: она нужна строке отказа в логе (по ней
    # оператор понимает, какое именно окно закрылось).
    window: int = 0


@dataclass(frozen=True)
class Verdict:
    """Итог по одному запросу: бюджет ручки плюс общий потолок клиента.

    Общий потолок может быть выключен значением — тогда `total` пуст,
    и заголовки про него не появляются.
    """

    rule: Decision
    total: Decision | None = None

    @property
    def allowed(self) -> bool:
        return self.rule.allowed

    @property
    def refused(self) -> list[Decision]:
        """Бюджеты, которые отказали сами (у них и стоит `retry_after`)."""
        return [d for d in (self.rule, self.total) if d is not None and d.retry_after]

    @property
    def binding(self) -> Decision:
        """Чей бюджет показывать в основных заголовках.

        На успехе — бюджет ручки (клиенту интересен остаток своей ручки,
        а не общий потолок). На отказе — тот, кто держит дольше всех:
        `Retry-After` обязан покрывать каждый отказ, иначе клиент
        вернулся бы ровно за следующим `429`.
        """
        refused = self.refused
        if not refused:
            return self.rule
        return max(refused, key=lambda d: d.retry_after)


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
        """Учесть запрос в одном бюджете и вернуть решение (частный случай
        `reserve`).

        `limit <= 0` или `window <= 0` — лимит выключен значением:
        пускаем всех, но честно сообщаем лимит в заголовках.

        Ключ обязан начинаться с имени правила (`news:203.0.113.7`) —
        по этому префиксу ведутся счётчики нагрузки.
        """
        return self.reserve([Budget(key, limit, window)])[0]

    def reserve(self, budgets: list[Budget]) -> list[Decision]:
        """Учесть один запрос сразу в нескольких бюджетах.

        Так работает общий потолок клиента: запрос стоит и в окне ручки,
        и в окне клиента. Решение одно на все — если хоть один бюджет
        отказал, запрос не проходит, и **ни один** счётчик не тратится:
        иначе отказ общего потолка съедал бы слот ручки, а данных клиент
        не получил бы. `retry_after` стоит только у бюджета, который и
        стал причиной отказа: ждать открытия чужого окна смысла нет, по
        нему же middleware понимает, чей бюджет показывать в заголовках.

        Счётчики нагрузки: пущенный запрос пишут всем участникам, отказ —
        только тому бюджету, который отказал (иначе `denied` у ленты
        объяснял бы оператору чужой потолок).

        Порядок результата — порядок бюджетов на входе.
        """
        now = self._now()
        # `hits is None` — бюджет выключен значением: счётчика у него нет.
        states: list[tuple[int, Budget, deque[float] | None, bool]] = []
        for index, budget in enumerate(budgets):
            if not budget.enabled:
                states.append((index, budget, None, True))
                continue
            hits = self._hits.setdefault(budget.key, deque())
            while hits and now - hits[0] >= budget.window:
                hits.popleft()
            self._seen[budget.key] = now
            states.append((index, budget, hits, len(hits) < budget.limit))

        passed = all(own for _, _, _, own in states)
        if passed:
            for _, _, hits, _ in states:
                if hits is not None:
                    hits.append(now)

        decisions: list[Decision | None] = [None] * len(budgets)
        for index, budget, hits, own in states:
            if hits is None:
                # Выключенный бюджет запрос не ограничивает, но и в нагрузку
                # пишется, только если запрос действительно прошёл.
                if passed:
                    self._count(budget.rule, allowed=True)
                decisions[index] = Decision(
                    allowed=passed,
                    limit=max(budget.limit, 0),
                    remaining=max(budget.limit, 0),
                    retry_after=0,
                    reset=0,
                    rule=budget.rule,
                    window=max(int(budget.window), 0),
                )
                continue
            reset = (
                max(1, math.ceil(budget.window - (now - hits[0])))
                if hits
                else max(1, int(budget.window))
            )
            if passed:
                self._count(budget.rule, allowed=True)
            elif not own:
                self._count(budget.rule, allowed=False)
            decisions[index] = Decision(
                allowed=passed,
                limit=budget.limit,
                remaining=max(0, budget.limit - len(hits)),
                retry_after=0 if passed or own else reset,
                reset=reset,
                rule=budget.rule,
                window=int(budget.window),
            )

        self._evict(
            now, keep=[budget.key for _, budget, hits, _ in states if hits is not None]
        )
        return [decision for decision in decisions if decision is not None]

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

    def clients(self) -> int:
        """Сколько разных клиентов сейчас в памяти лимитера.

        Ключей больше, чем клиентов: на одного приходится по счётчику на
        каждую тронутую ручку плюс общий потолок. Наружу
        (`GET /api/limits`) идёт число клиентов — сами адреса не отдаём,
        считаем только разные хвосты ключей.
        """
        return len({key.split(":", 1)[1] for key in self._hits if ":" in key})

    def __len__(self) -> int:
        """Сколько счётчиков в памяти: ими ограничен `RATE_LIMIT_MAX_KEYS`."""
        return len(self._hits)

    def _count(self, rule: str, allowed: bool) -> None:
        entry = self._stats.setdefault(rule, {"allowed": 0, "denied": 0})
        entry["allowed" if allowed else "denied"] += 1

    def _evict(self, now: float, keep: Collection[str]) -> None:
        """Держать не больше `max_keys` счётчиков: сначала выбрасываем
        опустевшие окна, потом — самых давних. `keep` — ключи текущего
        запроса (их несколько, когда работает общий потолок клиента)."""
        if len(self._hits) <= self._max_keys:
            return
        for key in [k for k, h in self._hits.items() if not h]:
            self._drop(key)
        overflow = len(self._hits) - self._max_keys
        if overflow <= 0:
            return
        oldest = sorted(self._seen.items(), key=lambda kv: kv[1])
        for key, _ in oldest[:overflow]:
            if key not in keep:
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


def total_rule() -> Rule | None:
    """Общий бюджет клиента поверх бюджетов ручек.

    От правила ручки он отличается тем, что не привязан к маршруту
    (`method`/`path` — «любые»): в `match_rule()` это правило не
    участвует, иначе лимитировался бы весь сайт вместе с каталогом
    и статикой. `None` — потолок выключен значением (`RATE_LIMIT_TOTAL=0`),
    и тогда остаются только бюджеты ручек.
    """
    if config.RATE_LIMIT_TOTAL <= 0 or config.RATE_LIMIT_TOTAL_WINDOW <= 0:
        return None
    return Rule(
        name=TOTAL,
        method="*",
        path="*",
        limit=config.RATE_LIMIT_TOTAL,
        window=config.RATE_LIMIT_TOTAL_WINDOW,
        hint="потолок на клиента поверх бюджетов ручек: все дорогие запросы",
    )


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


def check_rule(rule: Rule, ip: str) -> Verdict:
    """Учесть запрос в бюджете ручки и в общем потолке клиента.

    Раздельные окна защищают ручку, но не процесс: «по чуть-чуть» с каждой
    ручки в сумме даёт заметную нагрузку. Поэтому один запрос стоит в двух
    счётчиках сразу, а проходит только если место есть в обоих.
    """
    budgets = [Budget(f"{rule.name}:{ip}", rule.limit, rule.window)]
    total = total_rule()
    if total is not None:
        budgets.append(Budget(f"{total.name}:{ip}", total.limit, total.window))
    decisions = limiter.reserve(budgets)
    return Verdict(rule=decisions[0], total=decisions[1] if total else None)


def headers(decision: Decision) -> dict[str, str]:
    """Заголовки лимита: их видно и на успехе, и на 429.

    `X-RateLimit-Rule` называет бюджет, к которому относятся числа, —
    без него клиент не отличил бы остаток ленты от остатка квиза
    (или от общего потолка клиента, когда отказал он).
    """
    out = {
        HEADER_LIMIT: str(decision.limit),
        HEADER_REMAINING: str(decision.remaining),
        HEADER_RESET: str(decision.reset),
    }
    if decision.rule:
        out[HEADER_RULE] = decision.rule
    return out


def total_headers(total: Decision | None) -> dict[str, str]:
    """Заголовки общего потолка клиента (пусто, если он выключен).

    Отдельные имена — не замена основным: у ручки и у потолка разные
    окна, и смешать их в одной тройке чисел значит соврать клиенту.
    """
    if total is None or total.limit <= 0:
        return {}
    return {
        HEADER_TOTAL_LIMIT: str(total.limit),
        HEADER_TOTAL_REMAINING: str(total.remaining),
        HEADER_TOTAL_RESET: str(total.reset),
    }


def detail(retry_after: int) -> str:
    """Текст `detail` для 429: человеку важно знать, сколько ждать."""
    if retry_after >= 60:
        minutes = math.ceil(retry_after / 60)
        return f"слишком часто: попробуйте через {minutes} мин"
    return f"слишком часто: попробуйте через {retry_after} с"
