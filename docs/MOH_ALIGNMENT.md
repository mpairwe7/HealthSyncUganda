# Alignment with the National Digital Health Strategy 2021-2025

This document traces each HealthSync Uganda capability to a numbered priority in Uganda's National Digital Health Strategy (NDHS) 2021-2025 and the broader Uganda Digital Vision 2040. It is the artefact the Government Systems Prototype Showcase panel uses to score *Relevance to Government Needs*.

References:
- *Uganda National Digital Health Strategy 2021-2025* (Ministry of Health)
- *Uganda Digital Transformation Roadmap* (MoICT&NG)
- *Health Sector Development Plan III* (HSDP III, 2020/21-2024/25)
- *Uganda Vision 2040*

---

## NDHS Strategic Objectives → HealthSync features

| NDHS Objective | Description (summarised) | HealthSync delivers |
|---|---|---|
| **SO 1** | Governance & policy for digital health | Audit-by-default architecture, RBAC, DPIA, MoH-aligned consent model |
| **SO 2** | Interoperability & standards | FHIR R4 endpoints (`/fhir/Patient`, `/fhir/Encounter`, …), DHIS2 adapter, OpenMRS-compatible patient profile |
| **SO 3** | Service delivery (EMR, supply, M&E) | Patient records, supply-chain ledger, district & ministry analytics views |
| **SO 4** | Infrastructure & resilience | Offline-first PWA; circuit-breakers; gracefully-degrading dependencies |
| **SO 5** | Human capacity | Built on widely-taught stack (Python/FastAPI, TypeScript/Next.js, Postgres) — re-staffable from Makerere/MUBS/MUST graduates |
| **SO 6** | Data quality & use | Pydantic-strict validation; FHIR R4 conformance; immutable audit trail |
| **SO 7** | Equity & accessibility | Mobile-first; offline; low-bandwidth; multilingual (English + Luganda shipped, more roadmapped) |

## NDHS Tactical Priorities → Implementation

| Priority | NDHS reference | Where in HealthSync |
|---|---|---|
| Unique patient identifier linked to NIN | NDHS §4.2.1 | `app/fhir/patient.py` Uganda profile enforces exactly one NIN identifier with `system=https://nira.go.ug/identifiers/nin` |
| National Health Information Exchange | NDHS §4.2.3 | `/fhir/*` endpoints emit conformant R4 JSON; `CapabilityStatement` at `/fhir/metadata` |
| Logistics Management Information System (LMIS) interoperability | NDHS §4.4 | Supply chain module with FEFO dispense, hash-chained ledger, transfer between facilities |
| Real-time stock-out visibility | NDHS §4.4.2 | `/api/v1/supply/alerts/low-stock`; ministry dashboard |
| eHMIS form digitalisation | NDHS §4.3 | Encounter + Observation FHIR shapes map directly to HMIS 105 (outpatient), HMIS 077A (antenatal), HMIS 071 (immunisation) |
| Strengthening DHIS2 (not replacement) | NDHS §4.5 | DHIS2 client with `dataValueSets` push + outbox replay; never blocks clinical flow |
| Patient consent & data rights | NDHS §4.6 | `app/db/models/consent.py`; revocation propagates within 60 s |
| Cybersecurity baseline | NDHS §4.7 | TLS 1.2+, HSTS, bcrypt, rate-limit, audit log; aligned to DPPA 2019 in `docs/DPIA.md` |

## Uganda Vision 2040 → HealthSync contribution

| Vision 2040 outcome | HealthSync contribution |
|---|---|
| "Universal access to quality health services" | One canonical NIN-linked record means continuity of care anywhere in Uganda |
| "ICT as a strategic enabler" | Open-source, on-premise-deployable; trained Ugandan engineers |
| "Knowledge-based economy" | Open data formats (FHIR R4, OAuth, OpenTelemetry); enables a local health-tech vendor ecosystem |

## HSDP III alignment

| HSDP III Strategic Objective | Mapping |
|---|---|
| SO 1: Reduced morbidity & mortality | Cross-facility records prevent missed care and duplicate prescriptions |
| SO 2: Quality & safety of care | Audit log + observation typing reduces wrong-drug, wrong-dose, wrong-patient errors |
| SO 4: Effective, efficient & responsive health system | Supply-chain visibility cuts stock-out duration; district dashboards inform allocation |

## MoH-recognisable artefacts

Where Uganda's MoH already publishes a code system, HealthSync uses it directly:

| Domain | System | Used in HealthSync |
|---|---|---|
| Facility codes | MoH National Health Facility Master List | `Facility.code`, e.g. `MUL-NRH-001`, `GUL-RRH-002` |
| Drug codes | EMHSLU (Essential Medicines & Health Supplies List) | `SupplyItem.code`, e.g. `ACT-AL-001`, `ORS-001` |
| Diagnoses | ICD-10 (WHO) | `Encounter.diagnosis_codes` |
| Vital signs | LOINC | `Observation.code_system='http://loinc.org'` |
| Immunisations | SNOMED CT (with future MoH AEFI extension) | `Observation` codes 42284007 (BCG), 836382009 (OPV), … |
| Identifiers | NIRA NIN (`https://nira.go.ug/identifiers/nin`) | `Patient.identifier` |

## Three demonstrable MoH workflows

The 25 June showcase walks through three workflows that map 1-to-1 to MoH-published forms:

1. **HMIS 105 — Outpatient register** → FHIR `Encounter` with diagnosis code + observation(s).
2. **HMIS 077A — Antenatal care register** → FHIR `Encounter` with reason "Antenatal visit" + age/parity/BP observations.
3. **HMIS 071 — Immunisation register** → FHIR `Observation` with SNOMED-CT vaccine code + date.

The ministry analytics view aggregates these into the same indicators DHIS2 displays — *complementing* DHIS2, not replacing it.

## What HealthSync deliberately does **not** do (yet)

| Out of scope today | Rationale | Plan |
|---|---|---|
| Replace DHIS2 | DHIS2 is the country's standard; replacement is unnecessary disruption | Strengthen via FHIR + outbox |
| Billing / NHIS | Separate problem space; out of NDHS Strategic Objective 1-7 scope | Future module |
| Telemedicine | Network reality in 80% of HC II / HC III makes synchronous video unreliable today | Async store-and-forward roadmapped for Q4 2027 |
| Genomic / research data | Higher consent + governance burden; out of MVP scope | Separate consent scope `share_with_research` already modelled |

## Letters of intent (target before submission)

- [ ] Lacor Hospital (HC III + general hospital, Gulu) — primary pilot site
- [ ] Mulago National Referral — tertiary integration test
- [ ] One District Health Officer (Gulu DHO recommended)
- [ ] Makerere COCIS — academic partnership for student internships
- [ ] One donor partner (USAID Uganda Health Activity, GAVI Uganda, Global Fund Uganda)

These are operational deliverables — placeholders here intentionally — and are the highest-leverage *Relevance* score amplifier (see `docs/POSITIONING.md §3`).
