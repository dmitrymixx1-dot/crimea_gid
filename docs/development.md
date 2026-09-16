# Для разработчика

## Окружение

Требования: **Python 3.11+**; опционально Node.js (проверка синтаксиса JS)
и Docker.

```bash
git clone <repo> && cd crimea_gid
./run.sh          # поднимет venv, поставит зависимости, запустит dev-сервер
# или вручную:
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install pytest           # для тестового свита
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Приложение: `http://localhost:8000` (OpenAPI — `/docs`).

## Тесты

```bash
.venv/bin/python -m pytest tests/ -q        # весь свит
.venv/bin/python -m pytest tests/test_news.py -q   # один модуль
.venv/bin/python -m pytest tests/ -k weather -q    # по имени
node --check static/app.js && node --check static/sw.js
```

**135 тестов**, сеть не используется (все внешние вызовы заглушены):

| Модуль | Что покрывает |
|---|---|
| `test_api.py` | эндпоинты, фильтры (в т.ч. `tag=extreme`, `area=Западный`), заголовки безопасности, PWA-маршруты, 404/422 |
| `test_data.py` | схемы данных, границы координат, **якорные координаты** (`ANCHORS` — сверено с OSM), объём каталога и покрытие районов, согласованность каталога/квиза со словарями кода, источники, файлы картинок типов |
| `test_load.py` | загрузчик JSON: схемы, кэширование, ошибка на отсутствующий файл |
| `test_config.py` | формат версии, дефолты, переопределение через env, пути |
| `test_recommends.py` | матчинг (`_score_attraction` по факторам), профили, фильтры новостей, планировщик (слоты, районы, лимиты, запас) |
| `test_news.py` | скоринг «Крым», темы, дедупликация, TTL и файл-кэш, офлайн-fallback, форма payload |
| `test_telegram.py` | парсер `t.me/s/`, сквозной поток telegram-источника |
| `test_weather.py` | WMO-коды, разбор ответа Open-Meteo, день недели, кэш, фильтр по городу, падение сети, `CITIES` (18 курортов, границы, совпадение с каталогом) |

Соглашения:

- **Тесты не трогают реальный `cache/`**: autouse-фикстура
  `conftest.py::_redirect_cache_file` подменяет `NEWS_CACHE_FILE`
  на `tmp_path`.
- **Тесты не ходят в сеть**: `_fetch_feed`/`_fetch_city` подменяются
  заглушками (см. `test_news.py`, `test_weather.py`).
- Новый эндпоинт — плюс тест в `test_api.py`; новое правило данных —
  плюс тест в `test_data.py`.

## CI

GitHub Actions (`.github/workflows/ci.yml`), на push в `main`/`arena/**`
и на PR:

1. **test** — install deps → `node --check static/app.js` и
   `static/sw.js` → `pytest -q`;
2. **docker** — сборка образа (после успешных тестов).

## Стиль кода

- Python: PEP 8, строки ≤ 88 символов, docstring на модулях, публичных
  классах и нетривиальных функциях. Комментарии и сообщения — на русском.
- Типизация: аннотации в сигнатурах сервисов (`dict`, `list[dict]`,
  `tuple[...]`); `pydantic.BaseModel` для тел запросов.
- JS: ES2020, без транспиляции; `$`/`$$` — хелперы селекторов; состояние —
  единый объект `state`; рендер через template literals.
- Константы для словарей/правил — в верхней части модулей
  (`TAGS`, `TYPE_META`, `TOPIC_RULES`, `CRIMEA_WORDS`).

## Как расширять

| Задача | Что править | Тесты |
|---|---|---|
| Новое место | объект в `app/data/attractions.json` (схема — [data.md](data.md#attractionsjson)) | авто: `test_data.py` |
| Новый RSS-источник | строка в `sources.json`, `"type": "rss"` | `test_data.py::test_sources_urls_unique` |
| Новый TG-канал | строка в `sources.json`, `"type": "telegram"`, url `https://t.me/s/<канал>` (только публичные) | то же |
| Новый город погоды | кортеж в `CITIES` (`app/services/weather.py`) | `test_weather.py` |
| Новый тег | `TAGS` + `TAG_EMOJI` в `recommend.py`, вариант в `quiz.json`, при желании — профиль в `PROFILES` и правило в `purpose_topics` | `test_data.py`, `test_recommends.py` |
| Новый тип места | `TYPE_META` в `recommend.py` + картинка в `static/img/` + цвет в `TYPE_COLORS` (`app.js`) | `test_data.py::test_type_meta_images_exist` |
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

1. Поднять `APP_VERSION` в `app/config.py` (semver) и версию в README;
   при PWA-меняющихся правках — бампнуть `CACHE` в `static/sw.js`.
2. Прогнать `pytest` и `node --check`.
3. PR в `main`: CI обязан быть зелёным (test + docker build).
