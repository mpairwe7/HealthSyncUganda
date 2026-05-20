# Data Protection Impact Assessment

> **Statutory basis:** Uganda *Data Protection and Privacy Act, 2019* (DPPA) and the *Data Protection and Privacy Regulations, 2021*.
>
> **Scope:** HealthSync Uganda — Interoperable National Digital Health Platform (this repository).
>
> **Status:** Living document. Authored by the engineering team for the 25 June 2026 Government Systems Prototype Showcase. Independent review prior to any production deployment is mandatory.

This DPIA is structured to the Personal Data Protection Office (PDPO) guidance: identify, assess, mitigate. Each section follows that pattern.

---

## 1. Project description & scope

HealthSync Uganda is a national digital health platform that:

- Stores **personally identifiable health data** linked to the National Identification Number (NIN).
- Exchanges data with other systems (NIRA, DHIS2, OpenMRS, eHMIS) via FHIR R4.
- Tracks medical supply movements between facilities.
- Records every access to PII in an immutable audit log.

The platform is intended for adoption by the Ministry of Health (MoH) of Uganda and hosted on NITA-U Government Cloud or comparable sovereign infrastructure.

## 2. Lawful basis (DPPA s.7)

| Processing activity | Lawful basis | Reference |
|---|---|---|
| Maintain a citizen's clinical record | Provision of medical care; statutory function of MoH | DPPA s.7(d); Public Health Act |
| Verify identity via NIN | Statutory function (NIRA Act) + consent at point of care | DPPA s.7(c) |
| Cross-facility record exchange | Explicit, granular, revocable consent | DPPA s.7(a); *Consent* model in `app/db/models/consent.py` |
| Aggregate analytics (district / ministry dashboards) | Statistical use under DPPA s.31 (de-identified or pseudonymised) | DPPA s.31 |
| Supply-chain inventory | Legitimate interest (non-personal data) | n/a |
| Audit logging of who accessed what | Legal obligation (DPPA s.14, s.27) + integrity protection | DPPA s.27 |

## 3. Data categories & flows

| Category | Examples | Sensitivity | Where stored | Where transmitted |
|---|---|---|---|---|
| Identity | NIN, full name, gender, DOB, district | High | `patients` table | Frontend over TLS; FHIR endpoints |
| Contact | phone, email | Medium | `patients` table | n/a |
| Clinical | encounters, vitals, diagnoses, vaccines | **Highest (special category)** | `encounters`, `observations` | Frontend over TLS only to authenticated worker; FHIR endpoints under role check |
| Consent | scope, purpose, grant/revoke timestamps | High | `consents` table | n/a |
| Audit | actor, resource, action, purpose | High | `audit_log` table | Mirrored to SIEM in production |
| Supply | drug movements, lots, expiry | Low (no personal data) | `stock_*` tables | Aggregated to district dashboards |

Personal data **never** leaves Uganda in the default deployment (`docs/ARCHITECTURE.md §11`).

## 4. Data-subject rights (DPPA Part V)

| Right (DPPA section) | How HealthSync supports it |
|---|---|
| Access to own data (s.24) | Citizen portal: `/citizen/records`; FHIR `Patient/{id}` with citizen-role gating |
| Rectification (s.25) | Worker-mediated correction via `PATCH /api/v1/patients/{id}`; `record_version` increments and audit captures changed fields |
| Erasure / "be forgotten" (s.26) | Soft-delete with tombstone; physical erasure gated by ministry-admin role; cascade to all downstream stores (Redis cache invalidation) |
| Objection / withdraw consent (s.27) | `POST /api/v1/consents/{id}/revoke` — immediate effect; cached responses invalidated within 60s |
| Be informed (s.6) | Citizen-portal landing page declares purpose, lawful basis, controller; layered notice on each consent grant |
| Lodge a complaint (s.32) | Contact details for the MoH Data Protection Officer (DPO) published in the citizen portal |

## 5. Risks & mitigations

