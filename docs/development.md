# Для разработчика

## Окружение

Требования: **Python 3.11+**; опционально Node.js (проверка синтаксиса JS)
и Docker.

```bash
git clone <repo> && cd crimea_gid
./run.sh          # поднимет venv, поставит зависимости, запустит dev-сервер
# или вручную:
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt   # рантайм + pytest, ruff, PyYAML
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Приложение: `http://localhost:8000` (OpenAPI — `/docs`).

## Тесты

```bash
.venv/bin/python -m pytest tests/ -q        # весь свит
.venv/bin/python -m pytest tests/test_news.py -q   # один модуль
.venv/bin/python -m pytest tests/ -k weather -q    # по имени
node --test "tests/js/*.test.js"            # JS-тесты модулей фронта (node:test)
for f in static/*.js; do node --check "$f"; done   # синтаксис всех модулей
.venv/bin/ruff check app tests              # линтер
```

**439 Python-тестов**, сеть не используется (все внешние вызовы заглушены),
плюс **143 JS-тест** (`tests/js/`, `node:test` без зависимостей):

| Модуль | Что покрывает |
|---|---|
| `test_api.py` | эндпоинты, фильтры (в т.ч. `tag=extreme`, `area=Западный`), заголовки безопасности и CSP, рендер Open Graph (origin из env/`X-Forwarded-*`), a11y-каркас, PWA-маршруты, контракт 422 (квиз) / 404 (погода), машинная `price` в каталоге |
| `test_ratelimit.py` | лимиты: скользящее окно и `Retry-After`, заголовки `X-RateLimit-*` и имя правила, `429` на квизе и `?refresh=1`, **раздельные бюджеты ручек** (исчерпанная лента не занимает бюджет погоды), **общий потолок клиента** (`reserve`: запрос стоит в двух счётчиках, отказ потолка не тратит слот ручки, `Retry-After` покрывает оба окна, `X-RateLimit-Total-*`), счётчики нагрузки и `GET /api/limits`, строка в логе на каждый отказ, бесплатность обычного чтения, раздельный счёт клиентов по `X-Forwarded-For` (`TRUST_PROXY`) |
| `test_assets.py` | аудит статики: бюджет веса и размеры картинок, отсутствие inline-обработчиков и пустых `alt`, внешние `<script>`, согласованность SW/манифеста, прод-конфигурация (`docker-compose.yml`, `Caddyfile`, скрипты бэкапа), автодеплой и **репетиция выката** (`deploy.sh --dry-run` запускается по-настоящему: без сервера, Docker и сети) |
| `test_data.py` | схемы данных, границы координат, **якорные координаты** (`ANCHORS` — сверено с OSM), объём каталога и покрытие районов, согласованность каталога/квиза со словарями кода и `QuizIn`, покрытие всех `TAGS` в `quiz.purpose`/`PROFILES`/`PURPOSE_TOPICS`, **цена `price` и уровень `budget` выводятся из `price_hint`** (двусторонняя сверка, пороги квиза, непустая шкала), источники, файлы картинок типов |
| `test_load.py` | загрузчик JSON: схемы, кэширование, ошибка на отсутствующий файл |
| `test_config.py` | формат версии, **согласованность версий** (код/README/SW/доки), дефолты, переопределение через env, пути |
| `test_recommends.py` | матчинг (`_score_attraction` по факторам), профили, фильтры новостей, планировщик (слоты, районы, лимиты, запас), **бюджет как ответ квиза**: эконом платит за вход, премиум поднимает дорогие впечатления, каждый ответ меняет подборку и оставляет её непустой |
| `test_news.py` | скоринг «Крым», темы, дедупликация, TTL и файл-кэш, офлайн-fallback, форма payload |
| `test_telegram.py` | парсер `t.me/s/`, сквозной поток telegram-источника |
| `test_weather.py` | WMO-коды, разбор ответа Open-Meteo, день недели, часовое окно (`hourly_window`: старт с текущего часа, лимит, отставшая модель, короткие массивы и мусор вместо чисел), кэш, фильтр по городу, падение сети, `CITIES` (18 курортов, границы, совпадение с каталогом) |
| `test_sea.py` | купальный индекс: пороги воды (23/20/16 °C) и волны (1,0/1,5 м), подписи волнения, вердикт по сырым значениям, разбор Open-Meteo Marine, мусор вместо чисел, кэш, фильтр по точке, сводка `warmest`, согласованность `SEA_POINTS` с `CITIES` (15 точек вынесены в море рядом со «своим» городом, у материковых курортов точек нет) |
| `test_e2e_smoke.py` | сквозные сценарии: квиз → план → ссылка (3 профиля из чек-листа), выполнимость плана по дням, deep-link места, ссылка на подборку каталога, precache PWA, контракт `/api/health` |
| `tests/js/catalog-link.test.js` | фильтры каталога ↔ URL: дефолты не пишутся, round-trip кириллицы/спецсимволов, откат мусорной сортировки, флаг `open=1` |
| `tests/js/favs-link.test.js` | избранное ↔ URL: round-trip id, дубли и мусор, только id из каталога получателя, устойчивость к битому query |
| `tests/js/catalog-page.test.js` | порционный показ: размер первой порции, шаг догрузки, сужение подборки фильтром, устойчивость к мусору |
| `tests/js/rate-limit.test.js` | ответ 429: разбор `Retry-After` (мусор → `null`, потолок часа), русские формы минут, «через 30 с» / «через 5 минут», текст без времени ожидания, чтение бюджета ручки и общего потолка (`X-RateLimit-Total-*`), отдых кнопки по потолку |
| `tests/js/hourly.test.js` | окно почасового прогноза: крымское время вместо пояса устройства, «сейчас» ровно один раз и первым, переход через полночь, отставший кэш API (пустое окно вместо вчерашних часов), размер окна и мусорные значения, порог подписи осадков |
| `test_i18n.py` | контракт английской локали: `en.json` покрывает строки фронта без мёртвых ключей, `places` переводит ровно те поля, что есть в данных, **вывески изданий переведены** (бейдж новости приходит из `sources.json`), английские значения не содержат кириллицы (кроме бренда), `NUMBER_RE` синхронна с `I18n.fold`, бандл совпадает с источником (`build.py --check`) |
| `tests/js/i18n.test.js` | вторая речь: сворачивание чисел и порядок поиска ключа (буквал важнее свёрнутого), `params` в обе стороны, обход DOM (узлы, `title`/`aria-label`/`placeholder`/`alt`, `data-i18n="skip"`), идемпотентность, `applyLabels`/`stripLabels`, выбор языка |
| `tests/js/i18n-labels.test.js` | покрытие подписей, которые СОБИРАЮТ модули: вызывает `CatalogPage.statusLabel`, `RateLimit.waitText/message/budgetText`, `OpenNow.label` (все ветки и 12 месяцев) и `Hourly.hourLabel` и требует, чтобы словарь знал результат |
| `tests/js/open-now.test.js` | «открыто сейчас»: крымское время вне пояса устройства, дневные границы `firstDay`/`lastDay` (в т.ч. зимние диапазоны), сезоны через Новый год, границы окна, выходные дни, дата открытия в подписи вне сезона, битые правила |

