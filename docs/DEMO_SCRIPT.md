# Demo script — Government Systems Prototype Showcase

**Date:** Thursday 25 June 2026
**Audience:** Ministry of Health, NITA-U, NIRA, Office of the President's ICT advisors, members of the National Innovator Registry selection panel.
**Duration:** 8 minutes (6 min walkthrough + 2 min Q&A buffer)
**Presenters:** [Lead engineer] + [Health domain advisor]

---

## The story we tell

> *"Other systems collapse when the network goes down. Other systems collapse when a downstream like DHIS2 misbehaves. We built one that doesn't — and we'll show you in the first thirty seconds."*

We **open with resilience**, then earn the panel's attention to walk them through what each role actually does.

---

## Setup (the morning of)

```bash
# Clean rehearsal state, then bring the full stack up
make reset                              # only if a previous demo dirtied the DB
make full                               # docker compose --profile full up --build

# In a separate shell, before stepping on stage:
make preflight                          # verifies Postgres, Redis, FHIR, auth, breakers
./scripts/fhir-conformance.sh           # prints a green checklist — keep it on screen
```

Have **four browser windows / terminals** open before stepping on stage:

1. **Citizen** — `http://localhost:3000/citizen/login` (mobile-sized viewport)
2. **Worker** — `http://localhost:3000/login` (tablet-sized viewport)
3. **Ministry** — `http://localhost:3000/admin` (full screen)
4. **Terminal** — pre-loaded with the breaker-trip and offline-toggle commands

Have **OBS / browser dev tools** ready to flip the network offline on cue.

---

## Walkthrough — 6 minutes, every second counted

### ⏱ 0:00 — 1:00 · The resilience opening (the differentiator first)

Switch to the **Ministry window** on the Compliance + Stock-out dashboards.

> *"This is HealthSync Uganda, running live. Before I show you anything pretty, I want to show you what happens when things go wrong — because that is where every other system in this room has failed."*

Run, in the **terminal**:

```bash
curl -X POST http://localhost:8000/api/v1/interop/circuits/dhis2/trip \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

> *"I just simulated DHIS2 — the national HMIS — going down. Watch the dashboards."*

Refresh the Ministry view. Point to:

- **The page still renders.** Cached aggregates served with a small "stale" banner.
- The **resilience card**: `dhis2 circuit = OPEN`, queue depth rising.
- The **encounter recording flow is still green**.

> *"The clinician in front of a patient does not know — and does not need to know — that DHIS2 is down. Pushes are queued; the breaker will half-open in thirty seconds; when DHIS2 returns the queue drains. No one in this room has to phone anyone."*

(Optional, if time allows: toggle the breaker closed, watch the queue drain to zero.)

> *"That is the spine of the platform. Now let me show you what sits on top of it."*

### ⏱ 1:00 — 2:00 · A citizen sees her own record

Open the **citizen window**. Use the **language switcher** in the header to flip to **Luganda** for the first 10 seconds; flip back to English.

Log in:

- NIN: `CM85051712345X` (Akello — Gulu)
- OTP: `000000`

> *"Akello visited a HC III in Gulu last week. Today she's in Kampala for a different reason. She doesn't need to bring paper. She doesn't need to remember her vaccine history. She just signs in with her NIN."*

Go to **My records**. Show the cross-facility encounter list. Point out:

- Encounters at multiple facilities — one timeline.
- Diagnoses in ICD-10 codes.
- Observations (vitals, vaccines) properly typed in LOINC / SNOMED CT.

Open **Consent centre**. Revoke one consent.

> *"She is in charge. Every consent is granular, every revocation is immediate, every access is in the audit log she can read herself — in English or Luganda."*

### ⏱ 2:00 — 3:30 · A nurse in Gulu enrols a patient offline

Switch to the **worker window**. Log in as `nurse.gulu` / `demo1234`.

Go to **Enrol patient**. Fill in a record while telling the story:

> *"Susan, a nurse at Lacor HC III, has a new mother in front of her. There's no internet today — typical for Tuesday."*

**Toggle the network offline** in dev tools.

Submit the form. Point to:

- The toast: *"Saved offline — will sync when network returns"*.
- The header **sync indicator**: a number rises, the colour shifts amber.

> *"The record is safe. It's in the device's IndexedDB. The form moved on. Susan can keep working."*

Open a fresh tab — show the patient list still works (cached). Toggle network back on. Watch the sync indicator drain to zero. Refresh the list — the new patient is there.

> *"Same record. One source of truth. No re-entry. The server rejected the duplicate because every offline mutation carries an idempotency key."*

### ⏱ 3:30 — 4:45 · A pharmacist resolves a stock-out

Log out, log in as `pharmacist.mbarara` / `demo1234`.

Open **Supply**. The dashboard highlights:

> *"Mbarara RRH is below threshold on Artemether/Lumefantrine. 120 doses left, threshold 500. If we do nothing, they stock out in days."*

Use the **Initiate transfer** form:

- From: Mulago NRH
- To: Mbarara RRH
- Item: Artemether/Lumefantrine
- Quantity: 500
- Reason: "Replenishment — below threshold"

Submit. Show the toast and the table update.

> *"Every transfer is a hash-chained ledger entry. We can prove what moved, where, by whom. An external auditor can verify the chain without access to our database — the hash anchor is published in the Ministry's daily bulletin."*

(Optional: switch to a terminal and run `curl http://localhost:8000/api/v1/supply/ledger/verify` to show the chain as `OK`.)

