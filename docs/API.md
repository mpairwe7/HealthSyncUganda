# API reference

**Audience:** integration partners (NIRA, DHIS2, MoH downstreams), client engineers, security reviewers.
**Last reviewed:** 2026-05-20.

This document is the human-readable companion to the OpenAPI spec served at `GET /openapi.json` (Swagger UI at `/docs`, ReDoc at `/redoc`). The OpenAPI document is the machine-readable source of truth; this file explains conventions and the design intent behind them.

The platform exposes two interface families:

- **REST API** under `/api/v1/*` — used by the HealthSync frontend and by ministry / district integrations.
- **FHIR R4 API** under `/fhir/*` — the canonical exchange surface for external systems.

Both share the same authentication and authorisation model, the same audit trail, and the same trace propagation.

---

## 1. Conventions

### Base URL

| Environment       | Base URL                                       |
| ----------------- | ---------------------------------------------- |
| Local dev         | `http://localhost:8000`                        |
| Docker compose    | `http://backend:8000` (in-network) / `http://localhost:8000` (host) |
| Pilot (proposed)  | `https://api.healthsync.go.ug` (TBC with MoH)  |

### Versioning

- REST routes are versioned via the path: `/api/v1/...`. Breaking changes ship under `/api/v2/...` with overlap for at least one MoH release cycle.
- FHIR routes are NOT versioned in the path. The `CapabilityStatement` advertises `fhirVersion: 4.0.1`; future moves to R5 are flagged in the `meta` of every resource.

### Content types

- Request and response bodies are `application/json` by default.
- FHIR endpoints prefer `application/fhir+json`. The server still accepts `application/json` for ergonomics.
- `Accept-Language: en|lg` switches localised error messages.

### Time

All timestamps are ISO 8601 with explicit UTC offsets (`...+00:00`). Africa/Kampala is `+03:00`; clients display in local time.

### Identifiers

- Resource ids are ULIDs (sortable, opaque) — never sequence integers — except for ledger entries which use a strictly monotonic `BIGSERIAL` for chain integrity.
- Patient NINs use the NIRA format `^C[MF][A-Z0-9]{12}$`, system URI `https://nira.go.ug/identifiers/nin`.
- Trace ids appear on every response as `X-Trace-Id`.

---

## 2. Authentication

| Audience      | Endpoint                                | Body                                            | Returns                                |
| ------------- | --------------------------------------- | ----------------------------------------------- | -------------------------------------- |
| Staff         | `POST /api/v1/auth/login`               | `{"identifier":"admin","password":"…"}`         | `{access_token, role, subject, name, facility_id, expires_in}` |
| Citizen       | `POST /api/v1/auth/citizen/login`       | `{"nin":"CM…X","otp":"000000"}`                 | same shape                              |

The token is a JWT with role + subject claims. Pass it as `Authorization: Bearer <token>` on every subsequent request. Tokens cannot be refreshed in the prototype; re-login is intentional for attended workstations.

Lifetimes:

- Citizen tokens: 2 hours.
- Staff tokens: 8 hours.

There are five roles enforced at the API boundary (`backend/app/core/security.py::require_role`):

`citizen` · `worker` · `pharmacist` · `district_admin` · `ministry_admin`.

---

## 3. Idempotency

Every state-changing route accepts an `Idempotency-Key` header. If a request is repeated with the same key within the retention window (24 h by default), the server returns the original response — **including the same `id`** — without re-applying the mutation.

```http
POST /api/v1/encounters HTTP/1.1
Authorization: Bearer <staff-token>
Idempotency-Key: 01JAGRT8YS4G6F7VG3JK5MZ7N3
Content-Type: application/json

{...encounter body...}
```

The frontend mutation queue generates a ULID per offline write — see [ADR 0003](./adr/0003-offline-first-frontend.md).

---

## 4. Error model