Соглашения:

- **Тесты не трогают реальный `cache/`**: autouse-фикстура
  `conftest.py::_redirect_cache_file` подменяет `NEWS_CACHE_FILE`
  на `tmp_path`.
- **Тесты не ходят в сеть**: `_fetch_feed`/`_fetch_city` подменяются
  заглушками (см. `test_news.py`, `test_weather.py`).
- Новый эндпоинт — плюс тест в `test_api.py`; новое правило данных —
  плюс тест в `test_data.py`.
- Чистые JS-функции, от которых зависит шаринг/роутинг, — в отдельные
  файлы вида `static/plan-link.js` и `static/catalog-link.js`
  (UMD: `window` + `module.exports`) с тестами в `tests/js/`.
- Inline-обработчики (`onerror=` и т.п.) во фронтенде запрещены CSP —
  аварии картинок обрабатывает делегированный listener по
  `data-img-fallback` (`remove` / `hide` / `soft`).

## Проверка настоящего браузера (опционально)

Основной CI остаётся без браузерных зависимостей. Перед релизом можно
проверить интерфейс целиком, отдельно от HTTP-smoke:

```bash
.venv/bin/pip install -r requirements-browser.txt
.venv/bin/playwright install chromium
# В другом терминале запустить приложение по инструкции выше.
.venv/bin/python tools/browser_smoke.py
# Другой адрес или уже установленный Chromium:
BROWSER_URL=http://localhost:8000 CHROMIUM_PATH=/usr/bin/chromium \
  .venv/bin/python tools/browser_smoke.py
```

