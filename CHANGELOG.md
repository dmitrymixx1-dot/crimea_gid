# Changelog «Крым.Гид»

Формат — [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
версии — [semver](https://semver.org/lang/ru/). Даты — UTC.

## [Unreleased]

### Added

- Фаза 1.0: закрыт аудит покрытия тегов — все 15 тегов каталога теперь
  доступны в первом вопросе квиза, имеют профиль отдыха (`PROFILES`) и связь
  с темами ленты (`PURPOSE_TOPICS`); покрытие закреплено тестами.
- Тема новостей `nature` для природных локаций, экотроп, мысов, гор и ущелий.

### Docs

- `ROADMAP.md` и `docs/data.md`: зафиксирована матрица покрытия
  `TAGS` → `quiz.purpose` → `PROFILES` → `PURPOSE_TOPICS`.

## [0.12.0] — 2026-09-16

Фаза «Фронт и доступность» ([ROADMAP](ROADMAP.md)). Поведение для
пользователя изменилось точечно: фильтры каталога теперь видны в адресной
строке; остальное — новые возможности и ужесточение безопасности.

### Added

- Доступность: skip-link «Перейти к содержимому», focus trap в модалке
  с возвратом фокуса на инициатора, `aria-live` у тостов и анонс маршрутов
  (`#route-status`), осмысленные `alt` категорийных картинок,
  `aria-current="page"` в навигации, `aria-pressed` у избранного и чипов;
  карточки, остановки плана и точки карты открываются с клавиатуры
  (ссылки `#/place/<id>`, Enter/Space на маркерах SVG); видимый
  клавиатурный фокус (`:focus-visible`).
- Фильтры каталога в URL (`#/catalog?tag=&area=&q=&sort=`): подборка
  копируется кнопкой «🔗 Ссылка на подборку» и воспроизводится у получателя.
  Сериализация — `static/catalog-link.js` (UMD) + 8 JS-тестов.
- Open Graph / Twitter Card: `og:*`/`twitter:*` в каркасе; `GET /`
  подставляет фактический origin в `og:url`/`og:image` (`SITE_ORIGIN`
  из env или `X-Forwarded-Proto`/`X-Forwarded-Host`).
- `Content-Security-Policy` в заголовках всех ответов
  (`script-src 'self'`, `object-src 'none'`, `frame-ancestors 'self'`,
  ослабление через `CSP_FRAME_ANCESTORS`); inline-обработчики убраны —
  аварии картинок ведёт делегированный listener по `data-img-fallback`.
- `tests/test_assets.py` — аудит статики: бюджет веса и размеры картинок,
  запрет inline-обработчиков и пустых `alt`, внешние `<script>`,
  согласованность SW/манифеста.
- `tools/optimize_images.py` — dev-ресайз картинок (Pillow, идемпотентный,
  режим `--check`); в рантайм-зависимости не входит.

### Changed

- Картинки: hero 1536→1200 px (q76, progressive), категорийные 1536→760 px
  (q72) — `static/img` 3.1 МБ → 0.75 МБ; у hero `fetchpriority="high"`.
- Фильтры из ссылки — источник правды при входе в каталог; локальное
  состояние зеркалится в адрес через `history.replaceState`.
- `static/sw.js`: кэш `crimea-gid-v0.12.0`, в precache добавлен
  `catalog-link.js`, убран сырой `index.html` (кешируется рендер `GET /`).
- `manifest.webmanifest`: в описании 52 точки (было 36).
- Фронтенд экранирует поля данных и новостей при сборке шаблонов (`esc()`).

### Docs

- README: возможности 0.12.0, env `SITE_ORIGIN`/`CSP_FRAME_ANCESTORS`,
  161 Python-тест + 14 JS, `tools/` в структуре.
- `docs/api.md`: CSP в общих заголовках, `GET /` с подстановкой origin.
- `docs/architecture.md`: безопасность (CSP, esc, OG), фронтенд
  (URL-фильтры, a11y), PWA (precache рендера).
- `docs/development.md`: `test_assets.py` и `catalog-link.test.js`
  в таблицах, шаг CI `node --check static/catalog-link.js`, рецепт
  оптимизации картинок.

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
