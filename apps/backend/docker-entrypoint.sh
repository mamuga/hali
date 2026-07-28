#!/bin/sh
# Applies pending migrations, then starts the API.
#
# Migrations are intentionally fail-closed: if `alembic upgrade head` fails the
# container exits non-zero and Railway keeps the previous deployment serving,
# rather than booting an API against a schema it does not match.
#
# Set RUN_MIGRATIONS=false to skip (e.g. when a second replica would race).
set -e

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  echo "[entrypoint] applying database migrations"
  alembic upgrade head
  echo "[entrypoint] migrations up to date"
else
  echo "[entrypoint] RUN_MIGRATIONS=false — skipping migrations"
fi

exec uvicorn hali.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers 1 \
  --log-level info
