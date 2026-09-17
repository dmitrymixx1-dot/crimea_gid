# Деплой в продакшен

Штатная схема: **два контейнера** — приложение (FastAPI/uvicorn) и
**Caddy**, который терминирует HTTPS и проксирует запросы внутрь.
Сертификат выпускается автоматически по ACME, поэтому ключей и токенов
в конфигурации по-прежнему нет — принцип «без API-ключей» из
[архитектуры](architecture.md#принципы) сохраняется и в деплое.

```
        :80/:443                       :8000 (только внутренняя сеть)
Интернет ─────────► caddy ───reverse_proxy──► app ──► app/data/*.json
                      │                        │
              caddy-data (сертификаты)   news-cache (том, /srv/cache)
```

## Требования

- Linux-сервер с Docker 24+ и плагином `docker compose`;
- домен, у которого `A` (и по возможности `AAAA`) указывает на сервер;
- открытые порты **80** и **443** (80 нужен ACME для проверки домена).

Ресурсы: приложение держится в ~150 МБ RAM, базы нет, диск расходуется
только на образ и кэш ленты (единицы мегабайт).

## Первый запуск

```bash
git clone <repo> && cd crimea_gid
cp .env.example .env
$EDITOR .env              # DOMAIN и ACME_EMAIL — обязательны
docker compose up -d --build
docker compose ps         # app должен быть healthy
```

Через 10–30 секунд после старта Caddy получит сертификат, и сайт
откроется по `https://<DOMAIN>`. Проверка живости:

```bash
curl -s https://<DOMAIN>/api/health     # {"ok":true,"name":"Крым.Гид","version":"…"}
```

### Переменные `.env`

| Переменная | Обязательна | Что делает |
|---|---|---|
| `DOMAIN` | ✔ | домен сайта: по нему выпускается сертификат и собирается `og:url` |
| `ACME_EMAIL` | ✔ | почта для Let's Encrypt (уведомления об истечении) |
| `NEWS_CACHE_TTL` | | кэш ленты, сек (по умолчанию 900) |
| `WEATHER_TTL` | | кэш погоды, сек (по умолчанию 3600) |
| `CSP_FRAME_ANCESTORS` | | кому разрешено встраивать сайт в iframe |

Полный список ручек приложения — в [таблице README](../README.md#переменные-окружения).
`SITE_ORIGIN` в compose выставляется автоматически из `DOMAIN` — руками
его задавать не нужно.

## Обновление версии

```bash
git pull
docker compose up -d --build     # пересборка + перезапуск без простоя тома
docker image prune -f            # подчистить старые слои
```

Кэш ленты лежит в томе `news-cache` и переживает пересборку.
После обновления у пользователей сменится версия service worker
(`crimea-gid-v<версия>`), старый кэш оболочки удалится сам — отдельных
действий на сервере не требуется.

Откат на предыдущую версию:

```bash
git checkout <тег-или-коммит>
docker compose up -d --build
```

## Бэкап и восстановление кэша

Файловый кэш (`/srv/cache/news_cache.json` в томе `news-cache`) — это
последняя успешно собранная лента. Данные **некритичные**: при потере
приложение просто сходит в источники заново, а до первого успешного
опроса покажет офлайн-снапшот. Бэкап нужен для переезда сервера, чтобы
сайт стартовал сразу с наполненной лентой.

```bash
deploy/backup-cache.sh                 # → ./backups/news-cache-<UTC>.tar.gz
deploy/backup-cache.sh /srv/backups    # свой каталог
KEEP=30 deploy/backup-cache.sh         # хранить 30 копий вместо 14
```

Скрипт снимает архив через временный контейнер, останавливать сервис не
нужно, и сам ротирует старые копии. Ежедневный бэкап в 4:15 UTC:

```cron
15 4 * * * cd /opt/crimea_gid && KEEP=30 deploy/backup-cache.sh >> /var/log/crimea-backup.log 2>&1
```

Восстановление:

```bash
deploy/restore-cache.sh backups/news-cache-20260917-101500.tar.gz
```

Что ещё стоит забрать при переезде:

| Что | Где | Зачем |
|---|---|---|
| `news-cache` | том Docker | лента переживает переезд (скрипты выше) |
| `.env` | корень проекта | домен и почта ACME |
| `caddy-data` | том Docker | сертификаты; можно не переносить — Caddy выпустит новые (следите за [rate limits](https://letsencrypt.org/docs/rate-limits/) Let's Encrypt при частых пересозданиях) |

Контент (`app/data/*.json`) лежит в Git — отдельный бэкап ему не нужен.

## Наблюдение

```bash
docker compose logs -f app       # запросы uvicorn, тайминги
docker compose logs -f caddy     # TLS, ACME, коды ответов
docker compose ps                # статус healthcheck
curl -s https://<DOMAIN>/api/news | python3 -m json.tool | head -40
```

Здоровье ленты видно в ответе `/api/news`: поле `online` и список
`failed_sources` — какие источники отвалились. Это штатная ситуация:
лента деградирует, а не падает.

## Диагностика

| Симптом | Причина и что делать |
|---|---|
| Сертификат не выпускается | 80-й порт закрыт файрволом либо `DOMAIN` не резолвится на этот сервер — проверьте `dig +short <DOMAIN>` и `docker compose logs caddy` |
| `caddy` рестартует | не заполнен `.env`: compose требует `DOMAIN` и `ACME_EMAIL` и падает с внятной ошибкой |
| Ссылка в мессенджере без картинки | `SITE_ORIGIN`/`DOMAIN` не совпадает с фактическим адресом — проверьте `curl -s https://<DOMAIN>/ \| grep og:image` |
| Лента всегда «офлайн» | с сервера нет исходящего HTTPS: `docker compose exec app python -c "import httpx;print(httpx.get('https://tass.ru/rss/v2.xml').status_code)"` |
| Приложение `unhealthy` | `docker compose logs app`; healthcheck дёргает `/api/health` каждые 60 с |
| Нужно встроить сайт в iframe | `CSP_FRAME_ANCESTORS='*'` в `.env` и `docker compose up -d` |

## Запуск без Caddy

Если HTTPS уже терминирует внешний балансировщик или nginx, поднимайте
только приложение:

```bash
docker build -t crimea-gid .
docker run -d --name crimea-gid -p 127.0.0.1:8000:8000 \
  -e SITE_ORIGIN=https://gid.example.ru \
  -v crimea-cache:/srv/cache crimea-gid
```

Прокси обязан передавать `X-Forwarded-Proto` и `X-Forwarded-Host` —
из них приложение собирает абсолютные `og:url`/`og:image`, когда
`SITE_ORIGIN` не задан.
