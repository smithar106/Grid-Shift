#!/usr/bin/env bash
set -euo pipefail

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
WORKERS="${WEB_CONCURRENCY:-1}"

if [[ -f "alembic.ini" ]]; then
  echo "gridshift: applying database migrations"
  attempt=1
  max_attempts=10
  until alembic upgrade head; do
    if (( attempt >= max_attempts )); then
      echo "gridshift: migrations failed after ${attempt} attempts" >&2
      exit 1
    fi
    echo "gridshift: migration attempt ${attempt} failed, retrying in 3s" >&2
    attempt=$(( attempt + 1 ))
    sleep 3
  done
fi

echo "gridshift: starting api on ${HOST}:${PORT}"
exec uvicorn app.main:app --host "${HOST}" --port "${PORT}" --workers "${WORKERS}" --proxy-headers --forwarded-allow-ips='*'
