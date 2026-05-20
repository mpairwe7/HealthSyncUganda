# Local Innovation Value

What makes HealthSync Uganda *Ugandan* — and what tangible local impact a pilot can demonstrate.

---

## Built for Uganda's reality, not adapted from elsewhere

| Local-fit feature | Generic alternative would have | HealthSync chose |
|---|---|---|
| Identifier | NHS number / SSN / arbitrary UUID | **NIN** — 14-char NIRA format, validated at ingress (`app/schemas/common.py::_validate_nin`) |
| Facility hierarchy | "Clinic / Hospital" | **HC II → HC III → HC IV → HC → GH → RRH → NRH** — Uganda's actual MoH structure |
| Drug codes | RxNorm / proprietary | **EMHSLU** — Uganda's Essential Medicines & Health Supplies List |
| Geography | "City" | **District → Sub-county → Parish → Village** |
| Phone | E.164 generic | **+256-prefixed**, with mobile (`7x`) / landline (`3x`/`4x`) validation |
| Currency | USD | **UGX** for all monetary fields (`cost_ugx` on stock batches) |
| Demo data | "John Doe in Springfield" | **Akello in Pawel parish, Pageya, Cwero village — real Acholi names in Gulu** |
| Network assumption | Always-on broadband | **Offline-first PWA**; IndexedDB queue with replay (`frontend/src/lib/offline/`) |
| Demo languages | English only | **English + Luganda shipped**; Lusoga, Runyankole, Luo, Acholi scaffolded |

These are not localisation *patches* — they are first-class. Removing them would break tests.

## Built by Ugandans for Ugandans

- **Open source under Apache-2.0** — no vendor lock-in. The MoH can fork the codebase tomorrow.
- **Stack is locally re-staffable**: Python/FastAPI and TypeScript/Next.js are taught at Makerere COCIS, MUST, MUBS, and Uganda Technical College — so MoH can hire maintainers from the Ugandan graduate pool.
- **Documentation is in English, with Luganda translations of the citizen-facing strings**.
- **No proprietary dependencies** that route data, telemetry, or licensing through a non-Ugandan vendor by default.

## Three concrete impact commitments for a 2-district pilot

We make these falsifiable so the MoH can verify them at the end of the pilot.

| # | Commitment | Baseline | Target after 12 months | How we measure |
|---|---|---|---|---|
| 1 | **Reduce duration of ACT-AL stock-outs in pilot facilities by 50 %** | Median 14 days (HMIS data, 2024) | ≤ 7 days median | Stock-out events per facility per month, drawn from the ledger |
| 2 | **Lift childhood immunisation completion (DPT-3) in pilot districts by 5 percentage points** | District baseline from DHIS2 | +5 pp | Defaulter tracking via cross-facility records — children who got DPT-1 but not DPT-3 are surfaced as actionable lists |
| 3 | **Cut duplicate patient records at the pilot facilities by 80 %** | Estimated 8-12 % duplicate rate (paper + multiple EMRs) | ≤ 2 % | NIN-as-unique-key enforced in code; pre/post audit of facility registers |

## The local-vendor ecosystem

HealthSync deliberately uses common Ugandan-engineer skills so a local vendor ecosystem can grow around it:

- Postgres administration (MUBS Data-Science programme alumni)
- Python / FastAPI development (Outbox, Andela alumni, Makerere graduates)
- TypeScript / Next.js (LapTrust, Outbox, freelance bench in Kampala)
- Docker / Kubernetes (Refactory.dev graduates; NITA-U DevOps alumni)

Compare to a closed-source EMR import: only the vendor can extend it.

## Knowledge transfer commitments

If pilot is approved:

- **Monthly engineering office-hours**, open to any Ugandan engineer, recorded and posted.
- **Quarterly half-day MoH technical onboarding** sessions.
- **Annual internship cohort** (4 Makerere COCIS / MUST CS students) on a 6-month rotation.
- **Open hackathon** — annual — on extending HealthSync with new MoH modules.

## A note on humility

HealthSync is one of many Ugandan health-tech efforts (Clinic Master, M-TIBA, Mama Doc, Matibabu, Living Goods). We aim to **complement**, not replace — by being the open backbone they can each integrate with via FHIR R4. The product strategy is *infrastructure, not destination*.
