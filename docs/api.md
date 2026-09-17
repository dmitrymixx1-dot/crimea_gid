# Справочник REST API

Базовый URL: `/api`. Все ответы — JSON в UTF-8.
Интерактивная OpenAPI-документация FastAPI: `/docs`, `/redoc`.

Общие заголовки ответов (middleware безопасности):

```
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
Content-Security-Policy: default-src 'self'; script-src 'self';
  style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self';
  font-src 'self' data:; object-src 'none'; base-uri 'self';
  form-action 'self'; frame-ancestors 'self'
```

CSP допускает inline только для стилей (style-атрибуты шаблонов):
весь JavaScript приложения — внешние файлы (`script-src 'self'`),
inline-обработчики вида `onerror=` во фронтенде запрещены и закрыты
тестом `test_assets.py::test_no_inline_event_handlers_in_frontend`.
`frame-ancestors` ослабляется переменной `CSP_FRAME_ANCESTORS`
(например, `*` для встраивания в iframe-превью).

## Оглавление

- [GET /api/health](#get-apihealth)
- [GET /api/tags](#get-apitags)
- [GET /api/attractions](#get-apiattractions)
- [GET /api/attractions/{id}](#get-apiattractionsid)
- [GET /api/areas](#get-apiareas)
- [GET /api/quiz](#get-apiquiz)
- [POST /api/quiz/evaluate](#post-apiquizevaluate)
- [GET /api/news](#get-apinews)
- [GET /api/weather](#get-apiweather)
- [Служебные маршруты](#служебные-маршруты)
- [Коды ошибок](#коды-ошибок)

---

## GET /api/health

Живость сервиса и версия приложения. Используется Docker-healthcheck'ом
и фронтендом (бейдж версии в подвале).

**Ответ 200:**

```json
{"ok": true, "name": "Крым.Гид", "version": "0.12.0"}
```

| Поле | Тип | Описание |
|---|---|---|
| `ok` | bool | всегда `true`, если сервер отвечает |
| `name` | string | имя приложения |
| `version` | string | версия (semver, `MAJOR.MINOR.PATCH[-суффикс]`) |

---

## GET /api/tags

Словари тегов и типов мест. Фронтенд строит по ним фильтры, чипы,
легенду карты и эмодзи категорий.

**Ответ 200:**

```json
{
  "tags": {"beach": "пляжи", "wine": "вино", "...": "..."},
  "types": {
    "winery": {"emoji": "🍷", "label": "Вина", "img": "cat_wine.jpg"},
    "...": {}
  }
}
```

| Поле | Тип | Описание |
|---|---|---|
| `tags` | object | `id тега → русское название` (15 тегов) |
| `types` | object | `id типа → {emoji, label, img}`; `img` — файл в `/static/img/` |

Список тегов и типов: [data.md](data.md#справочники).

---

## GET /api/attractions

Каталог мест с фильтрами. Все элементы содержат координаты `lat`/`lng`
(используются схемой-картой).

**Параметры запроса** (все необязательные, комбинируются логическим И):

| Параметр | Тип | Описание |
|---|---|---|
| `tag` | string | оставить места, у которых есть этот тег (напр. `wine`) |
| `area` | string | географический район (напр. `Восточный`, URL-encoded) |
| `q` | string | подстрока в названии или описании (регистр не важен) |

**Пример:** `GET /api/attractions?tag=beach&area=Южный+берег&q=пляж`

**Ответ 200:**

```json
{
  "count": 52,
  "items": [
    {
      "id": "aipetri",
      "name": "Ай-Петри: канатная дорога и плато",
      "type": "nature",
      "region": "Ялта → Ай-Петри, 1234 м",
      "area": "Южный берег",
      "description": "7-минутный подъём канаткой…",
      "tags": ["view", "active", "photo", "nature"],
      "season": ["spring", "summer", "autumn"],
      "budget": 2,
      "duration_h": 4,
      "rating": 4.8,
      "price_hint": "канатка ~1200 ₽",
      "tips": "Берите ветровку…",
      "access": "both",
      "lat": 44.45,
      "lng": 34.06
    }
  ]
}
```

Поля элемента — см. [data.md → attractions.json](data.md#attractionsjson).

---

## GET /api/attractions/{id}

Одна точка каталога. Используется фронтендом для прямых ссылок
`#/place/<id>` и доступен внешним потребителям.

**Ответ 200:** все поля элемента каталога + `type_meta`:

```json
{
  "id": "aipetri",
  "name": "Ай-Петри: канатная дорога и плато",
  "…": "…",
  "type_meta": {"emoji": "🌿", "label": "Природа", "img": "cat_nature.jpg"}
}
```

**Ответ 404:**

```json
{"detail": "место «nope» не найдено"}
```

---

## GET /api/areas

Список географических районов, реально присутствующих в каталоге
(для селекта фильтра).

**Ответ 200:**

```json
{"areas": ["Восточный", "Западный", "Южный берег", "Центральный"]}
```

---

## GET /api/quiz

Контент квиза: вступление и 7 вопросов с вариантами ответов.
Схема вопроса — см. [data.md → quiz.json](data.md#quizjson).

**Ответ 200:**

```json
{
  "intro": "Ответьте на 7 коротких вопросов…",
  "questions": [
    {
      "id": "purpose",
      "type": "multi",
      "max": 3,
      "emoji": "🎯",
      "title": "Что для вас главное в отпуске?",
      "subtitle": "Выберите до трёх вариантов",
      "options": [
        {"id": "beach", "emoji": "🏖️", "label": "Море и пляжи", "hint": "…"}
      ]
    }
  ]
}
```

---

## POST /api/quiz/evaluate

Ответы квиза → профиль отдыха, ранжированные рекомендации,
план по дням, подсказка по логистике и новости по интересам.

Результат детерминирован: одни и те же ответы → один и тот же набор
(новости могут отличаться — лента живая).

**Тело запроса** (все поля необязательные; пустое тело валидно):

```json
{
  "purpose": ["beach", "photo"],
  "season": "summer",
  "tempo": "relax",
  "budget": "comfort",
  "party": "couple",
  "duration": "3-5",
  "transport": "car"
}
```

| Поле | Тип | Значения | По умолчанию |
|---|---|---|---|
| `purpose` | string[] | id тегов (неизвестные отбрасываются), макс. 3 | `["beach"]` |
| `season` | string | `summer` `spring` `autumn` `winter` `any` | `any` |
| `tempo` | string | `relax` `medium` `active` | `medium` |
| `budget` | string | `economy` `comfort` `premium` | `comfort` |
| `party` | string | `solo` `couple` `family` `friends` | `solo` |
| `duration` | string | `1-2` `3-5` `6-10` `10+` | `3-5` |
| `transport` | string | `car` `transit` | `car` |

**Ответ 200** (фрагменты):

```json
{
  "profile": {"title": "Море, солнце и спокойствие", "emoji": "🌅", "summary": "…"},
  "answers": {"purpose": ["beach", "photo"], "…": "…"},
  "count": 8,
  "days_hint": "3-5",
  "all_matched": 24,
  "recommendations": [
    {"id": "…", "name": "…", "score": 7.9,
     "reasons": ["Совпадает: пляжи"], "type_meta": {"emoji": "🏖️", "…": "…"}}
  ],
  "itinerary": {
    "n_days": 4,
    "days": [
      {"day": 1, "area": "Южный берег", "area_label": "Южный берег",
       "tags": ["beach", "view"],
       "stops": [
         {"id": "…", "name": "…", "slot": "morning", "duration_h": 3}
       ]}
    ],
    "reserve": [{"id": "…", "name": "…"}]
  },
  "news": [{"title": "…", "crimea_score": 4, "topics": ["beach"]}],
  "transport_hint": "🚗 На машине можно заехать…"
}
```

Семантика ключевых полей:

| Поле | Описание |
|---|---|
| `profile` | выбранный по первому интересу («профиль отдыха») |
| `count` / `all_matched` | сколько мест в выдаче / сколько всего прошло порог |
| `recommendations[].score` | итоговый балл места (как считается — [architecture.md](architecture.md#матчинг)) |
| `recommendations[].reasons` | человекочитаемые объяснения «почему» |
| `itinerary.days[].stops[].slot` | `morning` `afternoon` `evening` `full` |
| `itinerary.reserve` | подошедшие места, не влезшие в дни («запас на дождь») |
| `news` | до 4 крымских новостей по темам интересов |

**Ответ 422** — невалидное тело: неверный тип поля (например, `purpose`
не список) или значение вне `id` опций `quiz.json` (например,
`season: "never"`). Пустой `purpose` валиден — трактуется как `["beach"]`.

---

## GET /api/news

Лента новостей: агрегат RSS-источников и публичных телеграм-каналов
с фильтром «про Крым», классификацией тем и кэшированием.

**Параметры запроса:**

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `limit` | int | 40 | сколько элементов вернуть (1–100) |
| `refresh` | bool | false | `1` — игнорировать кэш и перечитать источники |

> ⚠️ `refresh=1` дёргает все внешние источники (до `NEWS_HTTP_TIMEOUT`
> секунд на источник). Не используйте в циклах.

**Ответ 200:**

```json
{
  "online": true,
  "updated_at": "2026-09-15T22:00:00+03:00",
  "sources": [{"id": "tass", "name": "ТАСС"}, {"id": "tg-rbc", "name": "РБК · TG"}],
  "failed_sources": ["News.ru · TG"],
  "total": 80,
  "crimea_total": 16,
  "items": [
    {
      "id": "n0",
      "title": "В Крыму продлили купальный сезон",
      "link": "https://…",
      "summary": "…",
      "published": "2026-09-15T18:40:00+03:00",
      "source": "ТАСС",
      "source_id": "tass",
      "crimea_score": 6,
      "topics": ["beach", "weather"]
    }
  ]
}
```

| Поле | Описание |
|---|---|
| `online` | `true` — хотя бы один источник ответил; `false` — показан кэш/офлайн-снапшот |
| `failed_sources` | имена источников, не ответивших при последнем опросе |
| `total` / `crimea_total` | всего элементов / из них про Крым (`crimea_score > 0`) |
| `items[].crimea_score` | баллы «крымскости» (маркеры городов и географии) |
| `items[].topics` | до 3 тем: `safety` `transport` `beach` `weather` `nature` `events` `food` `history` |
| `items[].id` | `n<N>` — живые элементы, `s<N>` — из офлайн-снапшота |

В офлайн-режиме элементы снапшота могут содержать флаг `sample: true`
(демонстрационные материалы — фронтенд их помечает).

---

## GET /api/weather

Погода по курортам (Open-Meteo, без ключа), кэш на час.

**Параметры запроса:**

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `city` | string | — | id города (напр. `yalta`); неизвестный id → `404` |
| `refresh` | bool | false | `1` — игнорировать часовой кэш |

**Ответ 200:**

```json
{
  "online": true,
  "updated_at": "2026-09-15T22:10:00+03:00",
  "cities": [
    {
      "id": "yalta",
      "name": "Ялта",
      "available": true,
      "current": {"temp": 22, "emoji": "🌤️", "label": "в основном ясно", "wind": 12},
      "forecast": [
        {"day": "Ср", "emoji": "🌤️", "max": 26, "min": 17},
        {"day": "Чт", "emoji": "⛅", "max": 25, "min": 16}
      ]
    },
    {"id": "kerch", "name": "Керчь", "available": false}
  ]
}
```

Погодные коды — WMO (`current.label` — русская подпись; полный словарь —
`WMO` в `app/services/weather.py`). `online: false` + `available: false`,
если Open-Meteo недостижим — фронтенд в этом случае прячет виджет.
Список городов — константа `CITIES` (18 курортов).

**Ответ 404** — неизвестный `city`:

```json
{"detail": "город «gotham» не найден"}
```

---

## Служебные маршруты

| Метод | Путь | Описание |
|---|---|---|
| GET | `/` | SPA-каркас: `index.html` с подставленным origin в Open Graph |
| GET | `/static/*` | статика (JS/CSS/изображения, манифест PWA) |
| GET | `/sw.js` | service worker из корня (scope `/`), `Cache-Control: no-cache` |

`GET /` отдаёт каркас с мета-тегами Open Graph / Twitter Card: плейсхолдер
`__ORIGIN__` заменяется фактическим origin запроса (с учётом
`X-Forwarded-Proto`/`X-Forwarded-Host`) или значением `SITE_ORIGIN` из env —
`og:url` и `og:image` обязаны быть абсолютными. Ответ — `text/html`,
заголовки безопасности те же.

---

## Коды ошибок

| Код | Когда |
|---|---|
| 404 | неизвестный `/api/*` маршрут; `/api/attractions/{id}` с несуществующим id; `/api/weather?city=` с неизвестным id |
| 405 | метод не поддерживается маршрутом (например, POST на GET-эндпоинт) |
| 422 | невалидные параметры запроса/тела (тип, диапазон `limit`, значение вне опций квиза) |
| 500 | непредвиденная ошибка (внешние сервисы сами по себе 500 не вызывают — они переводят ленту/погоду в офлайн) |
