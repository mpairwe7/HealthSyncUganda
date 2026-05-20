#!/usr/bin/env bash
# Pre-flight check before the 25 June showcase. Run from the repo root.
# Verifies that every load-bearing service is up and answering.
set -uo pipefail

API=${API:-http://localhost:8000}
WEB=${WEB:-http://localhost:3000}

pass() { printf "  \033[32m✓\033[0m %s\n" "$1"; }
fail() { printf "  \033[31m✗\033[0m %s\n" "$1"; FAIL=1; }
section() { printf "\n\033[1m%s\033[0m\n" "$1"; }

FAIL=0

section "Backend"
if curl -sf "$API/healthz" >/dev/null; then pass "healthz"; else fail "healthz unreachable at $API"; fi
READYZ=$(curl -s -w '\n%{http_code}' "$API/readyz")
CODE=$(echo "$READYZ" | tail -1)
BODY=$(echo "$READYZ" | head -n -1)
if [ "$CODE" = "200" ]; then
  pass "readyz (Redis + DB both healthy)"
else
  fail "readyz returned $CODE — $BODY"
fi

section "FHIR R4 surface"
META=$(curl -sf "$API/fhir/metadata")
if echo "$META" | grep -q '"resourceType":"CapabilityStatement"'; then
  pass "CapabilityStatement reachable"
else
  fail "CapabilityStatement missing"
fi

section "Auth"
TOKEN=$(curl -sf -X POST "$API/api/v1/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"identifier":"admin","password":"admin1234"}' \
  | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')
if [ -n "$TOKEN" ]; then pass "admin login"; else fail "admin login failed — did you run the seed?"; fi

section "Circuit breakers"
CIRCUITS=$(curl -sf -H "Authorization: Bearer $TOKEN" "$API/api/v1/interop/circuits")
if echo "$CIRCUITS" | grep -q '"state":"open"'; then
  fail "one or more breakers are OPEN — reset before the show"
  echo "$CIRCUITS"
else
  pass "all breakers closed"
fi

section "Frontend"
if curl -sf -o /dev/null "$WEB/"; then pass "landing page renders"; else fail "frontend not reachable at $WEB"; fi
if curl -sf -o /dev/null "$WEB/citizen/login"; then pass "citizen login page"; else fail "citizen login not reachable"; fi

if [ "$FAIL" -eq 0 ]; then
  printf "\n\033[32m✓ Pre-flight green. Ready to demo.\033[0m\n"
  exit 0
else
  printf "\n\033[31m✗ Pre-flight RED. Fix the items above before going live.\033[0m\n"
  exit 1
fi