| # | Risk | Likelihood | Impact | Mitigation in code/operations | Residual risk |
|---|---|---|---|---|---|
| R1 | Unauthorised PII access by a curious worker | Medium | High | `record_access()` writes an audit row with `actor_id`, `actor_role`, `purpose`, `consent_id` for every PII touch; the audit log is queried weekly by the DPO | Low |
| R2 | Stolen/lost device with cached records | Medium | High | Service worker caches only what the user actively viewed; IndexedDB encrypted at rest by the OS; session-only JWT (`sessionStorage`); short TTL (2h citizens, 8h staff) | Low–Medium |
| R3 | Mass scraping via search endpoints | Low | High | Rate limit (600 req/min/client/path); role-gated search; auditable | Low |
| R4 | Spoofed integrations (rogue "DHIS2") | Low | High | mTLS at the integration boundary in production; allow-listed callers; circuit-breaker isolates upstream impact | Low |
| R5 | Re-identification from "anonymous" analytics | Medium | Medium | All `/api/v1/analytics/*` outputs are aggregates only — no row-level cross-reference back to a citizen | Low |
| R6 | Cross-border data transfer (cloud vendor) | Low | High | Default deployment is on-premise / NITA-U; cloud backups encrypted client-side with keys held in Uganda | Low |
| R7 | Insider exfiltration | Low | High | Read-heavy paths audited; export endpoints rate-limited per actor; quarterly access review by DPO | Medium |
| R8 | Consent fatigue (citizens click "agree" without reading) | High | Medium | Layered notice (one-sentence summary + expandable detail); explicit purpose required at every facility | Medium |
| R9 | Children's data (under-18) | Medium | High | Guardian-consent flag required on patient creation when DOB < 18y; revocation by guardian or by the citizen on reaching majority | Low |
| R10 | Health-condition stigma (HIV, mental health, GBV) | Medium | Highest | Field-level encryption for stigma-sensitive observations (roadmapped); separate consent scope `share_with_research`; suppressed from cross-facility default view | Medium |

## 6. Vendor / processor management (DPPA s.21)

| Sub-processor | Role | Location | Safeguard |
|---|---|---|---|
| NITA-U Government Cloud (recommended host) | Infrastructure | Uganda | Government-owned; sovereign |
| NIRA | Identity verification | Uganda | Statutory; data-sharing MoU |
| MoH / DHIS2 | Aggregate reporting | Uganda | Statutory |
| (None of: AWS, GCP, Azure outside Uganda) | — | — | Default config does not use them; if used, encrypted backups only, with keys retained in Uganda |

## 7. Children & vulnerable subjects

- Patients under 18 require **guardian consent** (recorded with the consent scope).
- Workers must declare a **purpose** at every access, even for paediatric records.
- The citizen-portal is **not currently exposed to under-13s**; future work will add an "assisted view" for guardians.

## 8. Cross-border transfer (DPPA Part VI)

The default deployment performs **no cross-border transfer**. If a future deployment routes through a non-Ugandan cloud:

- Adequacy decision from PDPO is required, **or**
- Standard contractual clauses **plus** the data is pseudonymised before egress.

## 9. Retention & disposal (DPPA s.18)

| Data category | Retention | Trigger |
|---|---|---|
| Clinical records | Lifetime + 10 years | Death record |
| Audit log | 7 years (financial-class) | Rolling |
| Consent records | Lifetime | Tied to patient |
| Supply ledger | 10 years | Rolling |
| Cached / derived | 7 days (TanStack), 60s (analytics) | Rolling |

## 10. Outstanding work before production go-live

- [ ] Independent DPIA review by the MoH Data Protection Officer.
- [ ] Field-level encryption for stigma-sensitive categories (R10).
- [ ] Quarterly audit-log access review process documented in `docs/OPERATIONS.md`.
- [ ] Citizen-facing privacy notice translated into English, Luganda, Lusoga, Runyankole, and Luo.
- [ ] Penetration test by a Ugandan licensed firm (NITA-U CERT-UG-accredited).
- [ ] Submit Notification of Processing to the PDPO.

## 11. Approval

| Role | Name | Signature | Date |
|---|---|---|---|
| Project Lead | _to be signed_ |  |  |
| Data Protection Officer (MoH) | _to be signed_ |  |  |
| Information Security Lead | _to be signed_ |  |  |
| Clinical Advisor | _to be signed_ |  |  |
