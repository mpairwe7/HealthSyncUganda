# HealthSync Uganda — documentation index

This directory holds every document an auditor, ministry technical lead, security reviewer, new engineer or pilot partner needs to verify the platform and run it themselves. Documents are versioned alongside the code in this repository — when behaviour changes, the corresponding doc changes in the same pull request.

## 1. For decision-makers

Read these first if you are evaluating HealthSync Uganda.

| Document                                       | What it answers                                                                            |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------ |
| [POSITIONING.md](./POSITIONING.md)             | What is this, who is it for, how is it different from DHIS2 / OpenMRS / vendor systems?    |
| [LOCAL_VALUE.md](./LOCAL_VALUE.md)             | The three impact commitments and the Uganda-specific design choices behind them.           |
| [ROADMAP.md](./ROADMAP.md)                     | Five-year commitment, phased milestones through Dec 2031.                                  |
| [SUSTAINABILITY.md](./SUSTAINABILITY.md)       | Pilot cost (UGX 820M), revenue streams, donation pathway to MoH.                           |
| [TEAM.md](./TEAM.md)                           | Roles, expertise, ministry liaison contacts.                                               |

## 2. For technical reviewers

| Document                                       | What it answers                                                                         |
| ---------------------------------------------- | --------------------------------------------------------------------------------------- |
| [ARCHITECTURE.md](./ARCHITECTURE.md)           | System architecture, C4 levels 1–3, data flows, deployment topology.                    |
| [REQUIREMENTS.md](./REQUIREMENTS.md)           | Functional + non-functional requirements with stable IDs, acceptance criteria, traceability matrix. |
| [API.md](./API.md)                             | REST endpoint reference (FHIR R4 + operational APIs), auth, error model, idempotency.   |
| [DATA_MODEL.md](./DATA_MODEL.md)               | Entity-relationship overview, per-table column inventory, PII/PHI classification, retention.|
| [DESIGN_SYSTEM.md](./DESIGN_SYSTEM.md)         | Visual language, tokens, component contracts, accessibility commitments.                |
| [INTEROPERABILITY.md](./INTEROPERABILITY.md)   | FHIR R4 resources implemented, Uganda NIN profile, DHIS2 / NIRA adapters.               |
| [RESILIENCE.md](./RESILIENCE.md)               | Circuit breaker tuning, bulkhead sizes, offline contract, runbook hooks.                |
| [SCALABILITY.md](./SCALABILITY.md)             | Performance budget, national-scale sizing, cost model, SLOs.                            |
| [OBSERVABILITY.md](./OBSERVABILITY.md)         | SLO contract, `AL-NN` alert catalogue, telemetry contract (logs, traces, metrics).      |
| [THREAT_MODEL.md](./THREAT_MODEL.md)           | STRIDE per asset, trust-boundary diagram, residual-risk register.                       |
| [adr/](./adr/)                                 | Architecture Decision Records — governance (0000), FHIR R4 (0001), breakers (0002), offline-first (0003), supply ledger (0004), facility-scoped reads (0005), district-scope claim (0007), field-level PHI encryption (0009), DB append-only enforcement (0010), DP analytics (0012), shared breaker state (0013). |

## 3. For operators, SREs, and pilot partners

| Document                                       | What it answers                                                                         |
| ---------------------------------------------- | --------------------------------------------------------------------------------------- |
| [BACKEND_SETUP.md](./BACKEND_SETUP.md)         | Bootstrap, configuration, run, test, common errors.                                     |
| [FRONTEND_SETUP.md](./FRONTEND_SETUP.md)       | Bootstrap, dev server, build, PWA + offline verification.                               |
| [DEPLOYMENT.md](./DEPLOYMENT.md)               | Container topology, Docker Compose + Kubernetes targets, NITA-U cloud guidance.         |
| [RUNBOOK.md](./RUNBOOK.md)                     | Day-2 procedures: breakers, queue drain, DB failover, ledger verification, on-call.     |
| [BACKUP_RESTORE.md](./BACKUP_RESTORE.md)       | RPO/RTO per tier, backup taxonomy, restore procedures, quarterly drill plan.            |
| [TESTING.md](./TESTING.md)                     | Test strategy, coverage targets, FHIR conformance, load-test harness.                   |
| [DEMO_SCRIPT.md](./DEMO_SCRIPT.md)             | 6-minute showcase walkthrough, leading with the resilience moment.                      |

## 4. For governance, legal, and audit

