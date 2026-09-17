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
node --test "tests/js/*.test.js"            # JS-тесты шаринга плана и каталога
node --check static/app.js && node --check static/plan-link.js \
  && node --check static/catalog-link.js && node --check static/sw.js
.venv/bin/ruff check app tests              # линтер
```

**206 Python-тестов**, сеть не используется (все внешние вызовы заглушены),
плюс **33 JS-теста** (`tests/js/`, `node:test` без зависимостей):

| Модуль | Что покрывает |
|---|---|
| `test_api.py` | эндпоинты, фильтры (в т.ч. `tag=extreme`, `area=Западный`), заголовки безопасности и CSP, рендер Open Graph (origin из env/`X-Forwarded-*`), a11y-каркас, PWA-маршруты, контракт 422 (квиз) / 404 (погода) |
| `test_assets.py` | аудит статики: бюджет веса и размеры картинок, отсутствие inline-обработчиков и пустых `alt`, внешние `<script>`, согласованность SW/манифеста, прод-конфигурация (`docker-compose.yml`, `Caddyfile`, скрипты бэкапа) |
| `test_data.py` | схемы данных, границы координат, **якорные координаты** (`ANCHORS` — сверено с OSM), объём каталога и покрытие районов, согласованность каталога/квиза со словарями кода и `QuizIn`, покрытие всех `TAGS` в `quiz.purpose`/`PROFILES`/`PURPOSE_TOPICS`, источники, файлы картинок типов |
| `test_load.py` | загрузчик JSON: схемы, кэширование, ошибка на отсутствующий файл |
| `test_config.py` | формат версии, **согласованность версий** (код/README/SW/доки), дефолты, переопределение через env, пути |
| `test_recommends.py` | матчинг (`_score_attraction` по факторам), профили, фильтры новостей, планировщик (слоты, районы, лимиты, запас) |
| `test_news.py` | скоринг «Крым», темы, дедупликация, TTL и файл-кэш, офлайн-fallback, форма payload |
| `test_telegram.py` | парсер `t.me/s/`, сквозной поток telegram-источника |
| `test_weather.py` | WMO-коды, разбор ответа Open-Meteo, день недели, кэш, фильтр по городу, падение сети, `CITIES` (18 курортов, границы, совпадение с каталогом) |
| `test_e2e_smoke.py` | сквозные сценарии: квиз → план → ссылка (3 профиля из чек-листа), выполнимость плана по дням, deep-link места, ссылка на подборку каталога, precache PWA, контракт `/api/health` |
| `tests/js/catalog-link.test.js` | фильтры каталога ↔ URL: дефолты не пишутся, round-trip кириллицы/спецсимволов, откат мусорной сортировки, флаг `open=1` |
| `tests/js/catalog-page.test.js` | порционный показ: размер первой порции, шаг догрузки, сужение подборки фильтром, устойчивость к мусору |
| `tests/js/open-now.test.js` | «открыто сейчас»: крымское время вне пояса устройства, сезоны через Новый год, границы окна, выходные дни, битые правила |

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

## CI

GitHub Actions (`.github/workflows/ci.yml`), на push в `main`/`arena/**`
и на PR:

1. **test** — install deps (`requirements-dev.txt`) → `ruff check app tests` →
   `node --check` (`app.js`, `plan-link.js`, `catalog-link.js`,
   `catalog-page.js`, `open-now.js`, `sw.js`) →
   `node --test "tests/js/*.test.js"` → `pytest -q`;
2. **docker** — сборка образа и валидация compose-стека
   (`docker compose config` с `.env` и проверка, что без него конфиг падает).

## Стиль кода

- Python: PEP 8, строки ≤ 88 символов, docstring на модулях, публичных
  классах и нетривиальных функциях. Комментарии и сообщения — на русском.
  Стиль enforced: `ruff check app tests` (конфиг — `pyproject.toml`).
- Типизация: аннотации в сигнатурах сервисов (`dict`, `list[dict]`,
  `tuple[...]`); `pydantic.BaseModel` для тел запросов.
- JS: ES2020, без транспиляции; `$`/`$$` — хелперы селекторов; состояние —
  единый объект `state`; рендер через template literals.
- Константы для словарей/правил — в верхней части модулей
  (`TAGS`, `TYPE_META`, `TOPIC_RULES`, `CRIMEA_WORDS`).

## Как расширять

| Задача | Что править | Тесты |
|---|---|---|
| Новое место | объект в `app/data/attractions.json` (схема — [data.md](data.md#attractionsjson)); `hours` — только при стабильном расписании, вместе с парным `schedule` | авто: `test_data.py` |
| Новый RSS-источник | строка в `sources.json`, `"type": "rss"` | `test_data.py::test_sources_urls_unique` |
| Новый TG-канал | строка в `sources.json`, `"type": "telegram"`, url `https://t.me/s/<канал>` (только публичные) | то же |
| Новый город погоды | кортеж в `CITIES` (`app/services/weather.py`) | `test_weather.py` |
| Новый тег | `TAGS` + `TAG_EMOJI`, профиль в `PROFILES`, связь с лентой в `PURPOSE_TOPICS` (`recommend.py`) + вариант в `quiz.json` | `test_data.py`, `test_recommends.py` |
| Новый тип места | `TYPE_META` в `recommend.py` + картинка в `static/img/` + цвет в `TYPE_COLORS` (`app.js`) | `test_data.py::test_type_meta_images_exist` |
| Оптимизировать картинки | `pip install pillow && python tools/optimize_images.py` (бюджеты веса — в `test_assets.py` и в самом скрипте) | `test_assets.py::test_image_weight_budget` |
| Новая тема новостей | правило в `TOPIC_RULES` (`news.py`, порядок = приоритет) + подпись в `TOPIC_LABELS` (`app.js`) | `test_news.py::test_topics_*` |
| Новый вопрос квиза | `quiz.json` + учёт ответа в `evaluate()`/`_score_attraction()` + поле в `QuizIn` (`main.py`) + сериализация ссылки плана (`buildPlanLink`/`parsePlanParam` в `app.js`) | `test_data.py`, `test_api.py` |
| Новый эндпоинт | маршрут в `main.py`; документация — [api.md](api.md) | `test_api.py` |

После правки данных всегда прогоняйте `pytest tests/test_data.py` —
свит проверяет согласованность датасета со словарями кода.

## Переменные окружения

Полный список — в таблице README. Приоритет: env > дефолты `config.py`.
Изменения читаются при старте процесса (hot-reload пересоздаёт процесс,
так что --reload их подхватывает).

## Отладка

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
2. Прогнать `ruff check`, `pytest`, `node --check` и `node --test`.
3. Записать изменения в `CHANGELOG.md`, отметить пункты в `ROADMAP.md`.
4. PR в `main`: CI обязан быть зелёным (test + docker build).
5. Выкатить: `git pull && docker compose up -d --build` на сервере —
   подробности и бэкапы в [deploy.md](deploy.md).
