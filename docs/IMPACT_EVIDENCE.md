# Impact Evidence

**Audience:** Showcase panel (scores *Local Innovation Value* and *Usability & Accessibility*); MoH M&E unit; pilot district health teams.
**Status:** methodology, commitments, and measurement plan are complete. **Pilot result rows are explicitly marked `[Pilot lead to populate]` and must be filled with real measurements before any claim is made publicly** — fabricated numbers in a government submission are misrepresentation, not "polish".
**Last reviewed:** 2026-05-25.

This document sits next to [LOCAL_VALUE.md](./LOCAL_VALUE.md), which states the three impact commitments. IMPACT_EVIDENCE.md is the **measurement plan** plus the **structured slots** for measured results. Where a result is pending, the slot points at the script or protocol that will produce it.

Stable IDs: `IE-NN`.

---

## 1. Why this document exists separately

LOCAL_VALUE.md states *what* HealthSync commits to (and that the commitments are falsifiable). IMPACT_EVIDENCE.md is *how* the falsification happens — the baselines, the instruments, the control groups, the recording cadence, and the sign-off discipline that turns each commitment into a defensible number.

Keeping the two documents separate means:

- The commitment in LOCAL_VALUE.md does not drift when we refine the methodology.
- The methodology in this document does not get edited to flatter the result.
- Auditors can compare the *commitment as stated at submission time* with the *measured result at pilot end* against a single, immutable methodology.

---

## 2. Three impact commitments (canonical: LOCAL_VALUE.md)

LOCAL_VALUE.md §"Three concrete impact commitments for a 2-district pilot" carries the canonical commitment table. Repeated here for context only — the cell values are mirrored, not authoritative:

| # | Commitment                                                                  | Baseline (per LOCAL_VALUE.md)                              | Target after 12 months           |
| - | --------------------------------------------------------------------------- | ---------------------------------------------------------- | --------------------------------- |
| 1 | Reduce duration of ACT-AL stock-outs in pilot facilities by 50 %             | Median 14 days (HMIS data, 2024)                            | ≤ 7 days median                   |
| 2 | Lift childhood immunisation completion (DPT-3) in pilot districts by 5 pp    | District baseline from DHIS2                                 | +5 pp                             |
| 3 | Cut duplicate patient records at the pilot facilities by 80 %                 | Estimated 8–12 % duplicate rate (paper + multiple EMRs)     | ≤ 2 %                             |

If a commitment value in LOCAL_VALUE.md changes, this section is updated in the same PR.

---

## 3. Baselines (cited public sources)

The credibility of the targets depends on the credibility of the baselines. We cite the sources we believe authoritative, with the caveat that several pre-pilot baselines must be **recomputed against the specific pilot districts** before the pilot starts so the post-pilot comparison is like-for-like.

