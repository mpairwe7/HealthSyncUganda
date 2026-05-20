# Requirements specification

**Document owner:** Architecture group · **Last reviewed:** 2026-05-20 · **Status:** Approved

This document is the authoritative requirements register for HealthSync Uganda. Every requirement has a stable identifier (`FR-NNN` for functional, `NFR-NNN` for non-functional), an acceptance criterion that is testable, and a verification method. Cross-references from code, tests, and other documents point at these IDs and remain valid across renames.

Requirement IDs are not re-used. If a requirement is retired, its ID is marked `RETIRED` rather than deleted.

---

## 1. Stakeholders and scope

| Stakeholder                                        | Primary concern                                                              |
| -------------------------------------------------- | ---------------------------------------------------------------------------- |
| Ministry of Health (MoH)                           | National coverage, NDHS 2021-2025 alignment, HMIS continuity.                |
| National Information Technology Authority (NITA-U) | Government cyber posture, hosting compliance.                                |
| National Identification & Registration Authority (NIRA) | NIN integrity, lawful use of identifiers.                              |
| Personal Data Protection Office (PDPO)             | DPPA 2019 compliance, breach notification.                                   |
| District Health Officers (DHOs)                    | Stock-out reduction, immunisation coverage, audit visibility.                |
| Healthcare workers (nurses, clinical officers)     | Offline reliability, low-friction encounter capture.                         |
| Pharmacists                                        | Transparent stock movements, expiry visibility, dispense traceability.       |
| Citizens                                           | Consent control, record access, language choice.                             |

**In scope** for the v1 prototype: Patient, Encounter, Observation, Immunization, MedicationDispense, Consent, supply receipt + transfer + dispense, ministry analytics, breaker-mediated DHIS2/NIRA integrations.

**Out of scope** for v1: billing, insurance/NHIF, clinical decision support, telemedicine consultation video, claims adjudication.

---

## 2. Functional requirements

> Each requirement lists: **ID**, statement, **Priority** (`MUST` / `SHOULD` / `MAY` per RFC 2119), acceptance criterion (`AC:`), verification method (`V:`), and the source file(s) that implement it.

### 2.1 Identity, authentication, and consent

| ID      | Requirement                                                                                                                                       | Priority |
| ------- | ------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| FR-001  | Citizens MUST authenticate using their NIN plus a one-time password.                                                                              | MUST     |
| FR-002  | Healthcare workers, pharmacists, and admins MUST authenticate with username + password; passwords MUST be stored using bcrypt with cost ≥ 12.     | MUST     |
| FR-003  | The system MUST issue short-lived JWT access tokens (≤ 2 h citizen, ≤ 8 h staff) with role claims.                                                | MUST     |
| FR-004  | Five roles MUST be enforced at the API boundary: `citizen`, `worker`, `pharmacist`, `district_admin`, `ministry_admin`.                           | MUST     |
| FR-005  | Citizens MUST be able to view, grant, and revoke consent per facility and per data category.                                                      | MUST     |
| FR-006  | Every access to PHI MUST write an audit record capturing actor, role, purpose, consent reference, target resource id, and timestamp.              | MUST     |

- `AC FR-001`: a `POST /api/v1/auth/citizen/login` with a valid NIN + OTP returns a token; an invalid pair returns HTTP 401 with `Invalid OTP`. **V**: `backend/tests/test_auth.py`.
- `AC FR-006`: every read of `Patient` records an `AuditLog` row with non-null actor and consent_id. **V**: `backend/tests/test_audit.py::test_patient_read_logs_audit`.

Implementation: `backend/app/api/v1/auth.py`, `backend/app/api/v1/consent.py`, `backend/app/core/security.py`, `backend/app/services/audit.py`.

### 2.2 Patient records

| ID      | Requirement                                                                                                                              | Priority |
| ------- | ---------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| FR-010  | A patient record MUST carry exactly one `Patient.identifier` with system `https://nira.go.ug/identifiers/nin` matching the NIRA format.  | MUST     |
| FR-011  | The system MUST support search by NIN, family name, and a free-text query that combines name and identifier.                             | MUST     |
| FR-012  | Patient demographics MUST be PATCHable by clinicians of the patient's enrolling facility or by ministry administrators.                  | MUST     |
| FR-013  | A patient SHOULD have at most one canonical record across facilities; reconciliation candidates SHOULD be surfaced when NINs collide.    | SHOULD   |
| FR-014  | The platform MUST expose patients as FHIR R4 `Patient` resources at `/fhir/Patient/{id}` with full conformance to the Uganda profile.    | MUST     |

- `AC FR-010`: the validator rejects a `Patient` payload without the NIN slice with HTTP 422 and a `details` body identifying the failed constraint. **V**: `backend/tests/test_validators.py`.
- `AC FR-014`: `scripts/fhir-conformance.sh` passes 18/18 checks.

