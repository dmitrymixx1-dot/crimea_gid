#!/usr/bin/env bash
# Выкат релиза на сервере. Штатно запускается workflow
# .github/workflows/deploy.yml по SSH, но годится и для ручного обновления:
#
#   ./deploy/deploy.sh v1.9.0                            # выкатить тег
#   APP_DIR=/srv/crimea_gid ./deploy/deploy.sh v1.5.0    # откат на прошлый тег
#   ./deploy/deploy.sh --dry-run v1.9.0                  # репетиция выката
#
# Репетиция (--dry-run или DRY_RUN=1) проходит без сервера, без Docker и без
# сети: те же проверки, что и перед настоящим выкатом (ref существует, состав
# репозитория цел, скрипты синтаксически валидны, версия в коде совпадает
# с тегом), затем план — и ничего не меняется. Её гоняет CI на каждый push
# и шаг «Репетиция» в deploy.yml, поэтому сценарий выката проверен до того,
# как понадобятся живой сервер и секреты.
#
# Секретов и токенов не нужно: образ собирается из исходников на сервере,
# HTTPS поднимает Caddy (см. docs/deploy.md).
set -euo pipefail

DRY_RUN="${DRY_RUN:-0}"
REF=""
for arg in "$@"; do
  case "$arg" in
    --dry-run|-n) DRY_RUN=1 ;;
    -*) printf '[deploy] ошибка: неизвестный ключ %s\n' "$arg" >&2; exit 2 ;;
    *)
      if [ -n "$REF" ]; then
        printf '[deploy] ошибка: лишний аргумент %s\n' "$arg" >&2
        exit 2
      fi
      REF="$arg"
      ;;
  esac
done

APP_DIR="${APP_DIR:-/opt/crimea_gid}"
COMPOSE="${COMPOSE:-docker compose}"
# Healthcheck контейнера срабатывает раз в 60 с, поэтому ждём с запасом.
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-300}"
SLEEP_STEP="${SLEEP_STEP:-5}"
# Если задана — сверяем версию в ответе /api/health с ожидаемой:
# «выкат прошёл» ещё не значит «выкатилось то, что хотели».
EXPECT_VERSION="${EXPECT_VERSION:-}"
# Как вынимаем APP_VERSION из config.py: одна и та же регулярка в репетиции
# и в выкате, иначе они разойдутся молча.
VERSION_SED='s/^APP_VERSION = "\(.*\)"$/\1/p'

log() { printf '[deploy] %s\n' "$*"; }
warn() { printf '[deploy] внимание: %s\n' "$*" >&2; }
die() { printf '[deploy] ошибка: %s\n' "$*" >&2; exit 1; }
plan() { printf '[deploy] план: %s\n' "$*"; }

[ -n "$REF" ] || die "укажите тег или коммит: ./deploy/deploy.sh v1.9.0"
[ -d "$APP_DIR" ] || die "нет каталога приложения: $APP_DIR (задайте APP_DIR=...)"

cd "$APP_DIR"

# Теги вида v1.9.0 → ожидаемая версия 1.9.0 (без «v»); ветку версией
# не сверяем. Workflow считает то же самое — расходиться им нельзя.
case "$REF" in
  v*) EXPECT_VERSION="${EXPECT_VERSION:-${REF#v}}" ;;
esac

declared_version() {
  # В репетиции ref не выкатан, поэтому читаем файл прямо из объекта git;
  # в выкате рабочее дерево уже переключено на него.
  if [ "$DRY_RUN" = "1" ]; then
    git show "$REF:app/config.py" 2>/dev/null | sed -n "$VERSION_SED"
  else
    sed -n "$VERSION_SED" app/config.py
  fi
}

check_repo() {
  # Состав репозитория: без этих файлов выкатывать нечего.
  local f
  for f in Dockerfile docker-compose.yml deploy/Caddyfile deploy/deploy.sh \
           app/main.py app/config.py static/index.html; do
    [ -f "$f" ] || die "нет файла $f — репозиторий неполный"
  done
  # Синтаксис всех скриптов деплоя: их исполняет сервер, и опечатка
  # в одной строке стоит простоя.
  for f in deploy/*.sh; do
    bash -n "$f" || die "синтаксис $f не проверяется"
  done
  # ref обязан существовать в этом клоне — иначе выкат упадёт уже на сервере.
  git rev-parse --verify --quiet "$REF^{commit}" >/dev/null \
    || die "ref «$REF» не найден в репозитории (нужен git fetch --tags)"
  # Версия в коде обязана совпадать с тегом: иначе выкат «пройдёт»,
  # а на сервере окажется другой релиз. Проверяем до сборки, а не после.
  if [ -n "$EXPECT_VERSION" ]; then
    local declared
    declared="$(declared_version)"
    [ -n "$declared" ] || die "в $REF не нашёл APP_VERSION в app/config.py"
    [ "$declared" = "$EXPECT_VERSION" ] \
      || die "в $REF версия «$declared», ожидали «$EXPECT_VERSION»: тег не на том коммите"
    log "версия в исходниках: $declared"
  fi
  # .env compose требует DOMAIN и ACME_EMAIL; без них он падает на старте.
  # Жёстко не требуем: значения могут приходить и из окружения сервера.
  if [ -f .env ]; then
    grep -qs '^DOMAIN=' .env || warn "в .env нет DOMAIN — compose не поднимется"
    grep -qs '^ACME_EMAIL=' .env || warn "в .env нет ACME_EMAIL"
  elif [ -z "${DOMAIN:-}" ]; then
    warn "нет .env и DOMAIN в окружении — compose требует их для сертификата"
  fi
}

if [ "$DRY_RUN" = "1" ]; then
  log "репетиция выката $REF (ничего не меняем)"
  check_repo
  plan "git fetch --tags --force --prune"
  plan "git checkout --detach $REF"
  plan "$COMPOSE up -d --build"
  plan "жду healthy контейнера app (до ${HEALTH_TIMEOUT} с, шаг ${SLEEP_STEP} с)"
  if [ -n "$EXPECT_VERSION" ]; then
    plan "сверяю /api/health → version == $EXPECT_VERSION"
  fi
  plan "docker image prune -f"
  log "репетиция прошла: $REF в $APP_DIR"
  exit 0
fi

log "обновляем исходники до $REF"
git fetch --tags --force --prune
git checkout --detach "$REF"
check_repo

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
