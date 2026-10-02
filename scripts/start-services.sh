#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[[ -f .env ]] || { echo 'Run python3 scripts/generate-env.py first.' >&2; exit 1; }
docker compose config --quiet
docker compose build
docker compose up -d --wait postgres redis appium
docker compose run --rm --no-deps gateway-api python -m alembic upgrade head
docker compose run --rm --no-deps gateway-api python -m scripts.bootstrap_instance
docker compose up -d gateway-api worker dispatcher
echo 'API: http://127.0.0.1:8000/docs'
