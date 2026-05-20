#!/usr/bin/env bash
# Bring up Postgres + Redis for local development.
# Backend and frontend run on the host (`uv run uvicorn`, `bun run dev`).
set -euo pipefail

cd "$(dirname "$0")/.."

if ! command -v docker >/dev/null 2>&1; then
  echo "✗ docker not found. Install Docker Desktop or Docker Engine first." >&2
  exit 1
fi

echo "→ Starting Postgres + Redis (Docker)…"
docker compose up -d postgres redis

echo "→ Waiting for Postgres & Redis to report healthy…"
for svc in postgres redis; do
  attempts=0
  until [ "$(docker inspect --format '{{.State.Health.Status}}' "healthsync-uganda-${svc}-1" 2>/dev/null || echo starting)" = "healthy" ]; do
    attempts=$((attempts+1))
    if [ "$attempts" -gt 30 ]; then
      echo "✗ ${svc} did not become healthy in 60s." >&2
      docker compose logs "$svc" | tail -20
      exit 1
    fi
    sleep 2
  done
  echo "  ✓ ${svc} healthy"
done

cat <<'EOF'

╭──────────────────────────────────────────────────────────────────────╮
│  Postgres + Redis are up.                                            │
│                                                                      │
│  Next:                                                               │
│    cd backend                                                        │
│    uv sync                                                           │
│    uv run python -m app.seed.run         # one-time, idempotent      │
│    uv run uvicorn app.main:app --reload --port 8000                  │
│                                                                      │
│  In another shell:                                                   │
│    cd frontend                                                       │
│    bun install                                                       │
│    bun run dev                                                       │
│                                                                      │
│  Stop the stack:                                                     │
│    docker compose down                                               │
╰──────────────────────────────────────────────────────────────────────╯
EOF