Сценарий использует отдельные браузерные контексты и проходит UI при
1280 и 390 px: 7 вопросов квиза, возврат назад, план и его импорт по ссылке
в чистом контексте, маршрут на обеих картах, поиск и ссылка каталога,
избранное после перезагрузки, ссылка места, модалка с клавиатуры и
возврат фокуса, два совпавших маркера (настоящий клик, без `force`),
Leaflet/зум/фильтры, RU/EN и офлайн-перезагрузка под service worker.

Внешние тайлы OSM подменяются картинкой: это проверка Leaflet и нашего
кода, **не доступности внешнего сервиса**. Новости и погоду нужно также
проверить отдельно на живом сервере. Chromium с узким viewport не
заменяет проверку установки PWA и жестов на настоящем iPhone/Android.

Переходы квиза дополнительно проверяет `tests/js/quiz-flow.test.js`, а
раскладку совпавших маркеров — `tests/js/map-layout.test.js`; эти тесты
без зависимостей входят в обычный CI.

## CI

GitHub Actions (`.github/workflows/ci.yml`), на push в `main`/`arena/**`
и на PR:

1. **test** — install deps (`requirements-dev.txt`) → `ruff check app tests`
   → `ruff format --check app tests tools` →
   `node --check` (`app.js`, `plan-link.js`, `catalog-link.js`,
   `catalog-page.js`, `open-now.js`, `favs-link.js`, `sw.js`) →
   `node --test "tests/js/*.test.js"` → `pytest -q` →
   **репетиция выката** (`bash -n deploy/*.sh` + `DRY_RUN=1 ./deploy/deploy.sh HEAD`:
   сценарий деплоя проверяется на каждый push, без сервера и Docker);
2. **docker** — сборка образа и валидация compose-стека
   (`docker compose config` с `.env` и проверка, что без него конфиг падает).

## Стиль кода

- Python: PEP 8, строки ≤ 88 символов, docstring на модулях, публичных
  классах и нетривиальных функциях. Комментарии и сообщения — на русском.
  Стиль enforced: `ruff check app tests` + `ruff format app tests tools`
  (конфиг — `pyproject.toml`; версия ruff закреплена в
  `requirements-dev.txt`, чтобы формат не дрейфовал в CI).
- Типизация: аннотации в сигнатурах сервисов (`dict`, `list[dict]`,
  `tuple[...]`); `pydantic.BaseModel` для тел запросов.
- JS: ES2020, без транспиляции; `$`/`$$` — хелперы селекторов; состояние —
  единый объект `state`; рендер через template literals.
- Константы для словарей/правил — в верхней части модулей
  (`TAGS`, `TYPE_META`, `TOPIC_RULES`, `CRIMEA_WORDS`).

## Как расширять

