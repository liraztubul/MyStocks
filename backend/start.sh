#!/bin/sh
# Container entrypoint (Render and docker compose). Render free has no pre-deploy hook, so
# migrations run here; alembic/env.py serializes concurrent runs with an advisory lock.
set -e
alembic upgrade head
# exec so uvicorn is PID 1 and receives the platform's SIGTERM directly on shutdown.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --no-server-header
