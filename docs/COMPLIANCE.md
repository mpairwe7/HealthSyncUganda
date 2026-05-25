# Compliance Control Mapping

This document maps every relevant section of Uganda's *Data Protection and Privacy Act, 2019* (DPPA) and supporting frameworks to the concrete code or operational control in HealthSync Uganda that implements it. It is the artefact the showcase panel uses to score *Security and Compliance*.

> Each row is **falsifiable**: either the file/operation exists and behaves as described, or it doesn't.

---

## A. Uganda Data Protection and Privacy Act 2019

| Article | Obligation | HealthSync control | Evidence (file / operation) |
|---|---|---|---|
| s.3 | Definitions: personal data, special-category data | Clinical data marked special-category in our DPIA; treated with stricter controls | `docs/DPIA.md §3` |
| s.6 | Notice to data subject | Citizen portal landing displays purpose, controller, retention | `frontend/src/app/citizen/login/page.tsx` (privacy panel) |
| s.7 | Lawful basis | Documented per processing activity | `docs/DPIA.md §2` |
| s.9 | Data minimisation | Pydantic schemas accept only fields required for the use case (`extra="forbid"`) | `app/schemas/patient.py`, all FHIR models |
| s.10 | Purpose specification | Every PII access requires an explicit `purpose` field | `app/api/v1/patients.py:get_patient(purpose=...)` |
| s.11 | Accuracy | `record_version` on Patient bumps on every PATCH; rectification flow documented | `app/db/models/patient.py`, `app/api/v1/patients.py:update_patient` |
| s.12 | Storage limitation | Retention policy in DPIA; cache TTLs explicit (60 s analytics, 24 h idempotency, 7 d query cache) | `docs/DPIA.md §9` |
| s.13 | Integrity & confidentiality | Hash-chained audit log; bcrypt password hash; TLS 1.2+ | `app/db/models/audit_log.py`, `app/services/supply_ledger.py` |
| s.14 | Accountability | Every access logged with actor + purpose + consent_id | `app/core/audit.py:record_access` |
| s.17 | Security measures | Defense-in-depth: TLS, HSTS, rate-limit, RBAC, audit, idempotency, circuit-breakers | `docs/SECURITY.md` |
| s.18 | Retention | Documented + technical (cache TTLs + lifecycle policies on Postgres / Redis) | `docs/DPIA.md §9` |
| s.19 | Notification of breach | Breach playbook + 72-hour PDPO notification SLA | [`docs/INCIDENT_RESPONSE.md`](./INCIDENT_RESPONSE.md) — IR-30 notification template, IR-20…IR-25 incident classes |
| s.20 | Data Protection Officer (DPO) | MoH-appointed DPO; contact details published in citizen portal | Operational |
| s.21 | Sub-processor management | NITA-U + NIRA only by default; cross-border requires PDPO adequacy | `docs/DPIA.md §6, §8` |
| s.22 | Consent | Explicit, granular, revocable; child-guardian flagged | `app/db/models/consent.py` |
| s.24 | Right of access | Citizen portal `/citizen/records`; FHIR `Patient/{id}` self-read | `frontend/src/app/citizen/records/page.tsx` |
| s.25 | Right to rectification | Worker-mediated correction with audit | `app/api/v1/patients.py:update_patient` |
| s.26 | Right to erasure | Soft-delete + physical erasure gated by ministry-admin role; cascade to caches | Roadmapped — control gate exists, physical-erase script in `scripts/forget.sh` (Q3 2026) |
| s.27 | Right to object / withdraw consent | `/api/v1/consents/{id}/revoke`; cache invalidation within 60 s | `app/api/v1/consent.py:revoke` |
| s.29 | Cross-border transfer | None in default; controlled in roadmap | `docs/DPIA.md §8` |
| s.30 | Processing of special-category data | Highest-sensitivity clinical fields scoped for field-level encryption | `docs/DPIA.md §5 R10` |
| s.31 | Statistical / research use | Analytics endpoints emit aggregates only; no row-level export | `app/api/v1/analytics.py` returns counts/sums only |
| s.32 | Complaints to PDPO | Pathway documented; contact details in citizen portal | Operational |
| s.34 | PDPO registration | Notification of Processing filed before go-live | Operational |

## B. WHO / HL7 / clinical standards

| Standard | Use | Where |
|---|---|---|
| **HL7 FHIR R4** | National Health Information Exchange wire format | `app/fhir/*`, `/fhir/*` endpoints, `CapabilityStatement` at `/fhir/metadata` |
| **LOINC** | Lab and vital-sign observations | `Observation.code_system='http://loinc.org'` |
| **SNOMED CT** | Immunisation concepts | Vaccine observations in seed data |
| **ICD-10** | Diagnoses | `Encounter.diagnosis_codes` |
| **WHO Anatomical Therapeutic Chemical (ATC)** | Drug classification (roadmap) | `SupplyItem` will gain an `atc_code` column in Q3 2026 |
| **OpenHIE** architecture pattern | Health-info-exchange topology | HealthSync is an OpenHIE-compatible **point-of-service** + **shared health record** node |

## C. ISO / international baselines

| Standard | Self-assessment | Gap to formal certification |
|---|---|---|
| ISO 27001 (ISMS) | Controls aligned (access control, audit, incident, key management, supplier management) | Formal ISMS scope statement, internal audit, surveillance audits — operational work post-pilot |
| ISO 27799 (Health informatics — security) | Aligned with the *Patient Information* baseline | Formal gap analysis pending |
| ISO 13606 (Reference model for EHR comms) | Subsumed by FHIR R4 in our design | n/a |
| NIST CSF (Identify-Protect-Detect-Respond-Recover) | All five functions exercised in code | Maturity assessment pending |

## D. NITA-U Government cyber requirements

| Requirement | Status |
|---|---|
| Sovereign hosting (Uganda Government Cloud) | Default deployment supports this; documented in `docs/ARCHITECTURE.md §11` |
| TLS 1.2+ | Enforced at edge |
| Centralised logging (NITA-U SIEM compatible) | JSON-structured logs ship to any SIEM (Loki, Splunk, Elastic, Wazuh) |
| Vulnerability management | `bandit` (Python), `bun audit` (JS) wired into `make lint`; quarterly external scan planned |
| Incident reporting (CERT-UG) | 24-hour notification path in [`docs/INCIDENT_RESPONSE.md`](./INCIDENT_RESPONSE.md) §6 communication tree |

## E. Independent verifications scheduled before pilot

- [ ] DPIA review by an external Ugandan privacy counsel.
- [ ] Penetration test by a CERT-UG-accredited firm (5-day engagement target).
- [ ] Code review by Makerere COCIS faculty.
- [ ] Notification of Processing filed with the Personal Data Protection Office (PDPO).
- [ ] Risk-based audit-log access review process signed by the MoH DPO.

## F. Where this document fits

`docs/DPIA.md` is the risk register. `docs/SECURITY.md` is the engineering posture. **This file is the row-by-row mapping a panel auditor can walk down with a checklist in hand.**
