# Team & Governance

**Audience:** Showcase panel (scores *Innovator Capability*); MoH / NITA-U partnership leads; potential contributors.
**Status:** template for individual rows — placeholders use `[Role to populate]` rather than fabricated names. The rest (governance model, capacity-building commitments, decision processes) is canonical and ready to merge.
**Last reviewed:** 2026-05-25.

This document carries the panel's *Innovator Capability* evidence. Sections §1–§2 list the named roster and prior shipped work; §3–§5 are the governance, contribution, and capacity-building commitments that survive any individual's departure.

The accompanying repository-root [`MAINTAINERS.md`](../MAINTAINERS.md) is the **machine-checkable** maintainer list (GitHub handles + merge rights). This document is the **narrative** version with bios and rationale.

---

## 1. People

### 1.1 Core engineering

> The Showcase panel scores *Innovator Capability* directly from this section. **The project lead populates each row with a real name, a one-sentence bio, the GitHub handle (verifiable against the commit history), and at least one external link (LinkedIn, prior project URL, conference talk).** Empty cells must remain `[…to populate]` — never fabricated.

| Role                                | Name                          | Bio (1–2 sentences)                                                                                  | GitHub                         | Other                                |
| ----------------------------------- | ----------------------------- | ---------------------------------------------------------------------------------------------------- | ------------------------------ | ------------------------------------ |
| Project Lead & Backend Architect    | [Lead to populate]            | [Brief: years of Python/FastAPI experience; domain context — e.g. healthcare, fintech; prior outputs] | `[handle]`                     | LinkedIn: `[url]`; talks: `[url]`    |
| Frontend Engineer                    | [Frontend to populate]        | [Brief: Next.js / PWA / accessibility focus; relevant prior projects]                                 | `[handle]`                     | LinkedIn: `[url]`                    |
| Data Engineer                        | [Data engineer to populate]   | [Brief: Postgres / FHIR / DHIS2 experience]                                                          | `[handle]`                     | LinkedIn: `[url]`                    |
| DevOps / SRE                         | [SRE to populate]             | [Brief: Kubernetes, observability, healthcare workloads]                                              | `[handle]`                     | LinkedIn: `[url]`                    |
| QA / Conformance Engineer            | [QA to populate]              | [Brief: test automation, FHIR conformance, load testing]                                              | `[handle]`                     | LinkedIn: `[url]`                    |

### 1.2 Ugandan-national share

The *Local Innovation Value* dimension expects ≥ **70 % Ugandan-national** core team. The actual figure is reported below at submission time; the commitment is durable.

| Total core contributors | Ugandan nationals | Share | Source                                                          |
| ----------------------- | ----------------- | ----- | --------------------------------------------------------------- |
| [N]                     | [M]               | [M/N] | Project lead self-reports; cross-checked against GitHub history. |

### 1.3 Pipeline (interns and graduate hires)

Capacity-building is itself an evaluation signal. We commit (see §5) to a rolling intern programme; current cohort:

| Cohort           | Source                                | Status                                  |
| ---------------- | ------------------------------------- | --------------------------------------- |
| [2026 Cohort 1]  | [Makerere COCIS / MUST / MUBS]        | [Onboarding / Active / Concluded]       |

### 1.4 Advisors and reviewers

Advisors do not write production code. They review, validate, and bring outside expertise. Advisors with relevant artefacts are named in the Documents column.

| Domain                              | Name                         | Affiliation                  | Reviews                                                              |
| ----------------------------------- | ---------------------------- | ---------------------------- | -------------------------------------------------------------------- |
| Clinical (general practice)          | [Advisor to populate]        | [Affiliation]                | User flows; clinical safety; DEMO_SCRIPT.md                          |
| Public Health (epidemiology)         | [Advisor to populate]        | [Affiliation]                | Analytics indicators vs. HMIS forms; [MOH_ALIGNMENT.md](./MOH_ALIGNMENT.md) |
| Cybersecurity (independent)          | [Advisor to populate]        | [Affiliation]                | [SECURITY.md](./SECURITY.md); [THREAT_MODEL.md](./THREAT_MODEL.md); pentest scope |
| Data Protection / Legal              | [Advisor to populate]        | [Affiliation]                | [DPIA.md](./DPIA.md); consent flows; PDPO notification                |
| Health-systems policy                | [Advisor to populate]        | [Affiliation]                | MoH leadership bridge; [MOH_ALIGNMENT.md](./MOH_ALIGNMENT.md)         |
| Open-source community                | [Advisor to populate]        | [Affiliation]                | Open-source governance; [ADR 0000](./adr/0000-governance.md)         |

