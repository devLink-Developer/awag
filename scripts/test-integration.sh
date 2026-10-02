#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export TEST_DB_PASSWORD
TEST_DB_PASSWORD=$(python -c 'import secrets; print(secrets.token_hex(32))')
export TEST_DATABASE_URL="postgresql+psycopg://gateway_test:$TEST_DB_PASSWORD@127.0.0.1:55432/gateway_test"
export TEST_REDIS_URL=redis://127.0.0.1:56379/0
trap 'docker compose -p whatsapp-gateway-tests -f tests/compose.yml down --volumes' EXIT
docker compose -p whatsapp-gateway-tests -f tests/compose.yml up -d --wait
python -m pytest -q