| Задача | Что править | Тесты |
|---|---|---|
| Новое место | объект в `app/data/attractions.json` (схема — [data.md](data.md#attractionsjson)); `hours` — только при стабильном расписании, вместе с парным `schedule`; **плюс перевод**: запись в `tools/i18n_en/tr_places.py` (id → те же поля, что есть в данных) и `build.py` | авто: `test_data.py`, `test_i18n.py` |
| Новая строка интерфейса | русская фраза в `static/index.html` или `static/app.js` — обходчик переведёт её сама; если вставка стоит внутри фразы, выносить шаблоном: `t("Показано {seen} из {total}", …)`. Дыры: `python tools/i18n_extract.py --missing`; перевод — в `tools/i18n_en/tr_ui.py`, затем `build.py` | `test_i18n.py` (покрытие двустороннее: ни дыр, ни мёртвых ключей) |
| Новый источник ленты | строка в `sources.json` + `labels` в `tools/i18n_en/tr_ui.py` (название издания в бейдже переводят транслитерацией, заголовок новости — чужой текст) | `test_data.py::test_sources_urls_unique`, `test_assets.py::test_news_skips_only_foreign_text` |
| Новая подпись модуля | строку собирает `static/*.js` (например «через 5 минут») — в словарь её кладут в свёрнутом виде («через {n} минут»); статика её не видит, поэтому проверят JS-тесты | `tests/js/i18n-labels.test.js` |
| Новый RSS-источник | строка в `sources.json`, `"type": "rss"` | `test_data.py::test_sources_urls_unique` |
| Новый TG-канал | строка в `sources.json`, `"type": "telegram"`, url `https://t.me/s/<канал>` (только публичные) | то же |
| Новый город погоды | кортеж в `CITIES` (`app/services/weather.py`) | `test_weather.py` |
| Новый лимит | `Rule` в `rules()` (`app/ratelimit.py`) + дефолт в `config.py`, строка в `.env.example` и `docker-compose.yml`, таблица в [docs/api.md](api.md#ограничение-частоты-запросов); подписи отказа — `static/rate-limit.js`. Общий потолок клиента (`total`) живёт рядом: `total_rule()` + `RATE_LIMIT_TOTAL`(+`_WINDOW`) | `test_ratelimit.py`, `test_config.py`, `test_assets.py`, `tests/js/rate-limit.test.js` |
| Новый шаг деплоя | `deploy/deploy.sh` (исполняется на сервере) + шаг в `.github/workflows/deploy.yml`; секреты — только в GitHub. Шаг обязан попадать и в репетицию: проверка — в `check_repo`, строка плана — в блок `DRY_RUN` | `test_assets.py::test_deploy_*`, `test_assets.py::test_deploy_rehearsal_*` (запускают `--dry-run` по-настоящему) |
| Новое поле прогноза | параметр в `_fetch_city` (`hourly=…`) + разбор в `hourly_window()`; показ — `static/hourly.js` (правило окна держат JS-тесты) | `test_weather.py`, `tests/js/hourly.test.js` |
| Новая морская точка | кортеж в `SEA_POINTS` (`app/services/marine.py`), id — как у курорта в `CITIES`, координаты — в открытой воде в 1–8 км от города | `test_sea.py` |
| Новый порог купального индекса | правила `verdict()` в `app/services/marine.py` (во фронте их дублировать нельзя) | `test_sea.py` |
| Новый тег | `TAGS` + `TAG_EMOJI`, профиль в `PROFILES`, связь с лентой в `PURPOSE_TOPICS` (`recommend.py`) + вариант в `quiz.json` | `test_data.py`, `test_recommends.py` |
| Новый тип места | `TYPE_META` в `recommend.py` + картинка в `static/img/` + цвет в `TYPE_COLORS` (`app.js`) | `test_data.py::test_type_meta_images_exist` |
| Оптимизировать картинки | `pip install pillow && python tools/optimize_images.py` (бюджеты веса — в `test_assets.py` и в самом скрипте) | `test_assets.py::test_image_weight_budget` |
| Новая тема новостей | правило в `TOPIC_RULES` (`news.py`, порядок = приоритет) + подпись в `TOPIC_LABELS` (`app.js`) | `test_news.py::test_topics_*` |
| Новый вопрос квиза | `quiz.json` + учёт ответа в `evaluate()`/`_score_attraction()` + поле в `QuizIn` (`main.py`) + сериализация ссылки плана (`buildPlanLink`/`parsePlanParam` в `app.js`) | `test_data.py`, `test_api.py` |
| Новый эндпоинт | маршрут в `main.py`; документация — [api.md](api.md) | `test_api.py` |

После правки данных всегда прогоняйте `pytest tests/test_data.py` —
свит проверяет согласованность датасета со словарями кода. После правки
переводов — `python tools/i18n_en/build.py` (бандл генерируется из
`tools/i18n_en/`, руками `static/i18n/en.json` не правят: `test_i18n.py`
сверит файл с источником).

## Переменные окружения

Полный список — в таблице README. Приоритет: env > дефолты `config.py`.
Изменения читаются при старте процесса (hot-reload пересоздаёт процесс,
так что --reload их подхватывает).

## Отладка

- **Ответ 429 в dev?** Лимиты действуют и локально: квиз — 30 расчётов
  в минуту, `?refresh=1` — свой бюджет у каждой ручки (лента 6 за 5 минут,
  погода 4 за 15, море 3 за 30), а поверх них — общий потолок клиента
  (120 дорогих запросов за 10 минут, `RATE_LIMIT_TOTAL`). Для бэнчмарков
  и ручных прогонов ставьте `RATE_LIMIT_ENABLED=0`; посмотреть текущие
  бюджеты и нагрузку — `curl -s localhost:8000/api/limits`
  (`X-RateLimit-Rule: total` в отказе означает, что отбил потолок).
- **Проверить сценарий выката без сервера?**
  `DRY_RUN=1 APP_DIR=$PWD ./deploy/deploy.sh HEAD` — репетиция: проверки
  и план, ничего не меняет. С тегом сверяется и версия:
  `EXPECT_VERSION=1.11.0 ./deploy/deploy.sh --dry-run HEAD`.
- **Лента «офлайн» в dev-машине?** Проверьте исходящий HTTPS
  (`curl -I https://tass.ru/rss/v2.xml`). При недоступной сети приложение
  корректно показывает снапшот — это штатный офлайн-режим.
- **Какой источник упал?** `failed_sources` в ответе `/api/news`.
- **Сбросить файловый кэш ленты**: `rm -rf cache/`.
- **Сбросить PWA-кэш в браузере**: DevTools → Application → Storage → Clear.
- Логи uvicorn показывают тайминги запросов; уровень — стандартный
  (`--log-level debug` при необходимости).

## Релиз

1. Поднять `APP_VERSION` в `app/config.py` (semver), версию в README,
   пример в `docs/api.md` и `CACHE` в `static/sw.js`
   (согласованность проверяет `test_config.py`).
2. Если менялись строки фронта или данные каталога — пересобрать
   `python tools/i18n_en/build.py` (новый префикс `CACHE` в `sw.js` сам
   сбросит оболочку у тех, кто уже её держит).
3. Прогнать `ruff check`, `pytest`, `node --check` и `node --test`.
4. Записать изменения в `CHANGELOG.md`; закрытую фазу свернуть таблицей
   в `docs/roadmap-archive.md`, а [ROADMAP.md](../ROADMAP.md) — ориентир,
   он меняется, когда меняется направление, а не когда фаза закрыта.
5. PR в `main`: CI обязан быть зелёным (test + docker build).
6. Выкатить: `git pull && docker compose up -d --build` на сервере —
   подробности и бэкапы в [deploy.md](deploy.md). Если настроен
   автодеплой, достаточно `git tag v1.13.0 && git push --tags`:
   workflow сам прогонит тесты, репетицию выката и выкатит релиз.
   До первого выката сценарий стоит проверить репетицией
   (`./deploy/deploy.sh --dry-run v1.13.0`) или ручным запуском workflow
   с `dry_run=true` — ни сервера, ни секретов для этого не нужно.
