# Interoperability

**Audience:** MoH / NITA-U interoperability leads, OpenHIE assessors, FHIR / IHE reviewers, integrators (DHIS2, OpenMRS, eHMIS).
**Last reviewed:** 2026-05-25.

This document explains how HealthSync exchanges data with Uganda's existing health information systems — what we conform to today (FHIR R4 + Uganda profiles), what we are forward-compatible with (FHIR R5, IHE profiles), and where we sit in the OpenHIE reference architecture.

## Standard: FHIR R4

HL7 FHIR R4 is the interoperability layer. It is the same standard adopted by Kenya, Rwanda, Tanzania and 50+ countries worldwide — and the same one DHIS2 Tracker (used heavily across Africa) speaks natively.

### Resources implemented

| Resource | Endpoint | Notes |
|---|---|---|
| `CapabilityStatement` | `GET /fhir/metadata` | What this server supports |
| `Patient` | `GET /fhir/Patient/{id}` · `GET /fhir/Patient?identifier=…&family=…` | Uganda profile with NIN slice |
| `Encounter` | (search WIP) | Modelled in `app/fhir/encounter.py` |
| `Observation` | (search WIP) | Vitals, labs, immunisations |
| `MedicationDispense` | (search WIP) | Drug handoffs |
| `Bundle` | search responses | `searchset` mode used today |

### Patient profile (Uganda)

We bind the Uganda NIN identifier with system `https://nira.go.ug/identifiers/nin`. The validator in [`app/fhir/patient.py`](../backend/app/fhir/patient.py) enforces:

- Exactly one identifier with that system
- Value matches the NIRA format (`^C[MF][A-Z0-9]{12}$`)
- `birthDate` is not in the future

This means consumers (DHIS2 Tracker, OpenMRS) can rely on `identifier?system=https://nira.go.ug/identifiers/nin&value=…` as the canonical key.

### Code systems

We use the standard, internationally recognised code systems. A table of bindings is shipped in [`app/schemas/common.py:CodeSystems`](../backend/app/schemas/common.py).

| Domain | System | Example |
|---|---|---|
| Lab tests | LOINC | `8310-5` (Body temperature) |
| Diagnoses | ICD-10 | `B54` (Unspecified malaria) |
| Concepts | SNOMED CT | `42284007` (BCG vaccine product) |
| Identifiers | Uganda NIN | `https://nira.go.ug/identifiers/nin` |
| Facilities | Uganda Facility Master | `https://moh.go.ug/identifiers/facility-code` |
| Drugs | Uganda EMHSLU | `https://moh.go.ug/code/essential-medicines` |

The last two are HealthSync-defined namespaces that mirror the MoH's existing codes — when the MoH publishes canonical URLs, swap them in via a single search/replace.

## Integrations

### NIRA (identity)

`app/services/nira_client.py` is the adapter. Production integration is one config change away:

```env
NIRA_BASE_URL=https://api.nira.go.ug/v1
NIRA_API_KEY=<provisioned-by-NIRA>
```

The client is wrapped in `@resilient(breaker="nira")`. Failure modes:

1. Network timeout → retries 4× with backoff, then opens the breaker.
2. Breaker open → cached NIN responses served with `via_fallback=true` flag.
3. Cache miss + breaker open → hard fail, citizen receives a friendly error and a queued retry.

### DHIS2 (aggregate reporting)

`app/services/dhis2_client.py` posts data values to `/api/dataValueSets`. Failures pile into a Redis-backed queue (`dhis2:pending`) and are drained by:

- The next successful client call, or
- The admin endpoint `POST /api/v1/interop/dhis2/drain-queue`, or
- A background worker (cron / scheduled job — recommended in production).

This means a DHIS2 outage never blocks a clinical encounter; the data lands later.

### OpenMRS / eHMIS

The FHIR `Patient` and `Encounter` resources HealthSync emits are directly consumable by OpenMRS' Sync 2.0 module and by Uganda's eHMIS Patient Information Exchange. No custom translator needed.

## Synchronous vs asynchronous

Anything that touches a clinician's hot path is *synchronous*: identity verification, record fetch, encounter save. Anything that talks to an upstream that might be slow (DHIS2 aggregates, NIRA biometrics, eHMIS bulk imports) is asynchronous and queued.

## Outbound webhooks (roadmap)

HealthSync can also *push* changes — e.g. notify DHIS2 Tracker when a child is enrolled, or send an SMS via Uganda's UCC short code when an appointment is due. This is a planned `outbox` pattern on the same event bus we will use for the audit feed.

## Testing interoperability

The mock NIRA/DHIS2 endpoints are exposed under `/api/v1/interop/mock/*` so the demo runs without internet. Stripping these in production is a single line in `app/api/v1/router.py`.

