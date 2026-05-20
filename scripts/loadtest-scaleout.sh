#!/usr/bin/env bash
# Demonstrates linear scale-out: 1 replica → 2 replicas → 3 replicas.
# Requires docker compose + vegeta.
set -euo pipefail
cd "$(dirname "$0")/.."

API=${API:-http://localhost:8000}
DUR=${DUR:-20s}
RATE=${RATE:-300}
OUT="loadtest-results/$(date +%F)"
mkdir -p "$OUT"
REPORT="$OUT/scaleout.md"

if ! command -v vegeta >/dev/null 2>&1; then
  echo "vegeta required: https://github.com/tsenart/vegeta" >&2
  exit 1
fi

{
  echo "# HealthSync Uganda — Scale-out test"
  echo "_Generated $(date -Iseconds)_"
  echo
  echo "Rate: \`$RATE\` rps, duration: \`$DUR\`, target: \`$API/api/v1/patients?q=Akello\`"
  echo
} > "$REPORT"

for N in 1 2 3; do
  echo "→ Scaling backend to $N replicas..."
  docker compose --profile full up -d --scale backend="$N"
  sleep 5
  until curl -sf "$API/healthz" >/dev/null; do sleep 1; done

  echo "→ Attacking at $RATE rps for $DUR..."
  echo "GET $API/api/v1/patients?q=Akello" | \
    vegeta attack -rate="$RATE" -duration="$DUR" \
    | vegeta report -type=text > "$OUT/scaleout-$N.txt"

  {
    echo "## $N replica$([ "$N" -gt 1 ] && echo s)"
    echo '```'
    cat "$OUT/scaleout-$N.txt"
    echo '```'
    echo
  } >> "$REPORT"
done

# Restore to 1 replica
docker compose --profile full up -d --scale backend=1

echo "✓ Report: $REPORT"
