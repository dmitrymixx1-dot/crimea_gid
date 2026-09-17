#!/usr/bin/env bash
# Бэкап файлового кэша ленты «Крым.Гид» (том news-cache → tar.gz).
#
#   deploy/backup-cache.sh                  # в ./backups
#   deploy/backup-cache.sh /srv/backups     # в указанный каталог
#   KEEP=30 deploy/backup-cache.sh          # хранить 30 последних копий
#
# Кэш — не критичные данные: при его потере лента просто сходит
# в источники заново. Бэкап нужен, чтобы после переезда сервера
# приложение сразу стартовало с наполненной лентой, а не с офлайн-снапшотом.
set -euo pipefail
cd "$(dirname "$0")/.."

DEST="${1:-backups}"
KEEP="${KEEP:-14}"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
ARCHIVE="$DEST/news-cache-$STAMP.tar.gz"

mkdir -p "$DEST"

# Читаем том через временный контейнер: сам сервис останавливать не нужно,
# файловый кэш пишется атомарно (запись во временный файл + rename).
docker compose run --rm --no-deps \
  --volume "$PWD/$DEST:/backup" \
  --entrypoint sh app \
  -c "tar -czf /backup/$(basename "$ARCHIVE") -C /srv/cache ." \
  >/dev/null

echo "✔ бэкап: $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"

# Ротация: оставляем KEEP последних архивов.
mapfile -t OLD < <(ls -1t "$DEST"/news-cache-*.tar.gz 2>/dev/null | tail -n "+$((KEEP + 1))")
if [ "${#OLD[@]}" -gt 0 ]; then
  rm -f "${OLD[@]}"
  echo "🧹 удалено старых копий: ${#OLD[@]} (храним $KEEP)"
fi
