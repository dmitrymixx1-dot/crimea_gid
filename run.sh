#!/usr/bin/env bash
# Запуск «Крым.Гид»
#   ./run.sh          — с автоперезагрузкой при правках кода (dev)
#   ./run.sh prod     — без автоперезагрузки
set -euo pipefail
cd "$(dirname "$0")"

PY=".venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "Создаю виртуальное окружение…"
  python3 -m venv .venv
  .venv/bin/pip install --quiet --upgrade pip
  .venv/bin/pip install --quiet -r requirements.txt
fi

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

if [ "${1:-}" = "prod" ]; then
  exec "$PY" -m uvicorn app.main:app --host "$HOST" --port "$PORT"
else
  exec "$PY" -m uvicorn app.main:app --host "$HOST" --port "$PORT" --reload
fi