| Document                                       | What it answers                                                                          |
| ---------------------------------------------- | ---------------------------------------------------------------------------------------- |
| [DPIA.md](./DPIA.md)                           | Data Protection Impact Assessment against Uganda DPPA 2019.                              |
| [MOH_ALIGNMENT.md](./MOH_ALIGNMENT.md)         | NDHS 2021-2025 traceability and HMIS form mapping.                                       |
| [COMPLIANCE.md](./COMPLIANCE.md)               | DPPA article-by-article controls, ISO/NIST self-assessment, NITA-U cyber requirements.   |
| [SECURITY.md](./SECURITY.md)                   | Security posture: authentication, transport, audit, advisories, pentest cadence, zero-trust elements, incident response link. |
| [INCIDENT_RESPONSE.md](./INCIDENT_RESPONSE.md) | Breach playbook: NIST 800-61r2 phases, PDPO notification, evidence preservation.          |
| [ACCESS_CONTROL.md](./ACCESS_CONTROL.md)       | Consolidated RBAC matrix, role-to-endpoint table, citizen-self rule, audit semantics.    |
| [SHOWCASE_EVALUATION_MAPPING.md](./SHOWCASE_EVALUATION_MAPPING.md) | Criterion-to-evidence map for the MoICT&NG Showcase panel — `EV-CC-NN` IDs. |
| [IMPACT_EVIDENCE.md](./IMPACT_EVIDENCE.md)     | Measurement methodology + measured-result slots for impact commitments, Lighthouse / axe-core, and clinical rehearsals. |

## 5. Repository-root files

Files under the repository root, not this `docs/` folder, that are still part of the audit package:

| File                                           | Purpose                                                          |
| ---------------------------------------------- | ---------------------------------------------------------------- |
| [`../README.md`](../README.md)                 | One-page overview and entry point.                               |
| [`../CHANGELOG.md`](../CHANGELOG.md)           | Keep-a-Changelog history of user-visible changes, releases, and security entries. |
| [`../LICENSE`](../LICENSE)                     | Apache-2.0.                                                      |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md)     | Branching, commit style, definition of done.                     |
| [`../CODE_OF_CONDUCT.md`](../CODE_OF_CONDUCT.md) | Contributor Covenant 2.1 with health-data additions.           |
| [`../SECURITY.md`](../SECURITY.md)             | Coordinated disclosure policy (PGP key + DPPA notification).     |
| [`../.env.example`](../.env.example)           | Every required environment variable, documented.                 |
| [`../docker-compose.yml`](../docker-compose.yml) | Local + showcase stack composition.                            |
| [`../Makefile`](../Makefile)                   | One-line orchestrations (`make help` lists them).                |

## 6. Document conventions

- **Single-source-of-truth.** If a fact appears in two documents, exactly one is canonical. The other links to it.
- **Stable identifiers.** Requirements (`FR-001`), ADRs (`ADR 0003`), runbook procedures (`RB-12`), incident-response steps (`IR-13`), alerts (`AL-05`), SLOs (`SLO-2`), threats and residual risks (`T-NNN`, `RR-09`), Showcase evidence rows (`EV-CC-NN`), impact-evidence items (`IE-NN`), FHIR R5 migration steps (`IO-R5-NN`), OpenHIE alignment items (`IO-OHIE-NN`), IHE profile items (`IO-IHE-NN`), forward-architecture items (`FA-NN`) carry IDs that survive renames so cross-references do not rot.
- **Audit timestamps.** Documents that record point-in-time decisions carry a `Last reviewed:` line near the top.
- **No "wild" links.** Cross-references stay inside this repository or go to public, durable sources (RFCs, ISO catalogues, gov.ug). We do not link to private wikis or expiring URLs.

## 7. Where to start by role

- **Cabinet / Ministry decision-maker** → POSITIONING → LOCAL_VALUE → ROADMAP → SUSTAINABILITY.
- **NITA-U / MoH technical lead** → ARCHITECTURE → REQUIREMENTS → DATA_MODEL → DEPLOYMENT → RUNBOOK → OBSERVABILITY.
- **Showcase panel reviewer** → SHOWCASE_EVALUATION_MAPPING → IMPACT_EVIDENCE → TEAM → COMPLIANCE → INCIDENT_RESPONSE.
- **Security / privacy auditor** → DPIA → COMPLIANCE → SECURITY → THREAT_MODEL → ACCESS_CONTROL → INCIDENT_RESPONSE → RUNBOOK.
- **Code / architecture auditor** → ARCHITECTURE → DATA_MODEL → API → REQUIREMENTS → adr/ → CHANGELOG (root).
- **Onboarding engineer** → README (root) → BACKEND_SETUP → FRONTEND_SETUP → DATA_MODEL → TESTING → adr/.
- **SRE / on-call** → RUNBOOK → OBSERVABILITY → BACKUP_RESTORE → INCIDENT_RESPONSE.
- **Pilot facility ICT focal point** → DEPLOYMENT → RUNBOOK → DEMO_SCRIPT.
