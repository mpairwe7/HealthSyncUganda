#!/usr/bin/env bash
# Demonstrates Redis cache effectiveness on analytics endpoints.
# Compares cold vs warm response time for /api/v1/analytics/encounters-by-district.
set -euo pipefail
cd "$(dirname "$0")/.."

API=${API:-http://localhost:8000}
OUT="loadtest-results/$(date +%F)"
mkdir -p "$OUT"
REPORT="$OUT/analytics.md"

# Admin login (seed must have been run)
TOKEN=$(curl -sf -X POST "$API/api/v1/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"identifier":"admin","password":"admin1234"}' \
  | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')

if [ -z "$TOKEN" ]; then
  echo "✗ Admin login failed. Did you run 'make seed' first?" >&2
  exit 1
fi

# Bust the cache
docker compose exec -T redis redis-cli FLUSHDB >/dev/null 2>&1 || true

URL="$API/api/v1/analytics/encounters-by-district?since_days=30"

cold=$(curl -sf -o /dev/null -w "%{time_total}" -H "Authorization: Bearer $TOKEN" "$URL")
warm1=$(curl -sf -o /dev/null -w "%{time_total}" -H "Authorization: Bearer $TOKEN" "$URL")
warm2=$(curl -sf -o /dev/null -w "%{time_total}" -H "Authorization: Bearer $TOKEN" "$URL")
warm3=$(curl -sf -o /dev/null -w "%{time_total}" -H "Authorization: Bearer $TOKEN" "$URL")

{
  echo "# Analytics cache effectiveness"
  echo "_Generated $(date -Iseconds)_"
  echo
  echo "Endpoint: \`$URL\`"
  echo
  echo "| Request | Time (s) | Cache state |"
  echo "|---|---|---|"
  echo "| 1 — cold | $cold | MISS (Redis just flushed) |"
  echo "| 2 — warm | $warm1 | HIT |"
  echo "| 3 — warm | $warm2 | HIT |"
  echo "| 4 — warm | $warm3 | HIT |"
  echo
  echo "_Cache TTL: 60 seconds (set in \`app/api/v1/analytics.py\`)._"
} > "$REPORT"

echo "✓ Report: $REPORT"
