#!/usr/bin/env bash
# FHIR R4 conformance smoke-test for the HealthSync Uganda API.
#
# Verifies that the publicly-documented FHIR resources round-trip through the
# API and conform to the Uganda Implementation Guide profiles. Designed to run
# in CI and on a clean local dev stack.
#
# Exit status:
#   0   all checks passed
#   ≥1  number of failing checks
#
# Requirements: curl, jq
set -euo pipefail
cd "$(dirname "$0")/.."

API=${API:-http://localhost:8000}
OUT="conformance-results/$(date +%F)"
mkdir -p "$OUT"
REPORT="$OUT/fhir-conformance.md"
FAIL=0
PASS=0

red()   { printf '\033[31m%s\033[0m' "$*"; }
green() { printf '\033[32m%s\033[0m' "$*"; }
yel()   { printf '\033[33m%s\033[0m' "$*"; }

note() { printf '%s\n' "$*" >> "$REPORT"; }
row()  { printf '| %s | %s | %s |\n' "$1" "$2" "$3" >> "$REPORT"; }

check() {
  local name="$1"; shift
  local cond="$1"; shift
  local detail="${1:-}"
  if eval "$cond"; then
    PASS=$((PASS+1))
    printf '  %s %s\n' "$(green '✓')" "$name"
    row "$name" "✅ pass" "$detail"
  else
    FAIL=$((FAIL+1))
    printf '  %s %s — %s\n' "$(red '✗')" "$name" "$detail"
    row "$name" "❌ fail" "$detail"
  fi
}

require() {
  command -v "$1" >/dev/null 2>&1 || { echo "Missing dep: $1" >&2; exit 127; }
}
require curl
require jq

{
  echo "# FHIR R4 conformance report"
  echo "_Generated $(date -Iseconds) against \`$API\`_"
  echo
  echo "| Check | Result | Detail |"
  echo "|---|---|---|"
} > "$REPORT"

# ---------------------------------------------------------------------------
# 0. Capability statement
# ---------------------------------------------------------------------------
echo
echo "→ 0. Capability statement"
META=$(curl -sf "$API/fhir/metadata" || echo '')
check "metadata endpoint reachable" "[ -n '$META' ]" "GET /fhir/metadata"
check "resourceType is CapabilityStatement" \
  "[ \"$(echo \"$META\" | jq -r .resourceType 2>/dev/null)\" = 'CapabilityStatement' ]" \
  "FHIR R4 §2.1"
check "fhirVersion is 4.0.x" \
  "echo \"$META\" | jq -r .fhirVersion | grep -q '^4\\.0\\.'" \
  "FHIR R4"
check "format includes application/fhir+json" \
  "echo \"$META\" | jq -r '.format[]' | grep -q 'application/fhir+json'" \
  ""

# ---------------------------------------------------------------------------
# 1. Auth — most clinical reads require it
# ---------------------------------------------------------------------------
echo
echo "→ 1. Acquire admin token"
TOKEN=$(curl -sf -X POST "$API/api/v1/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"identifier":"admin","password":"admin1234"}' \
  | jq -r .access_token 2>/dev/null || echo '')
check "admin login returns a token" "[ -n '$TOKEN' ] && [ '$TOKEN' != 'null' ]" \
  "POST /api/v1/auth/login"

H_AUTH=(-H "Authorization: Bearer $TOKEN")

# ---------------------------------------------------------------------------
# 2. Patient — Uganda NIN profile
# ---------------------------------------------------------------------------
echo
echo "→ 2. Patient (Uganda NIN profile)"
PT=$(curl -sf "${H_AUTH[@]}" "$API/fhir/Patient?identifier=https://nira.go.ug/identifiers/nin|CM85051712345X" || echo '')
check "Patient search returns a Bundle" \
  "[ \"$(echo \"$PT\" | jq -r .resourceType 2>/dev/null)\" = 'Bundle' ]" \
  "Bundle.type=searchset"
check "Bundle.type is searchset" \
  "[ \"$(echo \"$PT\" | jq -r .type 2>/dev/null)\" = 'searchset' ]" \
  ""
check "At least one Patient with NIN slice" \
  "echo \"$PT\" | jq -e '.entry[]?.resource | select(.resourceType==\"Patient\") | .identifier[] | select(.system==\"https://nira.go.ug/identifiers/nin\")' >/dev/null 2>&1" \
  "system=https://nira.go.ug/identifiers/nin"
check "Patient has structured name" \
  "echo \"$PT\" | jq -e '.entry[0].resource.name[0].family' >/dev/null 2>&1" \
  "HumanName.family present"

# ---------------------------------------------------------------------------
# 3. Encounter — search by patient ref
# ---------------------------------------------------------------------------
echo
echo "→ 3. Encounter"
PID=$(echo "$PT" | jq -r '.entry[0].resource.id' 2>/dev/null || echo '')
check "Patient.id resolved" "[ -n '$PID' ] && [ '$PID' != 'null' ]" "for follow-up queries"
ENC=$(curl -sf "${H_AUTH[@]}" "$API/fhir/Encounter?patient=$PID" || echo '')
check "Encounter search returns a Bundle" \
  "[ \"$(echo \"$ENC\" | jq -r .resourceType 2>/dev/null)\" = 'Bundle' ]" ""
check "Encounter entries have a class coding" \
  "echo \"$ENC\" | jq -e '.entry[]?.resource | select(.resourceType==\"Encounter\") | .class.code' >/dev/null 2>&1" \
  "v3 ActCode"
check "Encounter references the patient" \
  "echo \"$ENC\" | jq -e --arg p \"Patient/$PID\" '.entry[]?.resource | select(.subject.reference==\\\$p)' >/dev/null 2>&1" \
  "subject.reference"

# ---------------------------------------------------------------------------
# 4. Observation — vitals + immunisations
# ---------------------------------------------------------------------------
echo
echo "→ 4. Observation"
OBS=$(curl -sf "${H_AUTH[@]}" "$API/fhir/Observation?patient=$PID&_count=5" || echo '')
check "Observation Bundle present" \
  "[ \"$(echo \"$OBS\" | jq -r .resourceType 2>/dev/null)\" = 'Bundle' ]" ""
check "At least one Observation with LOINC code" \
  "echo \"$OBS\" | jq -e '.entry[]?.resource | select(.resourceType==\"Observation\") | .code.coding[] | select(.system==\"http://loinc.org\")' >/dev/null 2>&1" \
  "LOINC"

# ---------------------------------------------------------------------------
# 5. Immunization — Uganda EPI schedule
# ---------------------------------------------------------------------------
echo
echo "→ 5. Immunization"
IMM=$(curl -sf "${H_AUTH[@]}" "$API/fhir/Immunization?patient=$PID" || echo '')
check "Immunization Bundle present" \
  "[ \"$(echo \"$IMM\" | jq -r .resourceType 2>/dev/null)\" = 'Bundle' ]" ""
check "Immunization has vaccineCode" \
  "echo \"$IMM\" | jq -e '.entry[]?.resource | select(.resourceType==\"Immunization\") | .vaccineCode.coding[0].code' >/dev/null 2>&1" \
  "CVX or Uganda EPI"

# ---------------------------------------------------------------------------
# 6. Round-trip: create → read → search
# ---------------------------------------------------------------------------
echo
echo "→ 6. Round-trip"
NEW_OBS_BODY='{
  "resourceType":"Observation",
  "status":"final",
  "code":{"coding":[{"system":"http://loinc.org","code":"8867-4","display":"Heart rate"}]},
  "subject":{"reference":"Patient/'"$PID"'"},
  "valueQuantity":{"value":78,"unit":"beats/min","system":"http://unitsofmeasure.org","code":"/min"}
}'
CREATED=$(curl -sf "${H_AUTH[@]}" -H 'Content-Type: application/fhir+json' \
  -X POST -d "$NEW_OBS_BODY" "$API/fhir/Observation" || echo '')
NEW_ID=$(echo "$CREATED" | jq -r .id 2>/dev/null || echo '')
check "POST Observation returns an id" "[ -n '$NEW_ID' ] && [ '$NEW_ID' != 'null' ]" \
  "Observation/$NEW_ID"
READ=$(curl -sf "${H_AUTH[@]}" "$API/fhir/Observation/$NEW_ID" || echo '')
check "GET Observation/{id} returns the same id" \
  "[ \"$(echo \"$READ\" | jq -r .id 2>/dev/null)\" = '$NEW_ID' ]" "read-back"
check "Observation has a meta.lastUpdated" \
  "echo \"$READ\" | jq -e '.meta.lastUpdated' >/dev/null 2>&1" "auditable"

# ---------------------------------------------------------------------------
# 7. Negative tests — the server should reject obvious garbage
# ---------------------------------------------------------------------------
echo
echo "→ 7. Negative tests"
BAD_STATUS=$(curl -s -o /dev/null -w '%{http_code}' "${H_AUTH[@]}" \
  -H 'Content-Type: application/fhir+json' \
  -X POST -d '{"resourceType":"Observation"}' "$API/fhir/Observation")
check "POST without required fields returns 4xx" \
  "[ '${BAD_STATUS:0:1}' = '4' ]" "got HTTP $BAD_STATUS"

UNAUTH_STATUS=$(curl -s -o /dev/null -w '%{http_code}' "$API/fhir/Patient")
check "Unauthenticated FHIR read returns 401/403" \
  "[ '$UNAUTH_STATUS' = '401' ] || [ '$UNAUTH_STATUS' = '403' ]" \
  "got HTTP $UNAUTH_STATUS"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
{
  echo
  echo "## Summary"
  echo
  echo "- Passed: **$PASS**"
  echo "- Failed: **$FAIL**"
} >> "$REPORT"

echo
echo "─────────────────────────────"
if [ "$FAIL" -eq 0 ]; then
  printf '%s %d checks passed\n' "$(green ✓)" "$PASS"
else
  printf '%s %d passed, %d failed\n' "$(red ✗)" "$PASS" "$FAIL"
fi
echo "Report: $REPORT"

exit "$FAIL"