## 2. Recent shipped work (portfolio)

> 2–5 prior projects per core team member, with links. Populated by each engineer for themselves.

- **Project Lead** — [link + one-line summary]
- **Frontend** — [link + one-line summary]
- **Data engineer** — [link + one-line summary]
- **SRE** — [link + one-line summary]
- **QA** — [link + one-line summary]

---

## 3. Governance

> Canonical governance model: [ADR 0000 — Open-source governance model](./adr/0000-governance.md). This section is the operational summary.

### 3.1 Maintainer tiers

| Tier         | Authority                                                  | Lives in                                            |
| ------------ | ---------------------------------------------------------- | --------------------------------------------------- |
| Contributor  | Open PRs; comment on issues                                | Anyone                                              |
| Reviewer     | Approve PRs in declared area                               | Promoted per ADR 0000                                |
| Maintainer   | Merge PRs; cut releases; binding ADR votes                  | Listed in [MAINTAINERS.md](../MAINTAINERS.md)        |

### 3.2 Decision-making

- **Routine PRs:** two reviewer approvals + green CI → maintainer merges.
- **Architectural decisions:** ADR PR, 10 working days open window, two maintainer approvals.
- **Privacy-relevant decisions:** DPO has a veto on changes to the audit log, consent model, role hierarchy, or PII inventory. See ADR 0000 §"Decision-making" item 4.
- **Escalation:** Architecture Review Board → two-thirds maintainer vote.

### 3.3 Standing review cadences

