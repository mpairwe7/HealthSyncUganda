# Testing strategy

**Audience:** engineering reviewers, audit reviewers, contributors.
**Last reviewed:** 2026-05-20.

The premise: in a health system, tests are the smallest unit of trust. Every requirement in [REQUIREMENTS.md](./REQUIREMENTS.md) has a verification method (`V:`) pointing here.

This document explains *what* we test, *how*, *what we deliberately do not*, and *what coverage we expect*.

---

## 1. The test pyramid

We do not subscribe dogmatically to the pyramid, but the shape matters:

```
                 ┌──────────────────────┐
                 │  Manual / Clinical   │   nurse rehearsal, partner walk-through
                 ├──────────────────────┤
                 │   End-to-end demo    │   scripts/preflight.sh (12 steps)
                 ├──────────────────────┤
                 │  Contract tests      │   FHIR conformance, OpenAPI snapshot
                 ├──────────────────────┤
                 │  Integration tests   │   pytest + sqlite + real Redis
                 ├──────────────────────┤
                 │     Unit tests       │   pytest (backend), bun test (frontend)
                 └──────────────────────┘
```

The intent: keep the bottom of the pyramid fast (< 30 s) so contributors run it before every commit, and keep the top of the pyramid honest (real workflows on real-shaped data).

---

## 2. Backend tests

### 2.1 Stack

- **pytest** + **pytest-asyncio**
- **httpx** AsyncClient as the test HTTP transport
- **aiosqlite** as the test database (transient, one schema per test session)
- **fakeredis** for unit tests; **real Redis** (`db=15`) for integration tests
- **pytest-cov** for coverage

### 2.2 Layout

```
backend/tests/
├── conftest.py              # fixtures: app, db, redis, tokens
├── unit/
│   ├── test_fhir_validator.py
│   ├── test_resilience.py
│   ├── test_security.py
│   ├── test_supply_ledger.py
│   └── test_idempotency.py
├── integration/
│   ├── test_auth_flow.py
│   ├── test_patient_crud.py
│   ├── test_encounter_idempotent.py
│   ├── test_consent_lifecycle.py
│   └── test_supply_transfer.py
└── contract/
    └── test_openapi_snapshot.py
```

(File names above describe the layout; some are in flight in this prototype build — pull `backend/tests/` for the live set.)

### 2.3 Run

```bash
make test                           # default — fast suite
cd backend
uv run pytest --cov=app             # with coverage
uv run pytest -k "consent"          # filter by name
uv run pytest -x -vv                # stop on first failure, verbose
```

CI runs the full suite in ~3 minutes on a clean cache.

### 2.4 What we test

| Concern                                | Test                                                    | Why it matters                                                |
| -------------------------------------- | ------------------------------------------------------- | ------------------------------------------------------------- |
| FHIR Patient profile compliance        | `test_fhir_validator.py`                                | The NIN slice is a national identifier requirement.           |
| Idempotency replay (offline → online)  | `test_encounter_idempotent.py`                          | Duplicate writes are a patient-safety bug.                    |
| Hash-chain integrity                   | `test_supply_ledger.py::test_verify_detects_tamper`     | The whole point of ADR 0004.                                  |
| Circuit breaker state transitions      | `test_resilience.py::test_closed_open_halfopen_closed`  | Resilience is the differentiator.                             |
| Audit log written on every PHI read    | `test_patient_crud.py::test_read_logs_audit`            | DPPA 2019 requires it. Untested means unverifiable.           |
| Consent revocation is immediate        | `test_consent_lifecycle.py::test_revoke_blocks_read`    | DPPA Part V right.                                            |
| Role enforcement at the API boundary   | `test_auth_flow.py::test_citizen_cannot_admin`          | A bypass here is the worst class of bug.                      |
| OpenAPI spec stability                 | `test_openapi_snapshot.py`                              | Partners rely on the spec. Silent breakage is forbidden.      |

### 2.5 Coverage target