Implementation: `backend/app/api/v1/patients.py`, `backend/app/fhir/patient.py`, `backend/app/schemas/patient.py`.

### 2.3 Encounters and clinical data

| ID      | Requirement                                                                                                                              | Priority |
| ------- | ---------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| FR-020  | Workers MUST be able to create encounters offline; the client MUST queue the mutation with an idempotency key.                           | MUST     |
| FR-021  | The backend MUST reject duplicate encounters by idempotency key, returning the original response.                                        | MUST     |
| FR-022  | An encounter MUST capture: patient ref, facility ref, type (ambulatory / inpatient / emergency), period, presenting complaint, diagnoses (ICD-10), observations (LOINC), prescriptions (EMHSLU). | MUST |
| FR-023  | Citizens MUST be able to view their encounter timeline aggregated across all facilities they visited.                                    | MUST     |
| FR-024  | Encounters MUST be exposable as FHIR R4 `Encounter` and linked `Observation` / `MedicationDispense` resources.                           | MUST     |

- `AC FR-021`: replaying a `POST /api/v1/encounters` with the same `Idempotency-Key` returns the original record with the same `id`. **V**: `backend/tests/test_encounters.py::test_idempotent_replay`.

Implementation: `backend/app/api/v1/encounters.py`, `backend/app/middleware/idempotency.py`, `frontend/src/lib/offline/queue.ts`.

### 2.4 Immunisation

| ID      | Requirement                                                                                                                              | Priority |
| ------- | ---------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| FR-030  | The system MUST record immunisations as FHIR `Immunization` resources keyed to the Uganda EPI schedule.                                  | MUST     |
| FR-031  | The system MUST surface immunisation coverage by antigen × district to district and ministry admins.                                     | MUST     |

### 2.5 Supply chain

| ID      | Requirement                                                                                                                              | Priority |
| ------- | ---------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| FR-040  | The system MUST track receipt, issue, transfer, adjustment, expiry, and loss for every catalogued supply item per facility.              | MUST     |
| FR-041  | Stock movements MUST be appended to a tamper-evident hash-chained ledger (see ADR 0004).                                                 | MUST     |
| FR-042  | Pharmacists MUST be able to initiate transfers between facilities; transfers MUST be acknowledged by the receiving facility.             | MUST     |
| FR-043  | The system MUST raise a low-stock alert when on-hand quantity falls below the configured threshold per item per facility.                | MUST     |
| FR-044  | The supply catalogue MUST use EMHSLU drug codes; non-EMHSLU items MUST carry a clearly tagged extension.                                  | MUST     |
| FR-045  | The ledger MUST be independently verifiable from `id`, `signed_at`, and `entry_hash` alone.                                              | MUST     |

- `AC FR-041 / FR-045`: `GET /api/v1/supply/ledger/verify` returns `{"ok": true, "checked": N}` on a clean ledger; deliberately corrupting one row makes it return `{"ok": false, "broken_at": <id>}`. **V**: `backend/tests/test_supply_ledger.py`.

Implementation: `backend/app/api/v1/supply.py`, `backend/app/supply/ledger.py`.

### 2.6 Interoperability

| ID      | Requirement                                                                                                                              | Priority |
| ------- | ---------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| FR-050  | The system MUST verify NINs against NIRA in real time; verification calls MUST be wrapped in a circuit breaker.                          | MUST     |
| FR-051  | The system MUST push aggregate indicators to DHIS2 (`dataValueSets`); failed pushes MUST be queued and replayed.                         | MUST     |
| FR-052  | The system MUST publish a FHIR `CapabilityStatement` at `GET /fhir/metadata`.                                                            | MUST     |
| FR-053  | Every FHIR-imported or FHIR-exported resource MUST carry a `meta.source` and `meta.lastUpdated`.                                         | MUST     |

### 2.7 Citizen portal

| ID      | Requirement                                                                                                                              | Priority |
| ------- | ---------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| FR-060  | Citizens MUST be able to switch the UI between English and Luganda; the choice MUST persist across sessions.                             | MUST     |
| FR-061  | Citizens MUST be able to view their own audit log of who accessed their record, when, and why.                                           | MUST     |
| FR-062  | Citizens MAY add or remove appointments and view immunisation reminders.                                                                 | MAY      |

Implementation: `frontend/src/lib/i18n/{dictionary.ts,provider.tsx}`, `frontend/src/app/citizen/*`.

### 2.8 Worker portal

| ID      | Requirement                                                                                                                              | Priority |
| ------- | ---------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| FR-070  | Workers MUST see a sync indicator with online/offline state and pending-mutation count on every page.                                    | MUST     |
| FR-071  | Workers MUST be able to register new patients and capture vitals offline.                                                                | MUST     |
| FR-072  | Workers MUST be able to issue referrals between facilities; the receiving facility MUST be able to accept or decline.                    | MUST     |

