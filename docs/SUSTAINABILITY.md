# Sustainability Model

A digital public good is only useful if it is still being maintained five years later. HealthSync's sustainability path is **explicitly non-extractive**: the platform is and remains Apache-2.0 licensed and donatable to the Government of Uganda; revenue comes from services *around* the platform.

---

## Three revenue streams

| Stream | Description | Status |
|---|---|---|
| **1. Deployment & integration services** | Paid implementation: configure facilities, train workers, integrate with existing DHIS2/OpenMRS/eHMIS. Charged per pilot. | Designed |
| **2. Managed hosting (NITA-U-backed)** | Optional managed-service offering for facilities or districts that prefer to outsource ops. Hosted on NITA-U Government Cloud; we operate. | Designed |
| **3. Custom modules** | Sponsored development of vertical modules (TB contact tracing, AEFI, maternal mortality EWS). Sponsor retains no IP — feature merges into open source. | Designed |

We will **not** charge per-citizen-record, per-facility, per-call. The platform license is, and will remain, Apache-2.0.

## Funding pipeline (target before 25 June 2026)

| Source | Type | Amount target | Status |
|---|---|---|---|
| NIISP / NITA-U grant | Public | Tier-2 grant (UGX 50–150 M) | Application drafted |
| USAID Uganda Health Activity | Donor | Sub-grant for pilot | In conversation |
| GAVI Uganda | Donor | Module sponsorship (immunisation) | Concept note submitted |
| Global Fund Uganda | Donor | Module sponsorship (TB/HIV) | Pipeline |
| Innovation Village Kampala | Accelerator | Equity-free accelerator slot | Application open |
| MoH directly | Government | Co-investment for pilot | Conditional on facility endorsement |

## Cost model — 24-month pilot

| Item | UGX / yr | Notes |
|---|---|---|
| Core engineering team (4 FTE Ugandan) | 240 M | Includes social security |
| Clinical & policy advisors (0.4 FTE each, 3 people) | 36 M | Stipend |
| Infrastructure (NITA-U cloud) | 24 M | 3 backend replicas + HA Postgres + Redis |
| Training (workers in 30 facilities) | 30 M | 2-day sessions × 10 cohorts |
| Independent security review (annual) | 15 M | Local firm |
| DPIA / legal | 10 M | Annual update |
| Travel (district visits) | 18 M | 12 trips × 1.5 M |
| Contingency (10 %) | 37 M |  |
| **Annual total** | **~410 M UGX** | ~110k USD at May 2026 rates |
| **24-month pilot total** | **~820 M UGX** | |

## What we will *not* do

- Sell anonymised health data. The DPIA prohibits it, the Apache-2.0 fork can't override it, and the audit log makes it instantly visible.
- Lock the data in proprietary formats. Every export is FHIR R4 + Postgres dumps.
- Hold the MoH hostage on hosting. Self-host or NITA-U-host are first-class.
- Charge per-citizen, per-facility, per-API-call.

## Donation pathway

HealthSync is structured so the Government of Uganda can take it in-house at any time. A **Deed of Donation** template is in `docs/DONATION.md` (template) and a Q&A on transition logistics is in the Phase 5 of `docs/ROADMAP.md`.

## Independent reporting

- **Annual financial report** published openly.
- **Quarterly impact metrics** (facilities live, citizens served, stock-out duration reduction, immunisation drop-off reduction).
- **Annual DPIA review** by MoH DPO.

## Why this model holds

It is not a B2B SaaS. The product is a **digital public good**. Revenue follows from services that *only the maintainers can credibly perform* — implementation, training, integration — not from the right to use the software. This separates "platform license" from "consulting business" *cleanly*, removes vendor-lock-in incentive, and is the same model OpenSRP, OpenMRS, DHIS2 and Bahmni have proven for 10+ years.