Per [NFR-070](./REQUIREMENTS.md#38-maintainability): **≥ 70 %** statement coverage across `backend/app`. CI fails below this threshold.

We do not chase 100 %. Coverage is a *floor*, not a *goal*. Tests that exist to bump coverage are deleted.

### 2.6 Test data

- Synthetic NINs use the format `CM0000000000NNN` reserved for testing.
- Synthetic citizens carry the surname `TestPatient` to make them easy to filter out of analytics.
- Synthetic drugs use a `TEST-` prefix on the EMHSLU code field.

**Real patient data is never used in tests.** Code reviewers reject any test that imports a CSV from a production export.

---

## 3. Frontend tests

### 3.1 Stack

- **bun test** for unit tests (Bun's built-in Jest-compatible runner — no Vitest, no Jest install).
- **Testing Library** (`@testing-library/react`) for component tests.
- **MSW (Mock Service Worker)** for mocking the backend in component and integration tests.
- **Playwright** (planned) for browser-driven E2E. Not in the showcase build; tracked.

### 3.2 What we test (today)

- The i18n harness: every English key resolves in Luganda; `useT()` panics outside the provider.
- The offline queue: enqueue → drain → idempotency-key dedup → server reject handling.
- Status badges: `kind=*` resolves to the documented icon + label.

### 3.3 Type safety as a test

`bun run typecheck` is the most-run "test" in the frontend. With strict mode and the typed i18n dictionary, missing translations or schema drifts fail the build, not the runtime.

### 3.4 Accessibility tests

- **axe-core** smoke run via `bun run a11y` (CI). Failures block merge for `serious` and `critical` violations.
- Manual screen-reader pass (VoiceOver, TalkBack) before every release of the citizen portal.
- Lighthouse CI runs on the citizen landing + record view; budgets in `frontend/lighthouserc.json`.

---

## 4. Contract tests

### 4.1 FHIR conformance

`scripts/fhir-conformance.sh` runs 18 checks against a live instance:

- Capability statement present and advertises FHIR 4.0.x.
- Patient search returns a `Bundle` with the NIN slice on the Uganda profile.
- Encounter/Observation/Immunization searches return `Bundle` shapes with the documented references.
- POST → GET round-trip on `Observation`.
- Negative tests: malformed body → 4xx; unauthenticated read → 401/403.

Output is a Markdown report at `conformance-results/<date>/fhir-conformance.md`. CI publishes the latest as a build artefact and fails on any failed check.

### 4.2 OpenAPI snapshot

`backend/tests/contract/test_openapi_snapshot.py` re-renders `/openapi.json` and diffs against a checked-in snapshot. Any breaking change requires:

1. Updating the snapshot deliberately in the same PR.
2. Updating [API.md](./API.md).
3. Linking the relevant ADR (if breaking) or CHANGELOG entry (if additive).

---

## 5. Load and resilience tests

### 5.1 Baseline

`scripts/loadtest-baseline.sh` — single backend replica, sustained `vegeta` attack on `/api/v1/patients?q=...`. Captures p50/p95/p99 latency, success rate, throughput.

### 5.2 Scale-out

`scripts/loadtest-scaleout.sh` — 1 → 2 → 3 replicas, same workload. Verifies near-linear throughput scaling (NFR-010).

### 5.3 Cache effectiveness

`scripts/loadtest-analytics.sh` — cold/warm response time comparison on `/api/v1/analytics/encounters-by-district`. Confirms the Redis cache shaves the response time by an order of magnitude.

Reports land in `loadtest-results/<date>/*.md`.

### 5.4 Chaos / breaker drills

Not a script today; a manual drill before every showcase:

1. Trip the DHIS2 breaker (`POST /api/v1/interop/circuits/dhis2/trip`).
2. Submit five encounters. Expect them to persist with no user-visible degradation.
3. Wait 30 s. Observe the breaker transition to half-open and then closed.
4. Confirm the DHIS2 outbox depth drained to zero.

This drill is part of `scripts/preflight.sh`.

---

## 6. Manual & clinical tests

Automated tests cannot tell us if a clinical workflow makes sense in a Ugandan HC III. We supplement with:

- **Nurse rehearsals** at Lacor and Gulu HC III before every release of the worker portal. A nurse performs the 6-task script in `docs/clinical/nurse_rehearsal.md` (in flight).
- **Pharmacist rehearsals** at Mbarara RRH for the supply flow.
- **Citizen usability sessions** for the language switch and consent flow. The user count is small (≤ 8) by design — health usability is qualitative.

Findings are filed as issues with the `clinical-review` label and triaged with the clinical lead within five working days.

---

## 7. Security tests

- **Dependency scanning** — `uv run pip-audit` (backend), `bunx npm audit` (frontend). CI fails on `high` and `critical`.
- **Static analysis** — ruff with security rules enabled (`S` codes), bandit on critical paths, eslint `eslint-plugin-security` on the frontend.
- **Secret scanning** — gitleaks pre-commit + CI. The whole `.env` family is gitignored.
- **Penetration testing** — planned with NITA-U's CERT once the pilot is greenlit. The engagement uses a dedicated staging environment with synthetic data only.

---

## 8. What we deliberately do not test

- We do not have UI snapshot tests. They produce false positives that erode trust and discourage refactoring. Visual regressions are caught by manual review and Storybook (planned).
- We do not test private functions. If a private function is interesting enough to test, it deserves a public boundary.
- We do not run tests against production. Production is for production traffic.
- We do not mock the database in integration tests (per the user instruction recorded in CONTRIBUTING). Mocks have lied to us before; SQLite-or-real-Postgres has not.

---

## 9. CI matrix

| Pipeline           | When            | Steps                                                                                  |
| ------------------ | --------------- | -------------------------------------------------------------------------------------- |
| **PR check**       | on PR open + push | typecheck, lint, unit + integration tests, contract tests, FHIR conformance smoke.    |
| **Main**           | on merge to main | full PR pipeline + load-test baseline + publish container images.                      |
| **Nightly**        | 02:00 UTC       | full load-test suite + dependency audit + ledger verification on staging.              |
| **Release**        | on tag          | end-to-end (preflight) + publish signed images + generate SBOM.                        |

Pipelines are GitHub Actions; the workflow files live under `.github/workflows/` (forthcoming).

---

## 10. Verification matrix (recap)

| Requirement family   | Verification                                                            |
| -------------------- | ----------------------------------------------------------------------- |
| FR-001 … FR-082      | pytest unit + integration suite                                         |
| FR-014 / FR-052      | `scripts/fhir-conformance.sh`                                           |
| FR-041 / FR-045      | `backend/tests/test_supply_ledger.py` + nightly chain verification      |
| NFR-001 … NFR-011    | `scripts/loadtest-*.sh`                                                 |
| NFR-023              | preflight + manual breaker drill                                        |
| NFR-040 / NFR-041    | DPIA tabletop drills + audit-log export check                           |
| NFR-050 … NFR-053    | axe-core CI + manual screen-reader pass + Lighthouse CI                 |
| NFR-070              | `pytest --cov` ≥ 70 %                                                   |
| NFR-080 … NFR-082    | trace-id assertion on every test response + Grafana SLO                 |

The matrix is enforced: a PR that touches a requirement without updating its verification fails review.
