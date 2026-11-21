#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
docker compose up -d --wait --wait-timeout 90
.venv/bin/python -m backend.cli migrate
if [ ! -f frontend/dist/index.html ]; then
    npm --prefix frontend ci
    npm --prefix frontend run build
fi
exec .venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8001
