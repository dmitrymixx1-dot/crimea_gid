#!/usr/bin/env bash
# Выкат релиза на сервере. Штатно запускается workflow
# .github/workflows/deploy.yml по SSH, но годится и для ручного обновления:
#
#   ./deploy/deploy.sh v1.6.0                     # выкатить тег
#   APP_DIR=/srv/crimea_gid ./deploy/deploy.sh v1.5.0   # откат на прошлый тег
#
# Секретов и токенов не нужно: образ собирается из исходников на сервере,
# HTTPS поднимает Caddy (см. docs/deploy.md).
set -euo pipefail

REF="${1:-}"
APP_DIR="${APP_DIR:-/opt/crimea_gid}"
COMPOSE="${COMPOSE:-docker compose}"
# Healthcheck контейнера срабатывает раз в 60 с, поэтому ждём с запасом.
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-300}"
SLEEP_STEP="${SLEEP_STEP:-5}"
# Если задана — сверяем версию в ответе /api/health с ожидаемой:
# «выкат прошёл» ещё не значит «выкатилось то, что хотели».
EXPECT_VERSION="${EXPECT_VERSION:-}"

log() { printf '[deploy] %s\n' "$*"; }
die() { printf '[deploy] ошибка: %s\n' "$*" >&2; exit 1; }

[ -n "$REF" ] || die "укажите тег или коммит: ./deploy/deploy.sh v1.6.0"
[ -d "$APP_DIR" ] || die "нет каталога приложения: $APP_DIR (задайте APP_DIR=...)"

cd "$APP_DIR"

log "обновляем исходники до $REF"
git fetch --tags --force --prune
git checkout --detach "$REF"

log "собираем и поднимаем контейнеры"
$COMPOSE up -d --build

log "ждём здорового приложения (до ${HEALTH_TIMEOUT} с)"
container="$($COMPOSE ps -q app)"
[ -n "$container" ] || die "контейнер app не запущен: $COMPOSE ps"

status=""
deadline=$(( $(date +%s) + HEALTH_TIMEOUT ))
while [ "$(date +%s)" -lt "$deadline" ]; do
  status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container" 2>/dev/null || echo missing)"
  case "$status" in
    healthy) break ;;
    unhealthy) die "healthcheck не прошёл: $COMPOSE logs app" ;;
  esac
  sleep "$SLEEP_STEP"
done
[ "$status" = "healthy" ] || die "не дождались healthy за ${HEALTH_TIMEOUT} с"

if [ -n "$EXPECT_VERSION" ]; then
  actual="$($COMPOSE exec -T app python -c "import json, urllib.request; print(json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=5))['version'])" || echo "нет ответа")"
  [ "$actual" = "$EXPECT_VERSION" ] \
    || die "на сервере версия «$actual», ожидали «$EXPECT_VERSION»"
  log "версия на сервере: $actual"
fi

log "подчищаем старые слои образа"
docker image prune -f >/dev/null 2>&1 || true

log "готово: $(git describe --tags --always 2>/dev/null || echo "$REF")"
