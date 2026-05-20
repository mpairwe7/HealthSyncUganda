# ADR 0001 — Use FHIR R4 as the primary clinical data model

- **Status**: Accepted
- **Date**: 2026-04-18
- **Decision-makers**: Architecture group + clinical lead
- **Consulted**: Ministry of Health DHI unit, Lacor Hospital IT lead

## Context

Uganda has at least four major clinical systems in production today —
**OpenMRS, DHIS2 Tracker, an in-house EMR at one regional referral hospital,
and several vendor-specific point solutions**. Each speaks a different on-the-
wire format, and patient records do not move between them. The National
Digital Health Strategy 2021-2025 (NDHS, §4.2) calls for "interoperable,
standards-based exchange" but does not mandate a specific standard.

We had to choose the canonical representation of clinical data inside the
HealthSync platform. The candidates were:

1. **HL7 FHIR R4** — JSON/XML, resource-oriented, RESTful, the de-facto modern
   standard. Production use at the U.S. VA, NHS England, India's ABDM.
2. **openEHR** — archetype-based reference model. Strong for long-term semantic
   stability; weak tooling outside the EHR vendor ecosystem.
3. **HL7 v2** — pervasive in lab/imaging but not browser-friendly; pipes-and-
   hats encoding is hostile to modern developers.
4. **Custom JSON / no standard** — fastest to prototype, expensive to maintain
   once you have more than one consumer.

## Decision

We adopt **HL7 FHIR R4** as the canonical wire format and storage shape for
clinical data. Every resource exposed on the public API conforms to a FHIR R4
profile. National extensions (e.g. NIN identifier slice) are published in
`backend/app/fhir/profiles/`.

For interop with legacy systems we run translation adapters:

- DHIS2 ↔ FHIR via the DHIS2 FHIR Adapter pattern.
- HL7 v2 (lab) ↔ FHIR via per-vendor mappers.

## Consequences

**Positive**

- A new vendor or research project can integrate in days by reading the
  published FHIR IG, not by negotiating bilaterally with us.
- Tooling — Inferno test kit, HAPI FHIR libraries, FHIR validators — exists
  and is well-maintained.
- The Ministry can credibly claim WHO SMART guideline conformance.
- Talent supply: we hire from a larger pool of developers who already know
  FHIR.

**Negative**

- FHIR R4 is verbose. A simple "blood pressure observation" carries dozens of
  fields, most of which are unused day-to-day. We mitigate with TypeScript
  helpers and FHIR-shaped UI primitives.
- We must publish and maintain a Uganda Implementation Guide. The first
  version covers Patient, Encounter, Immunization, MedicationDispense and
  Observation only.
- Some bespoke fields (Uganda subcounty taxonomy, indigenous language
  preferences) require extensions, which need explicit profile maintenance.

## Alternatives considered

**openEHR** was rejected because (a) the Ugandan dev ecosystem has effectively
zero openEHR experience, (b) tooling is dominated by one or two commercial
vendors, and (c) most regional peers (Kenya, Rwanda, Tanzania) are moving to
FHIR-based ecosystems, which matters for cross-border patient movement.

**Custom JSON** was rejected outright: the cost of being non-standard
compounds with every new integration partner.

## How we will know if this was wrong

- Onboarding a new integration partner takes longer than two weeks in
  > 25 % of cases (signal: the FHIR profile is missing or wrong).
- We accumulate more than ten extensions that should really be upstream
  proposals (signal: we're forking FHIR).
- An R5 / R6 migration becomes existentially expensive (signal: revisit
  storage strategy, perhaps move to FHIR-versioned canonical storage).

## Links

- NDHS §4.2.1 interoperability mandate — see `docs/MOH_ALIGNMENT.md`
- Uganda Patient profile — `backend/app/fhir/profiles/uganda_patient.json`
- Conformance harness — `scripts/fhir-conformance.sh`