---

## FHIR R5 forward-compatibility plan

HealthSync ships FHIR R4 today because that is what DHIS2 Tracker, OpenMRS, and Uganda's eHMIS speak in 2026. We have explicitly engineered for **forward migration to FHIR R5** so that as East African ministries (Kenya, Rwanda, Tanzania) and global donors (WHO, Gavi) move to R5 from 2027 onward, HealthSync follows without rewrite.

### Why R5 matters

R5 (HL7 normative ballot 2023; widely adopted from 2025 onwards) introduces:

- **`Permission` resource** — a structured representation of consent that supersedes R4's `Consent` resource. Maps cleanly to our `consents` table ([DATA_MODEL.md §3.10](./DATA_MODEL.md#310-consents--explicit-granular-revocable)).
- **`SubscriptionTopic`** — eventing primitive that replaces our outbound-webhook roadmap with a standards-based mechanism.
- **Tightened terminologies** — better LOINC/SNOMED conformance and improved ValueSet expansion semantics.
- **`Citation`, `Evidence`** — clinical-decision-support primitives we plan to use for indicator definitions in `MOH_ALIGNMENT.md`.

### Migration path (`IO-R5-NN`)

| ID       | Step                                                                                                          | Target            | Closure evidence                                                                                                                                                                          |
| -------- | ------------------------------------------------------------------------------------------------------------- | ----------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| IO-R5-01 | Version-negotiation header on `/fhir/*` (`Accept: application/fhir+json; fhirVersion=4.0` vs `5.0`)            | Pre-pilot         | New routes return R5 when negotiated; default remains R4. Conformance documented in updated `CapabilityStatement`.                                                                          |
| IO-R5-02 | Dual-version resource serialisers in `backend/app/fhir/` (R4 + R5 marshalling sharing a single canonical model) | Pre-pilot         | Round-trip tests: R4 in → canonical → R5 out, and R5 in → canonical → R4 out, with no semantic loss for the resources we implement.                                                       |
| IO-R5-03 | `Consent` → `Permission` mapping with bidirectional translator                                                | During pilot      | Mapping table in `backend/app/fhir/permission.py`; conformance harness includes both representations.                                                                                       |
| IO-R5-04 | `SubscriptionTopic` for outbound events (replaces ad-hoc webhook plan)                                         | During pilot      | Subscription endpoints emit FHIR R5 notifications; DHIS2 outbox migrates to `Subscription`-based dispatch where supported, falls back to current REST push otherwise.                       |
| IO-R5-05 | R5-native conformance run via `scripts/fhir-conformance.sh --version=5`                                       | Pre-national      | Conformance report archived per release; defects tracked as `IO-R5-*` issues.                                                                                                              |
| IO-R5-06 | Public `CapabilityStatement` advertises both versions                                                          | Pre-national      | `GET /fhir/metadata?fhirVersion=5.0` returns the R5 statement; R4 remains the default.                                                                                                      |

The migration does **not** require a database change. The on-the-wire representation differs; the canonical Postgres model is version-agnostic and the marshallers translate.

---

## OpenHIE alignment

