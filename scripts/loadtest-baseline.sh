#!/usr/bin/env bash
# Single-replica latency baseline.
#
# Reproduces the numbers in docs/SCALABILITY.md §1.
# Usage:    scripts/loadtest-baseline.sh
# Output:   loadtest-results/YYYY-MM-DD/baseline.md
set -euo pipefail
cd "$(dirname "$0")/.."

API=${API:-http://localhost:8000}
DUR=${DUR:-30s}
RATE=${RATE:-200}
OUT="loadtest-results/$(date +%F)"
mkdir -p "$OUT"
REPORT="$OUT/baseline.md"

need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing: $1" >&2; exit 1; }; }
need curl

# Prefer vegeta. Fall back to a curl-based estimator.
if command -v vegeta >/dev/null 2>&1; then
  echo "→ Using vegeta @ ${RATE} rps for ${DUR}"
  # Warm caches
  curl -sf "$API/healthz" >/dev/null
  for q in Akello Otim Namuyanja Drici Asiimwe; do
    curl -sf "$API/api/v1/patients?q=$q" >/dev/null || true
  done

  TARGETS=$(mktemp)
  cat >"$TARGETS" <<EOF
GET ${API}/api/v1/patients?q=Akello
GET ${API}/api/v1/patients?q=Mbarara
GET ${API}/api/v1/facilities
GET ${API}/api/v1/supply/snapshot
GET ${API}/fhir/Patient?family=Akello
EOF

  vegeta attack -targets "$TARGETS" -rate="$RATE" -duration="$DUR" \
    | tee "$OUT/baseline.bin" \
    | vegeta report -type=text > "$OUT/baseline.txt"
  vegeta report -type=json < "$OUT/baseline.bin" > "$OUT/baseline.json"

  {
    echo "# HealthSync Uganda — Baseline load test"
    echo
    echo "_Generated $(date -Iseconds)_"
    echo
    echo "- Endpoint mix: patient search, facilities, supply snapshot, FHIR search"
    echo "- Target: \`$API\`"
    echo "- Rate: \`$RATE\` rps for \`$DUR\`"
    echo
    echo '```'
    cat "$OUT/baseline.txt"
    echo '```'
  } > "$REPORT"
else
  echo "vegeta not found — running curl-based estimator (lower fidelity)"
  echo "Install vegeta for production-quality numbers: https://github.com/tsenart/vegeta"
  HITS=200
  OK=0
  TOTAL=0
  TIMES=""
  for ((i=0;i<HITS;i++)); do
    T=$(curl -sf -o /dev/null -w "%{time_total}" "$API/api/v1/patients?q=Akello") || continue
    OK=$((OK+1))
    TIMES="$TIMES $T"
  done
  {
    echo "# HealthSync Uganda — Baseline load test (curl estimator)"
    echo "_Install vegeta for production-quality runs._"
    echo
    echo "- $OK/$HITS requests succeeded"
    echo "- Sample times (s): $TIMES"
  } > "$REPORT"
fi

echo "✓ Report: $REPORT"