| ID    | Baseline                                                       | Source / method                                                                                                                                                                                                                                       | Status                                                                                                                          |
| ----- | -------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------- |
| IE-01 | Median duration of ACT-AL stock-out in HC II–IV (national)      | Uganda MoH HMIS / DHIS2 data for 2024, summarised in LOCAL_VALUE.md as a 14-day median. **Sub-district aggregation against the named pilot districts must be reproduced from DHIS2 before pilot start** — generic-national medians are indicative only. | National baseline cited; pilot-district baseline `[Pilot lead to extract from DHIS2 before kickoff]`.                              |
| IE-02 | DPT-3 coverage at the pilot districts                            | Uganda DHIS2 district indicators (the existing MoH source of truth for immunisation coverage).                                                                                                                                                          | Extract for the named pilot districts `[Pilot lead to extract before kickoff]`. National coverage trends in NDHS 2021–2025.       |
| IE-03 | Duplicate patient-record rate at the pilot facilities             | Pre-pilot audit: a structured 100-record sample per facility, two raters classifying duplicates blind. LOCAL_VALUE.md estimates 8–12 % as the realistic range based on paper + multiple-EMR pre-pilot environments.                                       | Audit form template in `docs/audit-templates/duplicate-records.md` (to be added). Outcome: `[Pilot lead to record before kickoff]`. |
| IE-04 | Patient enrolment offline tolerance                              | Direct PWA verification per [FRONTEND_SETUP.md §6](./FRONTEND_SETUP.md#6-verify-the-offline-path). Reproduces a real low-connectivity scenario in DevTools.                                                                                              | Methodology proven; submission-time evidence captured into §6 Lighthouse / PWA results.                                          |
| IE-05 | Cross-facility duplicate detection                                | Pre-pilot audit + NIN-uniqueness query (`SELECT nin, COUNT(*) FROM patients GROUP BY nin HAVING COUNT(*) > 1`).                                                                                                                                         | Code path proven; pilot baseline captured at pilot start.                                                                          |

**Caveat on national-scale baselines.** Where this document quotes a national-level number (e.g. national DPT-3 coverage, national stock-out median), the credibility lies with the underlying MoH / DHIS2 publication, not with HealthSync. The submission packet links to the specific MoH / NDHS / DHIS2 reports — placeholder `[Citation to populate]` until the published reference URL is verified.

---

## 4. Measurement methodology

### IE-10 — Stock-out duration

| Item                  | Specification                                                                                                                                                       |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Instrument             | Supply-ledger query: `SELECT facility_id, gap_start, gap_end FROM (compute gaps between successive 'receive' events where remaining=0) AS stockout_intervals;`        |
| Frequency              | Continuous; aggregated weekly.                                                                                                                                       |
| Unit                   | Days between a `remaining → 0` event and the next `receive` event for the same `(facility, supply_item)`.                                                            |
| Boundary               | Stock-out events open at the start of the measurement window are right-censored at the window edge.                                                                  |
| Reporting              | Median (50th percentile) over all events in the window per facility; aggregated to district median for the targeting indicator.                                       |
| Control                | Stock-out duration in two **non-pilot** comparator districts (`[Comparator A]`, `[Comparator B]`) is reported alongside.                                              |
| Sign-off               | Pilot M&E officer + an independent reviewer from the MoH M&E unit cross-sign each weekly report.                                                                       |

### IE-11 — DPT-3 coverage

| Item                  | Specification                                                                                                                                                            |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Instrument             | DHIS2 standard indicator (`Immunization — DPT-3`) at district level + HealthSync defaulter-tracker output (children with DPT-1 but no DPT-3 by 14 weeks).                |
| Frequency              | Monthly.                                                                                                                                                                  |
| Unit                   | Percentage points difference: month-12 minus month-0 for each pilot district.                                                                                              |
| Boundary               | Children born in the 12-month window only (avoid mixing pre-existing cohort).                                                                                              |
| Reporting              | District trend chart + cohort-survival table.                                                                                                                              |
| Control                | DPT-3 trend in non-pilot comparator districts, same 12-month window.                                                                                                       |
| Sign-off               | Pilot M&E officer + the district immunisation focal point + the public-health advisor in [TEAM.md §1.4](./TEAM.md#14-advisors-and-reviewers).                              |

### IE-12 — Duplicate patient records

| Item                  | Specification                                                                                                                                                                                                                  |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Instrument             | Pre-pilot audit (100-record blind sample per facility, two raters); post-pilot audit (same protocol); SQL duplicate-count query (`SELECT nin, COUNT(*) FROM patients GROUP BY nin HAVING COUNT(*) > 1`).                       |
| Frequency              | Pre-pilot (baseline) + month-12 (endpoint).                                                                                                                                                                                      |
| Unit                   | Proportion of records sharing an identifying triple (`given_name`, `family_name`, `birth_date`) with another record.                                                                                                            |
| Sample                 | 100 records per facility, drawn deterministically by ULID-sorted order with a fixed seed for reproducibility.                                                                                                                    |
| Reporting              | Pre/post audit table per facility + district aggregate.                                                                                                                                                                          |
| Sign-off               | Audit conducted by two raters; agreement reported; disagreements resolved by the clinical advisor.                                                                                                                              |

### IE-13 — Recording, archiving, and traceability

- Every weekly / monthly report is committed as a markdown file under `docs/m-and-e/<commitment>-<YYYY-MM-DD>.md` (directory created on first report).
- Every report includes the source query, the time range, the raw row count, and the analyst's name. Reproducibility is the price of admission.
- The MoH M&E unit is granted read access to the M&E directory at pilot start.

---

## 5. Projected impact (modelling assumptions)

We separate the *commitment* (which we are accountable for) from the *projection* (what the commitment is likely to look like once realised). The projection is an **engineering estimate**, not a guarantee.

| Commitment            | Projection                                                                                          | Modelling assumptions                                                                                                                                                                                                                                                                                                |
| --------------------- | --------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 — Stock-outs        | Stock-out median falls from 14 → 6–8 days within 6 months; ≤ 7 days median at month-12              | Low-stock alerts trigger 5 days before remaining = 0; district pharmacist initiates transfer within 48 h; transfer-execution time is 24–72 h; assumes baseline supply availability at the source facility. **If the source facility is also stocked-out, HealthSync cannot fix the problem and the target is missed.** |
| 2 — DPT-3 coverage    | +3–6 pp over 12 months in the pilot districts                                                       | Defaulter-tracker shifts 30–50 % of identified defaulters into completion (literature on similar interventions in East Africa places this in a 25–60 % band).                                                                                                                                                          |
| 3 — Duplicate records | Falls from estimated 8–12 % → ≤ 2 % at month-12                                                     | NIN-as-unique-key is enforced in code (`unique=True`); de-duplication exercise at pilot start identifies and merges existing duplicates; new-enrolment errors detected at write time.                                                                                                                                  |

The projection ranges are documented so that a panel reviewer (or future auditor) sees the team's stated expectation alongside the binding commitment. If the result lands inside the projection range, the team's modelling is calibrated. If the result is below projection but meets the commitment, the modelling under-estimated. If below the commitment, the post-pilot review names the cause.

---

## 6. Usability & accessibility results

The platform makes specific commitments to Lighthouse and axe-core scores. The **methodology and targets** are documented here; the **measured results** are captured into archived report files immediately before submission and are listed below at submission time.

### IE-20 — Lighthouse PWA + Core Web Vitals

**Targets (across landing, login, citizen records, worker dashboard, admin):**

| Category         | Target |
| ---------------- | ------ |
| Performance       | ≥ 85   |
| Accessibility     | ≥ 95   |
| Best Practices    | ≥ 90   |
| SEO               | ≥ 90   |
| PWA               | ≥ 90   |

**Reproduction recipe:**

```bash
make full                                                       # backend + frontend + db + redis
bun run --cwd frontend build && bun run --cwd frontend start &  # production build

# Per page, write a JSON + HTML report
for page in / /login /citizen/records /worker /admin; do
  npx lighthouse "http://localhost:3000${page}" \
    --output=json --output=html \
    --output-path="lighthouse-results/$(date +%F)/${page//\//_}.json" \
    --chrome-flags="--headless --no-sandbox"
done
```

**Submission evidence:**

| Page                  | Performance | Accessibility | Best Practices | SEO  | PWA  | Report file                                                                |
| --------------------- | ----------- | ------------- | -------------- | ---- | ---- | -------------------------------------------------------------------------- |
| `/`                   | `[score]`   | `[score]`     | `[score]`      | `[s]`| `[s]`| `lighthouse-results/[YYYY-MM-DD]/_.json`                                    |
| `/login`              | `[score]`   | `[score]`     | `[score]`      | `[s]`| `[s]`| `lighthouse-results/[YYYY-MM-DD]/_login.json`                               |
| `/citizen/records`    | `[score]`   | `[score]`     | `[score]`      | `[s]`| `[s]`| `lighthouse-results/[YYYY-MM-DD]/_citizen_records.json`                    |
| `/worker`             | `[score]`   | `[score]`     | `[score]`      | `[s]`| `[s]`| `lighthouse-results/[YYYY-MM-DD]/_worker.json`                              |
| `/admin`              | `[score]`   | `[score]`     | `[score]`      | `[s]`| `[s]`| `lighthouse-results/[YYYY-MM-DD]/_admin.json`                               |

> Empty `[score]` cells: **run the recipe and populate before submission**. Do not write a number you did not measure.

### IE-21 — Axe-core accessibility

**Target:** **0 serious / 0 critical** violations on each landing + workflow page. Other severities documented and triaged.

**Reproduction recipe:**

```bash
for page in / /login /citizen/records /worker /admin; do
  npx @axe-core/cli "http://localhost:3000${page}" \
    --save "axe-results/$(date +%F)/${page//\//_}.json"
done
```

**Submission evidence:**

| Page                  | Critical | Serious | Moderate | Minor | Report file                                          |
| --------------------- | -------- | ------- | -------- | ----- | --------------------------------------------------- |
| `/`                   | `[n]`    | `[n]`   | `[n]`    | `[n]` | `axe-results/[YYYY-MM-DD]/_.json`                   |
| `/login`              | `[n]`    | `[n]`   | `[n]`    | `[n]` | `axe-results/[YYYY-MM-DD]/_login.json`              |
| `/citizen/records`    | `[n]`    | `[n]`   | `[n]`    | `[n]` | `axe-results/[YYYY-MM-DD]/_citizen_records.json`    |
| `/worker`             | `[n]`    | `[n]`   | `[n]`    | `[n]` | `axe-results/[YYYY-MM-DD]/_worker.json`             |
| `/admin`              | `[n]`    | `[n]`   | `[n]`    | `[n]` | `axe-results/[YYYY-MM-DD]/_admin.json`              |

### IE-22 — Manual a11y verification (per WCAG 2.5.5 + screen-reader sample)

In addition to automated tools, a manual pass verifies:

- All interactive elements have ≥ 44 × 44 px touch target (WCAG 2.5.5 — pinned in `globals.css`).
- Skip-to-main-content link is the first focusable element (already in `frontend/src/app/layout.tsx`).
- Forms are navigable with keyboard alone.
- A screen reader (NVDA on Windows or VoiceOver on macOS) reads the citizen-records page coherently.

Outcome: `[Pilot lead to record before submission; sign-off note in docs/m-and-e/a11y-manual-YYYY-MM-DD.md]`.

---

## 7. Clinical rehearsal outcomes

A clinical rehearsal is a controlled walkthrough of the showcase journey with a real clinician, in a non-patient-facing environment, capturing the clinician's reactions on:

- Whether the flows match real practice.
- Whether any prompt is ambiguous or unsafe.
- Whether the offline behaviour is intuitive.
- Whether the consent and audit explanations are understandable.

### IE-30 — Protocol

1. **Participants.** At least one general-practice clinician (named in [TEAM.md §1.4](./TEAM.md#14-advisors-and-reviewers)) + a pharmacist + a district health team representative.
2. **Setting.** Test environment with seeded demo data; non-patient-facing; recorded with participant consent.
3. **Script.** Walk the citizen, worker, and pharmacist arcs in [DEMO_SCRIPT.md](./DEMO_SCRIPT.md), including the offline / breaker / consent revocation moments.
4. **Observation framework.** Think-aloud method; observer captures hesitations, navigation errors, vocabulary mismatches.
5. **Reporting.** Free-text observation document + a categorised defect list with severity. Filed under `docs/rehearsals/clinical-rehearsal-YYYY-MM-DD.md`.
6. **Sign-off.** Each participant signs the report — either approving the flows or itemising required changes.

### IE-31 — Outcome

> Rehearsal status at submission time. `[Pilot lead to populate]`. Empty until a real rehearsal has occurred and is documented.

| Item                                    | Result                                                                 |
| --------------------------------------- | ---------------------------------------------------------------------- |
| Date                                    | `[YYYY-MM-DD]`                                                         |
| Participants                            | `[Names + roles]`                                                      |
| Major findings                          | `[Bullet list — summarise from the rehearsal report]`                  |
| Defects raised                          | `[N raised, of which M resolved before submission]`                    |
| Sign-off                                | `[Names of participants who signed]`                                   |
| Report file                             | `docs/rehearsals/clinical-rehearsal-[YYYY-MM-DD].md`                    |

### IE-32 — Standing rehearsal cadence

After the showcase, clinical rehearsals continue on a **quarterly** cadence as part of the Architecture Review Board (per [TEAM.md §3.3](./TEAM.md#33-standing-review-cadences)). Each release with a user-flow change must be rehearsed before release.

---

## 8. Comparator and counterfactual

A panel reviewer will ask: "Without HealthSync, what would the pilot districts look like at month-12?" The honest answer:

- **Stock-outs:** likely unchanged from baseline — the underlying supply chain is the binding constraint and HealthSync only improves *visibility* and *response time*. Where the source facility is also stocked-out, HealthSync cannot fix it. The 50 % target is calibrated against the visible-source case (estimated 60–70 % of pilot events).
- **DPT-3 coverage:** the national trend is gently upward (per NDHS 2021–2025) regardless of HealthSync. The commitment is the *delta vs comparator districts*, not the absolute number.
- **Duplicate records:** without HealthSync the rate is likely to drift slowly downward as paper records age out. The 80 % reduction target is the active-intervention case (NIN enforcement + de-dup exercise).

The two non-pilot comparator districts (named in the methodology) are the counterfactual. Their numbers — drawn from the same DHIS2 / HMIS sources — are reported alongside the pilot numbers at month-12.

---

## 9. Honest limitations

- **12-month pilot is short.** Behaviour change in supply-chain and immunisation systems is multi-year. The first-year result is a leading indicator, not a definitive outcome.
- **Two pilot districts are a small N.** Statistical claims are bounded; the report leans on direction-and-magnitude rather than p-values.
- **Self-reported DHIS2 data quality is uneven.** Stock-out duration and DPT-3 coverage both depend on the underlying HMIS data being accurately reported. Where the baseline data are themselves suspect, HealthSync's improvement appears either inflated or muted by the same factor — the report explicitly notes this.
- **Hawthorne effect.** Pilot facilities know they are being observed. The comparator districts give us a check against this.

These limitations are why the methodology demands the comparator districts, the pre-pilot baseline recomputation, and the dual-rater audit — they are not afterthoughts.

---

## 10. Cross-references

- [LOCAL_VALUE.md](./LOCAL_VALUE.md) — canonical commitment table.
- [SHOWCASE_EVALUATION_MAPPING.md](./SHOWCASE_EVALUATION_MAPPING.md) — `EV-LV-06`, `EV-UA-03`, `EV-UA-04`, `EV-UA-08` point at this document.
- [MOH_ALIGNMENT.md](./MOH_ALIGNMENT.md) — NDHS 2021–2025 trace; this document's indicators map upward into NDHS strategic objectives.
- [TEAM.md §3.3](./TEAM.md#33-standing-review-cadences) — rehearsal cadence governance.
- [DEMO_SCRIPT.md](./DEMO_SCRIPT.md) — script that clinical rehearsals follow.
- [FRONTEND_SETUP.md §6](./FRONTEND_SETUP.md#6-verify-the-offline-path) — offline-path verification recipe (IE-04).
- [docs/m-and-e/](.) — output directory for monthly M&E reports (created on first report).
- [docs/rehearsals/](.) — output directory for clinical-rehearsal reports (created on first rehearsal).