| Body                                 | Composition                                                            | Cadence    | Output                                                                                          |
| ------------------------------------ | ---------------------------------------------------------------------- | ---------- | ----------------------------------------------------------------------------------------------- |
| Architecture Review Board (ARB)      | 2 maintainers + 1 external technical advisor + 1 clinical advisor       | Monthly    | Minutes in `docs/governance/arb-YYYY-MM.md`; ADRs accepted or returned                            |
| Security & Privacy Review            | 1 maintainer + DPO + cybersecurity advisor                              | Quarterly  | Updates to [THREAT_MODEL.md §6](./THREAT_MODEL.md#6-residual-risk-register); [SECURITY.md](./SECURITY.md); [DPIA.md](./DPIA.md) |
| Roadmap Closure heartbeat            | Maintainer group                                                       | Monthly    | Row-by-row status against [THREAT_MODEL.md §7](./THREAT_MODEL.md#7-roadmap-closure-plan)         |
| Tabletop exercise                    | DPO + IC + on-call rota                                                | Twice a year | Report under `docs/incidents/tabletop-…` per [INCIDENT_RESPONSE.md §7](./INCIDENT_RESPONSE.md#7-tabletop-exercises) |
| Restore drill                         | SRE                                                                    | Quarterly  | Report under `docs/incidents/restore-drill-…` per [BACKUP_RESTORE.md §6](./BACKUP_RESTORE.md#6-quarterly-restore-drill) |

### 3.4 Conflict of interest

A maintainer who has a direct material interest in a decision **must abstain** and disclose. See ADR 0000 §"Conflict-of-interest rule".

### 3.5 Code of conduct

The project uses the [Contributor Covenant 2.1](../CODE_OF_CONDUCT.md) with additions for health-data contexts (no posting of unredacted clinical data in issues / PRs, even when anonymised by the poster). Enforcement is the responsibility of the maintainer group with appeals to the ARB.

---

## 4. Contribution model

### 4.1 How to contribute

The mechanics are in [CONTRIBUTING.md](../CONTRIBUTING.md). Summary:

1. Fork; branch from `main`.
2. Open a PR with a description that follows the PR template.
3. Run `make lint && make test` locally first.
4. CI must be green before review.
5. Two reviewer approvals + one maintainer merge.

### 4.2 Definition of done

A PR is "done" when:

- All CI jobs are green.
- Tests cover the change (new feature → new tests; bug fix → regression test).
- Docs updated in the same PR if behaviour changes (single-source-of-truth: code and docs ship together).
- For PII-touching changes: an entry in [DATA_MODEL.md](./DATA_MODEL.md) (if a column changes), [ACCESS_CONTROL.md](./ACCESS_CONTROL.md) (if a role gate changes), or [SECURITY.md](./SECURITY.md) (if posture changes).

### 4.3 Release cadence

- **Patch:** as needed, including security backports.
- **Minor:** ~ every 4–6 weeks, batching feature work.
- **Major:** when a wire-format or governance change is accepted via ADR.

Each release adds a heading to [CHANGELOG.md](../CHANGELOG.md). Security advisories link to the canonical [SECURITY.md "Known advisories"](./SECURITY.md) table.

---

## 5. Capacity building

The MoH adopts the platform after donation. Sustainability requires Ugandan capacity to outlive the original core team. The following commitments are durable and externally visible.

### 5.1 Open practice

| Activity                                          | Cadence            | Outcome                                                                                       |
| ------------------------------------------------- | ------------------ | --------------------------------------------------------------------------------------------- |
| Engineering office hours (open to any Ugandan engineer) | Monthly             | Recorded session; agenda public; questions answered                                            |
| MoH / NITA-U technical onboarding                  | Quarterly (half-day) | Walkthrough of the latest architecture + runbook updates                                       |
| Open hackathon                                     | Annual             | New MoH modules built on HealthSync; merged contributions land in next minor release           |
| Public dashboard                                   | Continuous         | GitHub repository is the source of truth; Insights tab is open                                  |

### 5.2 Pipeline

| Programme                          | Source                                | Commitment                                                                                                                |
| ---------------------------------- | ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| Internship cohort                  | Makerere COCIS, MUST, MUBS            | Rolling 4-person cohort, 6-month rotations; mentored by a maintainer; targeted promotion to Reviewer for the strongest interns |
| Graduate hire pipeline             | Makerere COCIS, MUST, Refactory.dev   | First-look for open Maintainer-track roles                                                                                  |
| Cross-training                     | NITA-U DevOps team                    | Joint sessions on observability and runbook procedures, twice a year                                                       |
| Documentation translation           | Citizen-facing language coverage      | Luganda shipped; Lusoga, Runyankole, Luo, Acholi scaffolded; community-translated contributions accepted                  |

### 5.3 Knowledge transfer to MoH

| Artefact                                         | Where                                                                                                            |
| ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------- |
| Runbook with stable IDs                           | [RUNBOOK.md](./RUNBOOK.md) (RB-01 … RB-13)                                                                       |
| Incident playbook                                 | [INCIDENT_RESPONSE.md](./INCIDENT_RESPONSE.md) (IR-01 … IR-31)                                                   |
| Architecture decisions                            | [docs/adr/](./adr/)                                                                                              |
| Data model + PII inventory                        | [DATA_MODEL.md](./DATA_MODEL.md)                                                                                 |
| Access-control matrix                             | [ACCESS_CONTROL.md](./ACCESS_CONTROL.md)                                                                          |
| Backup/restore procedure                          | [BACKUP_RESTORE.md](./BACKUP_RESTORE.md)                                                                          |
| Observability contract (SLOs, alerts)             | [OBSERVABILITY.md](./OBSERVABILITY.md)                                                                            |
| Showcase evaluation mapping                       | [SHOWCASE_EVALUATION_MAPPING.md](./SHOWCASE_EVALUATION_MAPPING.md)                                                |
| Impact-measurement methodology                    | [IMPACT_EVIDENCE.md](./IMPACT_EVIDENCE.md)                                                                        |

All of the above use stable IDs so cross-references survive renames.

---

## 6. Contact for the showcase panel

> Populated before submission. Each row points to a real, reachable person — these are the people the panel calls if a clarification is needed during scoring.

| Purpose                                | Person                        | Channel                          | Office hours (EAT)   |
| -------------------------------------- | ----------------------------- | -------------------------------- | -------------------- |
| Project lead enquiries                  | [Project lead to populate]    | `[email]` · `[phone]`            | [Hours]              |
| Technical demo / on-site Q&A            | [Tech lead to populate]       | `[email]` · `[phone]`            | [Hours]              |
| Press / media                           | [Comms to populate]           | `[email]`                        | [Hours]              |
| Security disclosures                    | See [SECURITY.md](../SECURITY.md) | PGP-encrypted email             | Continuous           |
| Privacy / DPO escalation                 | [DPO to populate]             | `[email + PGP fingerprint]`      | [Hours]              |

---

## 7. Cross-references

- [adr/0000-governance.md](./adr/0000-governance.md) — canonical governance model.
- [MAINTAINERS.md](../MAINTAINERS.md) — machine-checkable maintainer list.
- [CONTRIBUTING.md](../CONTRIBUTING.md) — PR workflow.
- [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) — community baseline.
- [SECURITY.md](./SECURITY.md), [INCIDENT_RESPONSE.md](./INCIDENT_RESPONSE.md) — security and incident posture this team operates.
- [SHOWCASE_EVALUATION_MAPPING.md §IC](./SHOWCASE_EVALUATION_MAPPING.md#ic--innovator-capability) — how this team's evidence rolls up into *Innovator Capability* scoring.
