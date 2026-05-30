# Access Control

**Audience:** security assessors, MoH/NITA-U reviewers verifying RBAC, engineers adding endpoints.
**Source of truth:**
- `backend/app/core/security.py` — role hierarchy, `Principal` (now carries `district_id`), JWT issue/decode, `require_role`.
- `backend/app/core/access.py` — canonical per-resource authorisation gate (`can_read_patient`, `can_read_encounter`, `patient_visibility_filter`, `has_active_consent_for_worker`). REST and FHIR routes both call into this module.
- `require_role(...)` lines in each `backend/app/api/v1/*.py` file (minimum-role declarations per endpoint).

This document mirrors those files; the code wins on any conflict.
**Last reviewed:** 2026-05-28.

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

| Role             | Issued to                                          | Token TTL | Identifier (`Principal.subject`) | `facility_id` set? | `district_id` set? |
| ---------------- | -------------------------------------------------- | --------- | -------------------------------- | ------------------ | ------------------ |
| `citizen`        | Citizens, via NIN+OTP at `/auth/citizen/login`     | 2 h (per SECURITY.md) | NIN              | NULL               | NULL               |
| `worker`         | Nurses, clinical officers                          | 8 h       | username                         | YES                | YES (derived)      |
| `pharmacist`     | Pharmacists, store-keepers                         | 8 h       | username                         | YES                | YES (derived)      |
| `district_admin` | District health team                               | 8 h       | username                         | YES (home facility) | YES (required)    |
| `ministry_admin` | MoH / NITA-U operators                             | 8 h       | username                         | NULL               | NULL               |

JWT claims (`security.py:issue_token`): `sub`, `role`, `facility_id`, **`district_id`**, `name`, `iat`, `exp`, `iss`. Signed HS256 with `SECRET_KEY`. Verification (`_decode_token`) hard-codes `algorithms=["HS256"]` and requires `sub`, `role`, `exp`, `iat` (PyJWT advisory note in [SECURITY.md](./SECURITY.md)).

`district_id` is resolved at login time from `User.facility.district` (`auth.py:staff_login`) and embedded in the JWT so every request carries the district scope without re-querying. Tokens issued before this claim was added — "legacy tokens" — are treated as having `district_id = NULL`; see §3 for the fail-closed behaviour that protects against them being used to escalate scope.

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

## 3. Facility and district scoping (canonical authorisation gates)

Role alone is not sufficient for clinical data — every read+write goes through the per-resource gates in `backend/app/core/access.py`. The matrix below is the *single* authoritative statement of patient-level scope; REST `GET /patients/{id}` and FHIR `GET /fhir/Patient/{id}` both invoke `can_read_patient(...)` so there is no second policy to drift.