The [Open Health Information Exchange (OpenHIE) Architecture v3](https://wiki.ohie.org/) is the reference architecture used by Kenya KeHMIS, Tanzania CHIS, Rwanda HMIS, Ethiopia eHMIS and others. It defines a set of components that talk to each other over standardised interfaces. HealthSync is structured as a set of OpenHIE **point-of-service (POS)** + **shared health record (SHR)** + **infrastructure** components.

| OpenHIE component                | HealthSync role                                                                  | Where it lives                                                                                                                       | Interface (what it speaks)                          |
| -------------------------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------- |
| **Client Registry (CR)**         | Source-of-truth for citizen identity (NIN-keyed)                                  | `backend/app/db/models/patient.py`; FHIR `Patient` endpoints                                                                          | FHIR R4 (R5 forward-compatible per IO-R5-*)         |
| **Health Worker Registry (HWR)** | Staff identity and roles                                                          | `backend/app/db/models/user.py`                                                                                                       | FHIR `Practitioner` (planned, IO-OHIE-01)            |
| **Facility Registry (FR)**       | Uganda facility hierarchy (HC II → NRH)                                            | `backend/app/db/models/facility.py`; FHIR `Organization` (planned, IO-OHIE-02)                                                        | FHIR R4 + master-facility-list URLs ([INTEROPERABILITY.md](#code-systems)) |
| **Shared Health Record (SHR)**   | Canonical clinical record store                                                   | `backend/app/db/models/encounter.py`, `observation` model; FHIR `Encounter`, `Observation`, `MedicationDispense` endpoints              | FHIR R4 (R5 forward-compatible)                       |
| **Terminology Service (TS)**     | Uganda code-system registry (NIN, EMHSLU, facility codes, LOINC, SNOMED, ICD-10)   | `backend/app/schemas/common.py:CodeSystems`                                                                                            | ValueSet expansion (planned, IO-OHIE-03)             |
| **Interoperability Layer (IL)**  | Adapter & resilience layer (DHIS2, eHMIS, OpenMRS, NIRA)                          | `backend/app/services/*_client.py`; circuit breakers + outbox queues                                                                  | OpenHIE-compatible HTTP-FHIR                          |
| **Aggregate Reporting (HMIS)**   | Tally push to DHIS2                                                               | `backend/app/services/dhis2_client.py`                                                                                                | DHIS2 `dataValueSets` REST API                        |
| **Point-of-Service (POS)**       | Citizen + worker PWA                                                              | `frontend/`                                                                                                                            | Internal REST (FHIR R4 also exposed for 3rd-party POS) |

Planned OpenHIE alignment work (`IO-OHIE-NN`):

| ID         | Step                                                                                  | Target       |
| ---------- | ------------------------------------------------------------------------------------- | ------------ |
| IO-OHIE-01 | Expose FHIR `Practitioner` and `PractitionerRole` endpoints                            | Pre-pilot    |
| IO-OHIE-02 | Expose FHIR `Organization` (facility) endpoints                                        | Pre-pilot    |
| IO-OHIE-03 | Terminology service: `$expand`, `$lookup`, `$validate-code` on the Uganda code systems  | During pilot |
| IO-OHIE-04 | OpenHIE conformance test suite run; report archived per release                        | During pilot |

---

## IHE profile alignment

[Integrating the Healthcare Enterprise (IHE)](https://www.ihe.net/) profiles are the *implementation specifications* that turn FHIR's abstract semantics into interoperable wire behaviour. The MoH IHE profiles relevant to a national digital health backbone are mapped below. Status is one of: **Conformant** (we pass the profile's actor tests), **Partial** (we implement most of the profile; gaps tracked), **Planned** (deferred to a target window).

| IHE profile                                             | HealthSync actor                | Status   | Notes                                                                                                                                            |
| ------------------------------------------------------- | ------------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| **PIXm** (Patient Identifier Cross-Reference Mobile)     | Patient Identifier Source        | Partial  | FHIR `Patient.identifier` includes NIN + facility-local IDs; cross-reference query planned (IO-IHE-01).                                            |
| **PDQm** (Patient Demographics Query Mobile)             | Patient Demographics Supplier    | Partial  | `GET /fhir/Patient?identifier=…&family=…` supports the demographics-query operation; full PDQm test-suite run pending (IO-IHE-02).                |
| **MHD** (Mobile access to Health Documents)              | Document Source / Recipient      | Planned  | Required for cross-facility document exchange. Targeted for pre-national (IO-IHE-03).                                                              |
| **mACM** (Mobile Alert Communication Management)         | Alerter / Receiver               | Planned  | Targeted for the SMS / WhatsApp / USSD alerting layer post-pilot (IO-IHE-04).                                                                       |
| **QEDm** (Query for Existing Data Mobile)                | Data Responder                   | Partial  | `Encounter` and `Observation` queries are supported; QEDm-specific profile test pending (IO-IHE-05).                                                |
| **ATNA** (Audit Trail and Node Authentication)           | Secure Application / Audit Repository | Partial | Audit semantics meet ATNA's intent ([SECURITY.md §"Audit & accountability"](./SECURITY.md)); FHIR `AuditEvent` representation planned (IO-IHE-06). |

Planned IHE conformance work runs in the **conformance harness** (`scripts/fhir-conformance.sh`) so each release publishes a profile-by-profile pass/fail matrix.

---

## Forward-looking trends (2026+)

These trends are tracked but not load-bearing for the showcase. They are documented here so panel reviewers see the platform is forward-aware.

- **FHIR Bulk Data Access (Flat FHIR).** Enables population-level export for research and reporting. Targeted for pre-national tier. Maps to MoH HMIS aggregate reporting flows.
- **SMART on FHIR App Launch.** Standard launcher for clinical apps that consume HealthSync data. Forward-compatible with our existing FHIR endpoints; only the launch handshake is missing.
- **HL7 CDS Hooks.** Decision-support service hooks (e.g. "do not prescribe X to a patient on Y"). Roadmap; analytics service is the natural home.
- **WHO ICD-11 transition.** Uganda follows the global ICD-10 → ICD-11 transition. The `Encounter.diagnosis_codes` field is a JSON array — additive, not breaking — making the dual-code period transparent.
- **Africa CDC Digital Health Strategy alignment.** Continental-level interoperability profiles in early consultation; HealthSync will adopt as they ratify.

