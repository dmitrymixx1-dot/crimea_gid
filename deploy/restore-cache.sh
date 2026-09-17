#!/usr/bin/env bash
# Восстановление кэша ленты «Крым.Гид» из архива, снятого backup-cache.sh.
#
#   deploy/restore-cache.sh backups/news-cache-20260917-101500.tar.gz
#
# После восстановления приложение перезапускается: кэш читается
# при первом обращении к ленте, но рестарт снимает и кэш в памяти.
set -euo pipefail
cd "$(dirname "$0")/.."

ARCHIVE="${1:?укажите путь к архиву: deploy/restore-cache.sh backups/news-cache-*.tar.gz}"
[ -f "$ARCHIVE" ] || { echo "нет файла: $ARCHIVE" >&2; exit 1; }

DIR="$(cd "$(dirname "$ARCHIVE")" && pwd)"
NAME="$(basename "$ARCHIVE")"

docker compose run --rm --no-deps \
  --volume "$DIR:/backup:ro" \
  --entrypoint sh app \
  -c "rm -rf /srv/cache/* && tar -xzf /backup/$NAME -C /srv/cache" \
  >/dev/null

docker compose restart app
echo "✔ кэш восстановлен из $ARCHIVE, приложение перезапущено"
