# Changelog «Крым.Гид»

Формат — [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
версии — [semver](https://semver.org/lang/ru/). Даты — UTC.

## [0.11.0] — 2026-09-16

Фаза «Качество и контракт API» ([ROADMAP](ROADMAP.md)). Пользовательское
поведение не менялось; менялись контракт API и процессы.

### Changed (контракт API)

- `POST /api/quiz/evaluate`: строгая валидация тела (`Literal` по `id`
  опций `quiz.json`) — мусор отклоняется с `422` вместо молчаливых дефолтов.
- `GET /api/weather?city=<неизвестно>`: `404 {"detail": "город … не найден"}`
  вместо молчаливого «все города».

### Added

- `static/plan-link.js`: сериализация плана в ссылку вынесена из `app.js`
  в UMD-модуль; 6 JS-тестов (`tests/js/`, `node:test` без зависимостей).
- `test_config.py::test_version_is_consistent_everywhere`: `APP_VERSION`,
  `sw.js`, `README.md` и `docs/api.md` обязаны называть одну версию.
- `test_data.py::test_quiz_options_match_quiz_model`: `Literal` в `QuizIn`
  обязаны совпадать с `id` опций `quiz.json` (включая дефолты).
- Ruff (`E,F,I,UP,B,C4,S,BLE`, строка ≤ 88) — конфиг в `pyproject.toml`,
  шаг `ruff check app tests` в CI.
- `ROADMAP.md` — план развития; этот `CHANGELOG.md`.

### Docs

- `docs/api.md`: `422` для квиза, `404` для погоды, обновлённая таблица кодов.
- `docs/development.md`: ruff, JS-тесты, шаги CI, релиз-чеклист.

## [0.10.0] — 2026-09-16

Бета: квиз (7 вопросов) с планом по дням и шарингом ссылкой/текстом/печатью;
каталог 52 точки с координатами; SVG-схема-карта; новости из 7 RSS + 4 TG;
погода по 18 курортам; PWA; 135 тестов.
