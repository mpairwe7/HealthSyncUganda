# Access Control

**Audience:** security assessors, MoH/NITA-U reviewers verifying RBAC, engineers adding endpoints.
**Source of truth:** `backend/app/core/security.py` (role hierarchy and `require_role`) + the `require_role(...)` lines in each `backend/app/api/v1/*.py` file. This document mirrors those files; the code wins on any conflict.
**Last reviewed:** 2026-05-25.

This is the consolidated RBAC matrix for the platform. It exists so that:

- A **security assessor** can confirm that every endpoint declares its minimum role, and that the role chosen is the *least* one needed.
- An **MoH/NITA-U reviewer** can confirm citizen-self access (DPPA s.24 right of access), worker facility-scoping, and admin-tier separation.
- An **engineer adding an endpoint** can pick the right `require_role(...)` value by analogy with the table below — and update this document in the same PR.

---

## 1. Role hierarchy

Five roles, ordered (`security.py:Principal.is_at_least`):

```
citizen  <  worker  <  pharmacist  <  district_admin  <  ministry_admin
```

`is_at_least(role)` returns true when the holder's role is *at or above* the requested level. So a `ministry_admin` satisfies `require_role("worker")`, and a `pharmacist` satisfies `require_role("pharmacist")` but not `require_role("district_admin")`.

| Role             | Issued to                                          | Token TTL | Identifier (`Principal.subject`) | `facility_id` set? |
| ---------------- | -------------------------------------------------- | --------- | -------------------------------- | ------------------ |
| `citizen`        | Citizens, via NIN+OTP at `/auth/citizen/login`     | 2 h (per SECURITY.md) | NIN              | NULL               |
| `worker`         | Nurses, clinical officers                          | 8 h       | username                         | YES                |
| `pharmacist`     | Pharmacists, store-keepers                         | 8 h       | username                         | YES                |
| `district_admin` | District health team                               | 8 h       | username                         | NULL               |
| `ministry_admin` | MoH / NITA-U operators                             | 8 h       | username                         | NULL               |

JWT claims (`security.py:issue_token`): `sub`, `role`, `facility_id`, `name`, `iat`, `exp`, `iss`. Signed HS256 with `SECRET_KEY`. Verification (`_decode_token`) hard-codes `algorithms=["HS256"]` and requires `sub`, `role`, `exp`, `iat` (PyJWT advisory note in [SECURITY.md](./SECURITY.md)).

---

## 2. Role-to-endpoint matrix

The endpoints below are the **complete** set of `/api/v1/*` routes that declare a role requirement (via `Depends(require_role(...))` or `Depends(get_current_principal)`). Routes mounted at `/healthz`, `/readyz`, `/openapi.json`, and `/docs` are unauthenticated by design; the FHIR endpoints under `/fhir/*` enforce the same role gates as the underlying `/api/v1` resources they wrap.

Legend: ✅ = allowed; — = denied; ★ = self-scoped (citizens may access only their own NIN-keyed resources); 🅵 = facility-scoped at the application layer (see §3).