### ⏱ 4:45 — 5:45 · The Ministry sees the country

Back on the **Ministry window**. Log in as `admin` / `admin1234` if needed.

Talk through:

- **Encounters by district** (bar chart) — backed by FHIR `Encounter` resources.
- **Immunisation coverage by antigen** — sourced from observations against SNOMED CT codes; broken down per Uganda EPI schedule.
- **Stock-out risk** — only Mbarara's ACT row is gone (we just fixed it!).

Scroll to the **Compliance posture** card.

> *"This isn't a vanity board. Each green checkmark is verifiable. The audit log is append-only. Every PII access has a purpose and a consent. The supply ledger chain is verified. DHIS2 backlog is drained — even though we just tripped it."*

### ⏱ 5:45 — 6:00 · Standards proof

Switch to the **terminal** showing the conformance report:

> *"Every claim about FHIR R4, NIN profiles, LOINC coding is verified by `fhir-conformance.sh` on every commit. 18 checks. Green. Open the file — you can run it on your own machine in 30 seconds."*

---

## Closing — 30 seconds

> *"HealthSync Uganda is open source under Apache-2.0, built on open standards, runs on NITA-U's cloud or on a laptop in Karamoja. The code, the DPIA, the roadmap, and the conformance suite are public. We are ready to donate the platform to the Ministry of Health and would welcome a pilot in two districts of your choosing. Thank you."*

Slide back to the **architecture diagram**. Stay there for Q&A.

---

## Likely questions & one-line answers

| Q | A |
|---|---|
| Is patient data leaving Uganda? | No. The platform runs on-premise or in NITA-U's cloud. |
| What if NIRA's API is down? | Cached NIN lookups served from Redis; new lookups fail with a clear error and never block clinical work. |
| How does it integrate with DHIS2? | Native FHIR + a DHIS2 dataValueSets adapter with replay queue (you saw this in the first minute). |
| Cost to scale to 6,937 facilities? | Two API replicas per 1,000 concurrent users; the bottleneck is Postgres. See `docs/SCALABILITY.md`. |
| Open source licence? | Apache-2.0 — fully permissive for government use and local vendor extension. See `LICENSE`. |
| Time to a real pilot? | 8 weeks: 2 districts, ~30 facilities. We have an implementation plan in `docs/ROADMAP.md`. |
| Who pays for hosting? | NITA-U government cloud OR a 3-year donor-funded shared service. The architecture supports both. |
| What about languages? | English and Luganda today, with the translation harness ready for Runyankole, Luo, Lugbara, and Ateso. |
| Security disclosure process? | Coordinated disclosure at `security@healthsync.ug`, see `SECURITY.md`. |

---

## Backup plans

- If Wi-Fi is unstable → **lean into it**. The offline scenario becomes the whole story.
- If the projector colours look wrong → all charts have explicit colour callouts in the table cells.
- If you have **only 4 minutes** → keep the resilience opening, the citizen view, and the ministry view; cut supply and the language switcher.
- If a command pauses unexpectedly → say *"the platform is fault-tolerant, the demo is not"*, and continue with the next window. Never debug live.

---

## Reset between rehearsals

```bash
make reset && make seed
./scripts/preflight.sh
```