| Role               | `can_read_patient(p)` returns true iff |
| ------------------ | -------------------------------------- |
| `ministry_admin`   | always |
| `district_admin`   | `principal.district_id IS NOT NULL` **AND** `p.enrolling_district == principal.district_id`. Tokens without a district claim **fail closed** — they get nothing. |
| `worker`, `pharmacist` | `principal.facility_id IS NOT NULL` **AND** active-consent check passes (see below) **AND** (`p.enrolling_facility_id == principal.facility_id` **OR** the patient has at least one prior encounter at the caller's facility). |
| `citizen`          | `p.nin == principal.subject` **OR** a `CaregiverLink` row exists where `caregiver_id` resolves to `principal.subject`. |
| any other role     | denied. |

### 3.1 Worker / pharmacist consent enforcement

`has_active_consent_for_worker(principal, patient, db)` (in `app/core/access.py`) is called by `_worker_can_access_patient` before any facility check succeeds. The rule:

- If the patient has **no `Consent` rows at all**, default-allow (facility-scope alone gates access — this matches the demo-data state and the pre-pilot DPPA s.10 "purpose of care" baseline).
- If the patient has **at least one** `Consent` row, **at least one** must be active — i.e. `revoked_at IS NULL` **AND** (`expires_at IS NULL` **OR** `expires_at > now()`).
- If every consent has been revoked or expired, the worker/pharmacist read returns 403 even when facility-scope would otherwise grant it. This realises DPPA s.27 right-to-withdraw at the *access* layer, not just at the *recording* layer.

The check writes nothing — it's a pure read against the `consents` table — so it carries no audit cost beyond the surrounding `record_access` call.

### 3.2 Other facility-scoping points

1. **Implicit in the data model.** Write endpoints (`POST /encounters`, `POST /supply/batches`, `POST /supply/dispense`) stamp `facility_id` from the caller's `Principal.facility_id`. No API path lets a worker write into another facility's records.
2. **Explicit in the SQL.** List endpoints that surface facility-scoped data (patient search, encounter list, stock snapshot) use `patient_visibility_filter(...)` or an analogous `WHERE facility_id = ...` clause server-side. The filter is applied at SQL level — never at Python row-iteration — so an N-row bundle never produces N authz queries.
3. **`patient_visibility_filter` for `district_admin`** fails closed identically to `can_read_patient`: a legacy token without a district claim resolves to a sentinel `Patient.id == "__no_district__"` clause, which never matches.

`district_admin` collapses scope to a whole district (cross-facility within the district). `ministry_admin` is national-scope.

---

## 4. Citizen-self rule

Citizens authenticate via NIN+OTP. Their `Principal.subject` is their NIN. The rule is enforced via the canonical gate:

```python
# backend/app/core/access.py — _citizen_can_read_patient
if patient.nin == principal.subject:
    return True
me = (await db.scalars(
    select(Patient).where(Patient.nin == principal.subject)
)).one_or_none()
if me is None:
    return False
link = (await db.scalars(
    select(CaregiverLink).where(
        CaregiverLink.caregiver_id == me.id,
        CaregiverLink.child_id == patient.id,
    )
)).one_or_none()
return link is not None
```

`GET /api/v1/patients/{id}` and `GET /fhir/Patient/{id}` both call `can_read_patient(...)` which routes citizens through this branch — so the citizen-self rule is identical across REST and FHIR. The list endpoints use `patient_visibility_filter(...)` to express the same logic at SQL level (own NIN OR caregiver-linked child).

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
| Seed demo (internal)         | `POST /auth/seed-demo`         | env-gated; refused in `APP_ENV=production` | Bootstrap | `include_in_schema=False`; documented in BACKEND_SETUP.md. |

The legacy `POST /auth/seed-admin` endpoint was removed during the 2026-05-28 compliance sweep — it created a `ministry_admin` with a weak hardcoded password and had no production guard. Recovery / first-bootstrap is handled by `seed-demo` (which writes the same admin record as part of the full demo dataset and is production-gated). See CHANGELOG `[Unreleased]` for the audit trail.

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

- The `Principal` shape (`subject`, `role`, `facility_id`, `district_id`, `name`).
- The role hierarchy (`citizen < worker < pharmacist < district_admin < ministry_admin`).
- The `require_role(...)` dependency at every endpoint.
- The canonical access gates in `app/core/access.py` (`can_read_patient`, `can_read_encounter`, `patient_visibility_filter`, `has_active_consent_for_worker`).
- The audit-log shape and `record_access` calls.
- The facility-and-district-scoping rules in §3 (including the consent enforcement for worker/pharmacist).

Endpoints do not need code changes when the IdP swaps. This is the design intent.

---

## 8. Cross-references

- [SECURITY.md](./SECURITY.md) — auth posture, password hashing, transport.
- [DATA_MODEL.md](./DATA_MODEL.md) — the resources this matrix governs; `audit_log` schema; `users.role` column.
- [API.md](./API.md) — endpoint reference (request/response shapes).
- [INCIDENT_RESPONSE.md](./INCIDENT_RESPONSE.md) — IR-23 credential compromise; detection signals that fire on anomalous role/facility access.
- [THREAT_MODEL.md](./THREAT_MODEL.md) — privilege-escalation and lateral-movement scenarios.
- [COMPLIANCE.md](./COMPLIANCE.md) — DPPA s.10 (purpose), s.14 (accountability), s.24/s.25/s.27 (data-subject rights).