| Endpoint                                            | Method | Citizen | Worker | Pharmacist | District&nbsp;admin | Ministry&nbsp;admin | Notes |
| --------------------------------------------------- | ------ | :-----: | :----: | :--------: | :-----------------: | :-----------------: | ----- |
| `/auth/login`                                       | POST   | —       | open\* | open\*     | open\*              | open\*              | Issues JWT for staff. \*No auth header required to call; succeeds only with valid credentials. |
| `/auth/citizen/login`                               | POST   | open\*  | —      | —          | —                   | —                   | NIN + OTP. \*No auth header. Rate-limited (5 / 5 min / NIN per SECURITY.md). |
| `/patients` — search                                | GET    | —       | ✅     | ✅         | ✅                  | ✅                  | `require_role("worker")`. |
| `/patients/{id}` — read one                         | GET    | ★       | ✅     | ✅         | ✅                  | ✅                  | Citizens 403 unless `subject == patient.nin`. `purpose` query param recorded in audit. |
| `/patients` — create                                | POST   | —       | ✅     | ✅         | ✅                  | ✅                  | `require_role("worker")`. |
| `/patients/{id}` — update                           | PATCH  | —       | ✅     | ✅         | ✅                  | ✅                  | `require_role("worker")`. Bumps `record_version` (DPPA s.11). |
| `/encounters` — create                              | POST   | —       | ✅     | ✅         | ✅                  | ✅                  | `require_role("worker")`. 🅵 |
| `/encounters/by-patient/{id}` — list                | GET    | —       | ✅     | ✅         | ✅                  | ✅                  | `require_role("worker")`. |
| `/consents` — grant                                 | POST   | —       | ✅     | ✅         | ✅                  | ✅                  | Worker records consent on the patient's behalf. `granted_by` stamped with caller. |
| `/consents/by-patient/{id}` — list                  | GET    | ★       | ✅     | ✅         | ✅                  | ✅                  | Citizens 403 unless they are the named patient. |
| `/consents/{id}/revoke`                             | POST   | ✅      | ✅     | ✅         | ✅                  | ✅                  | Any authenticated. DPPA s.27 right to withdraw — by design no role gate; the consent_id functions as the capability. |
| `/facilities` — list                                | GET    | ✅      | ✅     | ✅         | ✅                  | ✅                  | No role gate; facility list is non-sensitive reference data. |
| `/supply/items` — list                              | GET    | —       | ✅     | ✅         | ✅                  | ✅                  | `require_role("worker")`. |
| `/supply/items` — create                            | POST   | —       | —      | —          | —                   | ✅                  | `require_role("ministry_admin")` — master-data change. |
| `/supply/batches` — receive                         | POST   | —       | —      | ✅         | ✅                  | ✅                  | `require_role("pharmacist")`. Emits `stock_events.event_type='receive'`. |
| `/supply/transfers` — initiate                      | POST   | —       | —      | ✅         | ✅                  | ✅                  | `require_role("pharmacist")`. Emits paired `transfer_out` / `transfer_in` events. |
| `/supply/dispense`                                  | POST   | —       | —      | ✅         | ✅                  | ✅                  | `require_role("pharmacist")`. Emits `stock_events.event_type='dispense'` with `quantity_delta<0`. |
| `/supply/stock-snapshot` (and variants)             | GET    | —       | ✅     | ✅         | ✅                  | ✅                  | `require_role("worker")`. |
| `/supply/alerts/low-stock`                          | GET    | —       | ✅     | ✅         | ✅                  | ✅                  | `require_role("worker")`. |
| `/analytics/*` — every endpoint                     | GET    | —       | —      | —          | ✅                  | ✅                  | All three analytics routes carry `require_role("district_admin")`. Returns aggregates only — never row-level (DPPA s.31). |
| `/interop/circuits` — read breakers                 | GET    | —       | —      | —          | —                   | ✅                  | `require_role("ministry_admin")`. |
| `/interop/circuits/{name}/trip` — force trip        | POST   | —       | —      | —          | —                   | ✅                  | `require_role("ministry_admin")`. `include_in_schema=False`. |
| `/interop/dhis2/drain-queue` — manual drain          | POST   | —       | —      | —          | ✅                  | ✅                  | `require_role("district_admin")`. See [RUNBOOK.md RB-03](./RUNBOOK.md#rb-03). |
| `/interop/mock/nira/verify/{nin}`                   | GET    | open\*  | open\* | open\*     | open\*              | open\*              | Dev mock only; `include_in_schema=False`. Replaced by NIRA OIDC in production. |
| `/interop/mock/dhis2/dataValueSets`                 | POST   | open\*  | open\* | open\*     | open\*              | open\*              | Dev mock only; `include_in_schema=False`. Replaced by real DHIS2 in production. |

---

## 3. Facility scoping

Role alone is not sufficient for clinical data — a `worker` is also scoped to their own facility. The scoping is enforced at the **application layer** in two places:

1. **Implicit in the data model.** Endpoints that write (`POST /encounters`, `POST /supply/batches`, `POST /supply/dispense`) stamp `facility_id` from the caller's `Principal.facility_id`. There is no API path that lets a worker write into another facility's records.
2. **Explicit in the query.** Read endpoints that surface facility-scoped data (stock snapshots, low-stock alerts) filter by `Principal.facility_id` server-side.

`district_admin` collapses the scope to a whole district (cross-facility within the district). `ministry_admin` is national-scope.

**Current gap (tracked):** the patient `GET /patients/{id}` endpoint does *not* facility-scope worker access. A worker at any facility can read any patient by ID. The compensating controls are: (a) every read is audit-logged with `actor_id`, `actor_facility_id`, and `purpose`; (b) anomalous cross-facility patterns trip the detection signals in [INCIDENT_RESPONSE.md §3 Phase B](./INCIDENT_RESPONSE.md#phase-b--detection--analysis). A migration to enforce facility-or-consent at read time is on the roadmap (no ADR yet).

---

## 4. Citizen-self rule

Citizens authenticate via NIN+OTP. Their `Principal.subject` is their NIN. The rule is enforced in code:

```python
# patients.py:118
if principal.role == "citizen" and principal.subject != p.nin:
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your record")
```

```python
# consent.py:75
if principal.role == "citizen":
    patient = await db.get(Patient, patient_id)
    if not patient or patient.nin != principal.subject:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your record")
```

Combined effect:

| Resource                      | Citizen can read | Citizen can write |
| ----------------------------- | ---------------- | ----------------- |
| Own `Patient` record          | ✅               | ✗ (worker-mediated correction via DPPA s.25) |
| Own `Consent` list            | ✅               | — (grants are worker-recorded; **revoke** is citizen-actionable per DPPA s.27) |
| Own audit-log entries         | Roadmap          | — |
| Any other citizen's data      | ✗                | ✗ |
| Any clinical write            | ✗                | ✗ |
| Any analytics                 | ✗                | ✗ |
| Any supply / facility data    | Facility list ✅ | ✗ |

Citizens get a thin, focused surface: read your record, see your consents, revoke a consent. Everything else is staff-mediated.

---

## 5. Audit semantics

Every privileged access produces a row in `audit_log` via `app.core.audit.record_access`. The row carries:

| Field                | Source                                                |
| -------------------- | ----------------------------------------------------- |
| `actor_id`           | `Principal.subject` (NIN for citizens, username for staff) |
| `actor_role`         | `Principal.role`                                      |
| `actor_facility_id`  | `Principal.facility_id` (NULL for citizens and admins) |
| `resource_type`      | The endpoint declares it (`"Patient"`, `"Consent"`, `"Encounter"`, …) |
| `resource_id`        | The row id touched                                    |
| `action`             | `read`, `create`, `update`, `grant`, `revoke`, `fhir-read`, … |
| `purpose`            | A free-text reason — required at read time for sensitive resources (enforced as `Query(...)` in the endpoint signature) |
| `consent_id`         | The consent row that authorised the access, if applicable |
| `extra`              | JSONB for endpoint-specific metadata (e.g. fields changed on an update) |

The row is also mirrored to structured logs (`logger.info("audit", …)`) so any SIEM (Loki, Splunk, Elastic, Wazuh) can index it independently of the DB.

`audit_log` is **append-only by application convention** (no UPDATE, no DELETE). A database-level `RULE` enforcing this is a planned migration; see [SECURITY.md](./SECURITY.md) and [DATA_MODEL.md §3.11](./DATA_MODEL.md#311-audit_log--append-only-pii-access-trail).

**Canonical query for "what did actor X do":**

```sql
SELECT created_at, resource_type, resource_id, action, purpose
FROM audit_log
WHERE actor_id = $1
  AND created_at >= $2
ORDER BY created_at DESC;
```

Backed by the composite index `ix_audit_log_actor_time (actor_id, created_at)`.

**Canonical query for "who touched record Y":**

```sql
SELECT created_at, actor_id, actor_role, action, purpose
FROM audit_log
WHERE resource_type = $1 AND resource_id = $2
ORDER BY created_at DESC;
```

Backed by `ix_audit_log_resource (resource_type, resource_id)`.

---

## 6. Authentication channels

| Channel                      | Endpoint                       | Credentials                  | Audience           | Notes |
| ---------------------------- | ------------------------------ | ---------------------------- | ------------------ | ----- |
| Staff password               | `POST /auth/login`             | `username` + `password`      | Staff              | bcrypt verification (`security.py:verify_password`). Production should put Keycloak / Authentik in front. |
| Citizen NIN+OTP              | `POST /auth/citizen/login`     | `nin` + `otp`                | Citizens           | Prototype OTP-stub; production swaps to NIRA OIDC. Contract (endpoint shape) does not change. Rate-limited per [SECURITY.md](./SECURITY.md). |
| Bearer token                 | `Authorization: Bearer …`      | JWT from one of the above    | All authenticated  | HS256, hard-coded algorithm (CVE-2025-45768 advisory). |
| Seed admin (internal)        | `POST /auth/seed-admin`        | env-gated                    | Bootstrap          | `include_in_schema=False`; documented in BACKEND_SETUP.md. |

No refresh tokens. Re-login is intentional for attended-workstation contexts (per [SECURITY.md](./SECURITY.md) §"Authentication & authorisation").

---

## 7. Future-IdP migration

The auth layer is intentionally framework-light (`security.py` docstring) to allow swap-in of:

- **NIRA OIDC** for citizen authentication (replaces OTP-stub).
- **Keycloak / Authentik** for staff (RS256 tokens with key rotation).
- **OpenMRS basic-auth bridge** for legacy facility installs that already have OpenMRS accounts.

What changes when an IdP is wired in:

- `_decode_token` becomes JWKS-backed (RS256 with key rotation) instead of HS256-with-shared-secret.
- `issue_token` is no longer called by the platform — the IdP issues; the platform only verifies.
- Role claim source: from the IdP's group/role mapping (configured per IdP).

What does **not** change:

- The `Principal` shape (`subject`, `role`, `facility_id`, `name`).
- The role hierarchy (`citizen < worker < pharmacist < district_admin < ministry_admin`).
- The `require_role(...)` dependency at every endpoint.
- The audit-log shape and `record_access` calls.
- The facility-scoping rules in §3.

Endpoints do not need code changes when the IdP swaps. This is the design intent.

---

## 8. Cross-references

- [SECURITY.md](./SECURITY.md) — auth posture, password hashing, transport.
- [DATA_MODEL.md](./DATA_MODEL.md) — the resources this matrix governs; `audit_log` schema; `users.role` column.
- [API.md](./API.md) — endpoint reference (request/response shapes).
- [INCIDENT_RESPONSE.md](./INCIDENT_RESPONSE.md) — IR-23 credential compromise; detection signals that fire on anomalous role/facility access.
- [THREAT_MODEL.md](./THREAT_MODEL.md) — privilege-escalation and lateral-movement scenarios.
- [COMPLIANCE.md](./COMPLIANCE.md) — DPPA s.10 (purpose), s.14 (accountability), s.24/s.25/s.27 (data-subject rights).
