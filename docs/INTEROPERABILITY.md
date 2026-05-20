# Interoperability

This document explains how HealthSync exchanges data with Uganda's existing health information systems.

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