### 2.9 Administration

| ID      | Requirement                                                                                                                              | Priority |
| ------- | ---------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| FR-080  | District admins MUST be able to view encounters and stock-out risk for facilities in their district only.                                | MUST     |
| FR-081  | Ministry admins MUST be able to view nationwide aggregates.                                                                              | MUST     |
| FR-082  | Admins MUST be able to inspect circuit breaker state for every monitored dependency.                                                     | MUST     |

---

## 3. Non-functional requirements

### 3.1 Performance

| ID       | Requirement                                                                                                                                | Target           |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------ | ---------------- |
| NFR-001  | p95 latency on `GET /api/v1/patients?q=…` MUST be ≤ 250 ms at 100 rps per replica.                                                          | ≤ 250 ms         |
| NFR-002  | p95 latency on `GET /api/v1/analytics/encounters-by-district` MUST be ≤ 500 ms warm cache, ≤ 2 s cold.                                      | per SLO          |
| NFR-003  | Offline mutation queue drain MUST complete in ≤ 60 s for a backlog of ≤ 200 mutations on a 3G connection.                                  | ≤ 60 s           |
| NFR-004  | Initial page load on the citizen portal MUST be ≤ 3 s on a slow-3G profile (Lighthouse).                                                   | ≤ 3 s            |

**V**: `scripts/loadtest-baseline.sh`, `scripts/loadtest-analytics.sh`, `scripts/loadtest-scaleout.sh`, plus Lighthouse CI on the citizen entrypoint.

### 3.2 Scalability

| ID       | Requirement                                                                                                                                | Target           |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------ | ---------------- |
| NFR-010  | API throughput MUST scale near-linearly from 1 to 3 backend replicas on the FHIR `Patient` search path.                                    | ≥ 80% efficiency |
| NFR-011  | The system MUST be sized for 6,937 facilities and 32M citizens (national rollout). Reference sizing in `SCALABILITY.md`.                   | Documented       |

### 3.3 Availability and resilience

| ID       | Requirement                                                                                                                                | Target           |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------ | ---------------- |
| NFR-020  | Production availability SLO MUST be ≥ 99.5% measured monthly at the public API.                                                            | 99.5%            |
| NFR-021  | Recovery Point Objective (RPO) MUST be ≤ 15 minutes.                                                                                       | ≤ 15 min         |
| NFR-022  | Recovery Time Objective (RTO) MUST be ≤ 60 minutes.                                                                                        | ≤ 60 min         |
| NFR-023  | Failure of any single downstream (NIRA, DHIS2, Redis) MUST NOT cascade to the encounter-capture flow. Verified by `scripts/preflight.sh`.  | Verified         |

### 3.4 Security

| ID       | Requirement                                                                                                                                | Target           |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------ | ---------------- |
| NFR-030  | All public endpoints MUST require TLS 1.2 or higher.                                                                                       | Enforced         |
| NFR-031  | Passwords MUST be hashed with bcrypt cost ≥ 12.                                                                                            | Enforced         |
| NFR-032  | Secrets (DB password, JWT secret, NIRA API key) MUST NOT be present in container images or git history.                                    | Verified         |
| NFR-033  | The system MUST support full audit trail export in a structured format suitable for PDPO inspection.                                       | Available        |
| NFR-034  | Vulnerability reports MUST be addressed per SLA in [SECURITY.md](../SECURITY.md) (48 h ack, 30 d fix for critical).                        | Tracked          |

### 3.5 Privacy and compliance

| ID       | Requirement                                                                                                                                | Target           |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------ | ---------------- |
| NFR-040  | The platform MUST satisfy each obligation in the DPPA 2019 traceability matrix (see `COMPLIANCE.md`).                                      | Mapped           |
| NFR-041  | A confirmed PHI breach MUST trigger a PDPO notification within 72 hours.                                                                   | Procedure exists |
| NFR-042  | Data MUST remain inside Uganda by default; export requires an explicit, audited authorisation.                                              | Enforced         |

### 3.6 Accessibility

| ID       | Requirement                                                                                                                                | Target           |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------ | ---------------- |
| NFR-050  | The UI MUST meet WCAG 2.2 AA across all citizen and worker surfaces.                                                                       | AA               |
| NFR-051  | Clinical text MUST meet WCAG 2.2 AAA contrast (7:1).                                                                                       | AAA              |
| NFR-052  | All interactive targets MUST be at least 44 × 44 px (WCAG 2.5.5).                                                                          | 44 × 44 px       |
| NFR-053  | The UI MUST be fully operable with keyboard only and with screen readers (VoiceOver / TalkBack).                                           | Verified         |