Errors follow [RFC 7807](https://www.rfc-editor.org/rfc/rfc7807) Problem+JSON, with optional FHIR-shaped variant for `/fhir/*` routes.

```json
{
  "type": "https://healthsync.go.ug/errors/validation",
  "title": "Validation failed",
  "status": 422,
  "trace_id": "5e4d3c2b1a09e8d7c6b5a4f3e2d1c0b9",
  "details": [
    {"loc": ["body", "identifier", 0, "system"], "msg": "must be https://nira.go.ug/identifiers/nin", "type": "value_error"}
  ]
}
```

Common status codes:

| Status | Meaning                                                                                 |
| ------ | --------------------------------------------------------------------------------------- |
| 200    | OK.                                                                                     |
| 201    | Created. New resource. The `Location` header points to it.                              |
| 202    | Accepted. Queued (e.g. DHIS2 push when the breaker is open).                            |
| 400    | Malformed request. Fix the client.                                                      |
| 401    | Missing or invalid token.                                                               |
| 403    | Authenticated, but the role / consent does not permit the action.                       |
| 404    | Resource does not exist (or the caller has no consent to know it does).                 |
| 409    | Conflict (idempotency-key reused with a different payload).                             |
| 422    | Body failed validation. `details` enumerates the offending paths.                       |
| 429    | Rate limit hit. Retry after `Retry-After` seconds.                                      |
| 503    | A downstream breaker is open or the service itself is not ready. See `/readyz`.         |

---

## 5. REST endpoints (`/api/v1`)

The full list is in OpenAPI. The endpoints below are the ones a partner is most likely to use.

### 5.1 Health and readiness

| Method | Path           | Auth | Purpose                                            |
| ------ | -------------- | ---- | -------------------------------------------------- |
| GET    | `/healthz`     | none | Liveness. Returns 200 if the process is up.        |
| GET    | `/readyz`      | none | Readiness. 200 only if DB + Redis are healthy.     |
| GET    | `/metrics`     | none (internal) | Prometheus scrape endpoint.              |

### 5.2 Patients (`backend/app/api/v1/patients.py`)

| Method | Path                                              | Auth                  | Purpose                                                            |
| ------ | ------------------------------------------------- | --------------------- | ------------------------------------------------------------------ |
| GET    | `/api/v1/patients?q=&family=&nin=&page=&size=`    | worker+               | Paginated search.                                                  |
| GET    | `/api/v1/patients/{id}`                           | worker+ with consent  | Full patient record.                                               |
| POST   | `/api/v1/patients`                                | worker+               | Register a new patient. Idempotency-Key supported.                 |
| PATCH  | `/api/v1/patients/{id}`                           | worker+ with consent  | Update demographics.                                               |

### 5.3 Encounters (`backend/app/api/v1/encounters.py`)

| Method | Path                                              | Auth      | Purpose                                                      |
| ------ | ------------------------------------------------- | --------- | ------------------------------------------------------------ |
| POST   | `/api/v1/encounters`                              | worker+   | Create encounter. Idempotency-Key strongly recommended.      |
| GET    | `/api/v1/encounters?patient=&since=&until=`       | varies    | List encounters; citizens see only their own.                |

### 5.4 Consent (`backend/app/api/v1/consent.py`)

| Method | Path                                              | Auth      | Purpose                                                      |
| ------ | ------------------------------------------------- | --------- | ------------------------------------------------------------ |
| GET    | `/api/v1/consents/by-patient/{patient_id}`        | varies    | List active consents.                                        |
| POST   | `/api/v1/consents`                                | citizen   | Grant consent for a facility × category.                     |
| POST   | `/api/v1/consents/{consent_id}/revoke`            | citizen   | Revoke. Effect is immediate.                                 |

### 5.5 Supply chain (`backend/app/api/v1/supply.py`)

| Method | Path                                                              | Auth                 | Purpose                                              |
| ------ | ----------------------------------------------------------------- | -------------------- | ---------------------------------------------------- |
| GET    | `/api/v1/supply/items`                                            | worker+              | Catalogue (EMHSLU-coded).                            |
| GET    | `/api/v1/supply/by-facility/{id}`                                 | worker+              | On-hand quantities + thresholds.                     |
| POST   | `/api/v1/supply/receipts`                                         | pharmacist+          | Record stock receipt. Ledger entry created.          |
| POST   | `/api/v1/supply/transfers`                                        | pharmacist+          | Initiate transfer between facilities.                |
| POST   | `/api/v1/supply/transfers/{id}/acknowledge`                       | pharmacist+ (recv)   | Receiving facility confirms receipt.                 |
| POST   | `/api/v1/supply/dispense`                                         | pharmacist+          | Dispense to patient. Decrements stock.               |
| GET    | `/api/v1/supply/alerts/low-stock`                                 | worker+              | Items at/below threshold.                            |
| GET    | `/api/v1/supply/ledger/verify`                                    | district_admin+      | Verify the hash chain end to end.                    |

### 5.6 Analytics (`backend/app/api/v1/analytics.py`)

| Method | Path                                                              | Auth                 | Purpose                                              |
| ------ | ----------------------------------------------------------------- | -------------------- | ---------------------------------------------------- |
| GET    | `/api/v1/analytics/encounters-by-district?since_days=`            | district_admin+      | Bar chart data, Redis-cached 60 s.                   |
| GET    | `/api/v1/analytics/immunisation-coverage?antigen=&since_days=`    | district_admin+      | Coverage per antigen × district.                     |
| GET    | `/api/v1/analytics/stock-out-risk`                                | district_admin+      | Items at risk, weighted by burn-rate.                |

### 5.7 Interoperability operations (`backend/app/api/v1/interop.py`)

| Method | Path                                                              | Auth                 | Purpose                                                                |
| ------ | ----------------------------------------------------------------- | -------------------- | ---------------------------------------------------------------------- |
| GET    | `/api/v1/interop/circuits`                                        | ministry_admin       | List all breakers and their state.                                     |
| POST   | `/api/v1/interop/circuits/{name}/trip`                            | ministry_admin       | **Demo/incident only.** Trip a breaker.                                |
| POST   | `/api/v1/interop/dhis2/drain-queue`                               | ministry_admin       | Force drain of the DHIS2 outbox.                                       |
| GET    | `/api/v1/interop/mock/nira/verify/{nin}`                          | internal             | Mock NIRA endpoint used by local dev. Not in OpenAPI public docs.      |
| POST   | `/api/v1/interop/mock/dhis2/dataValueSets`                        | internal             | Mock DHIS2 endpoint.                                                   |

### 5.8 Facilities (`backend/app/api/v1/facilities.py`)

| Method | Path                                                              | Auth      | Purpose                                                |
| ------ | ----------------------------------------------------------------- | --------- | ------------------------------------------------------ |
| GET    | `/api/v1/facilities?district=&level=`                             | any       | Browse the national facility list (HC II → NRH).       |

---

## 6. FHIR API (`/fhir`)

The FHIR layer is the **stable, partner-facing surface**. It is intentionally narrower than the REST API and tracks the published Uganda Implementation Guide.

| Method | Path                                                              | Resource              | Notes                                                          |
| ------ | ----------------------------------------------------------------- | --------------------- | -------------------------------------------------------------- |
| GET    | `/fhir/metadata`                                                  | CapabilityStatement   | Public, no auth required.                                      |
| GET    | `/fhir/Patient?identifier=…\|…&family=…&_count=…`                  | Patient               | Search by NIN slice + family name.                             |
| GET    | `/fhir/Patient/{id}`                                              | Patient               | Single resource.                                               |
| GET    | `/fhir/Encounter?patient=…&date=…`                                 | Encounter             | Search by patient ref.                                         |
| GET    | `/fhir/Observation?patient=…&code=…&_count=…`                      | Observation           | Search vitals/labs by patient and LOINC code.                  |
| POST   | `/fhir/Observation`                                               | Observation           | Create a new observation.                                      |
| GET    | `/fhir/Immunization?patient=…`                                    | Immunization          | EPI history.                                                   |
| GET    | `/fhir/MedicationDispense?patient=…`                              | MedicationDispense    | Dispense events for a patient.                                 |

### Uganda Patient profile

Every `Patient` resource conforms to the profile at `backend/app/fhir/profiles/uganda_patient.json`:

- Exactly one `identifier` with `system=https://nira.go.ug/identifiers/nin` and `value` matching `^C[MF][A-Z0-9]{12}$`.
- `name[0]` MUST be present with `family` and at least one `given`.
- `gender` MUST be `male | female`.
- `birthDate` is required for paediatric workflows.

### Provenance

Every imported / exported resource carries:

- `meta.source` — origin system URI (`https://dhis2.moh.go.ug`, `https://hospital-x.lacor.go.ug`, etc.).
- `meta.lastUpdated` — UTC timestamp.
- `meta.tag` — `partition`, `confidentiality`.

---

## 7. Auditing

Every read or write of PHI generates an `AuditLog` row. Each row captures:

- `actor_id` (the authenticated subject)
- `actor_role`
- `action` (`read`, `create`, `update`, `delete`, `consent.grant`, `consent.revoke`, …)
- `resource_type` + `resource_id`
- `purpose_of_use` (taken from the access context, e.g. `TREATMENT`, `OPERATIONS`)
- `consent_id` (if applicable)
- `request_id` / `trace_id`
- `timestamp`

Citizens can view their own audit trail at `/citizen/audit` in the UI; the backing endpoint is `GET /api/v1/audit/by-subject/{nin}`.

---

## 8. Rate limiting

A token-bucket limiter in `backend/app/middleware/ratelimit.py` enforces:

| Surface           | Limit                                                       |
| ----------------- | ----------------------------------------------------------- |
| `/auth/login`     | 10 / 5 min per IP.                                          |
| `/auth/citizen/login` | 5 / 5 min per NIN + 30 / 5 min per IP.                  |
| Other authenticated routes | 200 / minute per token, 5 000 / minute per IP.    |
| Unauthenticated `/healthz` | None.                                              |

Limit hits return HTTP 429 with `Retry-After` in seconds.

---

## 9. Verification and contract tests

- `scripts/fhir-conformance.sh` — 18-check FHIR R4 round-trip suite.
- `scripts/preflight.sh` — end-to-end smoke test before the showcase.
- `backend/tests/test_*` — unit + integration coverage; runs in CI on every push.

The OpenAPI document at `/openapi.json` is treated as a contract. CI fails if it changes in a way that is not reflected in this document or `CHANGELOG.md`.

---

## 10. Versioning policy

- **Patch** (`0.1.x`): bug fixes, no API change.
- **Minor** (`0.x.0`): additive changes (new endpoints, new optional fields).
- **Major** (`x.0.0`): breaking change. Requires:
  - An ADR documenting the rationale.
  - A 30-day deprecation notice on the previous version.
  - A migration guide in `docs/MIGRATIONS/`.

The `Sunset` HTTP header is set on deprecated routes per [RFC 8594](https://www.rfc-editor.org/rfc/rfc8594) so partners can be alerted automatically.
