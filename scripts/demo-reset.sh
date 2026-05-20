#!/usr/bin/env bash
# Reset the demo to a known-clean state, then re-seed.
# Useful between rehearsal runs of docs/DEMO_SCRIPT.md.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "→ Dropping and recreating the healthsync database…"
docker compose exec -T postgres \
  psql -U "${POSTGRES_USER:-healthsync}" -d postgres -c \
  "DROP DATABASE IF EXISTS ${POSTGRES_DB:-healthsync}; CREATE DATABASE ${POSTGRES_DB:-healthsync};"

echo "→ Flushing Redis DB…"
docker compose exec -T redis redis-cli FLUSHDB

echo "→ Re-seeding demo data…"
cd backend
uv run python -m app.seed.run

echo
echo "✓ Demo state reset. Restart the API to pick up the schema."