### 3.7 Localisation

| ID       | Requirement                                                                                                                                | Target           |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------ | ---------------- |
| NFR-060  | The citizen portal MUST ship English and Luganda for v1.                                                                                   | Met              |
| NFR-061  | The translation harness MUST support adding Runyankole, Luo, Lugbara, and Ateso without code changes outside `dictionary.ts`.              | Met              |

### 3.8 Maintainability

| ID       | Requirement                                                                                                                                | Target           |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------ | ---------------- |
| NFR-070  | Backend unit + integration test coverage MUST be ≥ 70%.                                                                                    | ≥ 70%            |
| NFR-071  | Frontend MUST pass `tsc --noEmit` with `strict: true`.                                                                                     | Enforced         |
| NFR-072  | Every architecturally-significant decision MUST be recorded as an ADR.                                                                     | Process exists   |

### 3.9 Observability

| ID       | Requirement                                                                                                                                | Target           |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------ | ---------------- |
| NFR-080  | Every API response MUST carry an `X-Trace-Id` header correlatable to OpenTelemetry traces.                                                  | Enforced         |
| NFR-081  | Application logs MUST be structured (JSON) and tagged with service, version, and trace id.                                                 | Enforced         |
| NFR-082  | Prometheus-compatible metrics MUST cover request rate, latency p50/p95/p99, error rate, breaker state.                                     | Exposed          |

### 3.10 Portability

| ID       | Requirement                                                                                                                                | Target           |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------ | ---------------- |
| NFR-090  | The platform MUST be deployable on NITA-U government cloud, on a Linux VM, and on a laptop (docker compose).                               | Met              |
| NFR-091  | No proprietary cloud APIs in the runtime path. All managed services MUST have an open-source equivalent (e.g. RDS → Postgres, MSK → Kafka). | Met              |

---

## 4. Traceability matrix (summary)

The full matrix is generated nightly by the build into `docs/_generated/traceability.json`. The summary view:

| Requirement | Code (primary)                                                                  | Test                                                            | ADR / Doc       |
| ----------- | ------------------------------------------------------------------------------- | --------------------------------------------------------------- | --------------- |
| FR-001      | `backend/app/api/v1/auth.py::citizen_login`                                     | `backend/tests/test_auth.py`                                    | SECURITY        |
| FR-010      | `backend/app/fhir/patient.py`                                                    | `backend/tests/test_validators.py`                              | ADR 0001        |
| FR-020      | `backend/app/api/v1/encounters.py::create_encounter`                             | `backend/tests/test_encounters.py`                              | ADR 0003        |
| FR-021      | `backend/app/middleware/idempotency.py`                                          | `backend/tests/test_encounters.py::test_idempotent_replay`      | ADR 0003        |
| FR-041      | `backend/app/supply/ledger.py`                                                   | `backend/tests/test_supply_ledger.py`                           | ADR 0004        |
| FR-050      | `backend/app/services/nira_client.py` + `app/core/resilience.py`                 | `backend/tests/test_resilience.py`                              | ADR 0002        |
| FR-052      | `backend/app/api/v1/fhir.py::capability_statement`                               | `scripts/fhir-conformance.sh`                                   | ADR 0001        |
| FR-060      | `frontend/src/lib/i18n/`                                                          | (manual + Storybook)                                            | DESIGN_SYSTEM   |
| NFR-001     | `backend/app/api/v1/patients.py::search`                                          | `scripts/loadtest-baseline.sh`                                  | SCALABILITY     |
| NFR-020     | `infra/` (Kubernetes manifests)                                                  | (ops-level monitor)                                             | SCALABILITY     |
| NFR-041     | n/a (procedure)                                                                  | DPIA tabletop drill                                             | DPIA            |
| NFR-050     | `frontend/src/app/globals.css` + components                                      | manual + Lighthouse                                             | DESIGN_SYSTEM   |

---

## 5. Out-of-scope (for v1)

The following are recognised as valuable but deliberately deferred. They are tracked but not blocking.

- Clinical decision support (drug-drug interactions, dosage warnings).
- Telemedicine video consultation.
- Insurance / NHIF claims adjudication.
- Lab result integration via HL7 v2 ADT/ORM/ORU.
- Multi-tenant private-sector hospital licensing.
- Genomic / research data warehousing.

These are revisited in [ROADMAP.md](./ROADMAP.md).

---

## 6. Change control

Requirements are amended only via a pull request that:

1. Updates this document (preserving stable IDs).
2. Updates or adds the corresponding test referenced in `V:`.
3. Is signed off by both an engineering reviewer and a clinical reviewer if the change touches PHI.

Retired requirements are kept in this document with the marker `RETIRED — <date> — <reason>` so historical traceability survives.
