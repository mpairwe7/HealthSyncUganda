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
| [DESIGN_SYSTEM.md](./DESIGN_SYSTEM.md)         | Visual language, tokens, component contracts, accessibility commitments.                |
| [INTEROPERABILITY.md](./INTEROPERABILITY.md)   | FHIR R4 resources implemented, Uganda NIN profile, DHIS2 / NIRA adapters.               |
| [RESILIENCE.md](./RESILIENCE.md)               | Circuit breaker tuning, bulkhead sizes, offline contract, runbook hooks.                |
| [SCALABILITY.md](./SCALABILITY.md)             | Performance budget, national-scale sizing, cost model, SLOs.                            |
| [adr/](./adr/)                                 | Architecture Decision Records (FHIR R4, breakers, offline-first, supply ledger).        |

## 3. For operators, SREs, and pilot partners

| Document                                       | What it answers                                                                         |
| ---------------------------------------------- | --------------------------------------------------------------------------------------- |
| [BACKEND_SETUP.md](./BACKEND_SETUP.md)         | Bootstrap, configuration, run, test, common errors.                                     |
| [FRONTEND_SETUP.md](./FRONTEND_SETUP.md)       | Bootstrap, dev server, build, PWA + offline verification.                               |
| [DEPLOYMENT.md](./DEPLOYMENT.md)               | Container topology, Docker Compose + Kubernetes targets, NITA-U cloud guidance.         |
| [RUNBOOK.md](./RUNBOOK.md)                     | Day-2 procedures: breakers, queue drain, DB failover, ledger verification, on-call.     |
| [TESTING.md](./TESTING.md)                     | Test strategy, coverage targets, FHIR conformance, load-test harness.                   |
| [DEMO_SCRIPT.md](./DEMO_SCRIPT.md)             | 6-minute showcase walkthrough, leading with the resilience moment.                      |

## 4. For governance, legal, and audit

| Document                                       | What it answers                                                                          |
| ---------------------------------------------- | ---------------------------------------------------------------------------------------- |
| [DPIA.md](./DPIA.md)                           | Data Protection Impact Assessment against Uganda DPPA 2019.                              |
| [MOH_ALIGNMENT.md](./MOH_ALIGNMENT.md)         | NDHS 2021-2025 traceability and HMIS form mapping.                                       |
| [COMPLIANCE.md](./COMPLIANCE.md)               | DPPA article-by-article controls, ISO/NIST self-assessment, NITA-U cyber requirements.   |
| [SECURITY.md](./SECURITY.md)                   | Threat model, authentication, transport, audit.                                          |

## 5. Repository-root files

Files under the repository root, not this `docs/` folder, that are still part of the audit package:

| File                                           | Purpose                                                          |
| ---------------------------------------------- | ---------------------------------------------------------------- |
| [`../README.md`](../README.md)                 | One-page overview and entry point.                               |
| [`../LICENSE`](../LICENSE)                     | Apache-2.0.                                                      |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md)     | Branching, commit style, definition of done.                     |
| [`../CODE_OF_CONDUCT.md`](../CODE_OF_CONDUCT.md) | Contributor Covenant 2.1 with health-data additions.           |
| [`../SECURITY.md`](../SECURITY.md)             | Coordinated disclosure policy (PGP key + DPPA notification).     |
| [`../.env.example`](../.env.example)           | Every required environment variable, documented.                 |
| [`../docker-compose.yml`](../docker-compose.yml) | Local + showcase stack composition.                            |
| [`../Makefile`](../Makefile)                   | One-line orchestrations (`make help` lists them).                |

## 6. Document conventions

- **Single-source-of-truth.** If a fact appears in two documents, exactly one is canonical. The other links to it.
- **Stable identifiers.** Requirements (`FR-001`), ADRs (`ADR 0003`), and runbook procedures (`RB-12`) carry IDs that survive renames so cross-references do not rot.
- **Audit timestamps.** Documents that record point-in-time decisions carry a `Last reviewed:` line near the top.
- **No "wild" links.** Cross-references stay inside this repository or go to public, durable sources (RFCs, ISO catalogues, gov.ug). We do not link to private wikis or expiring URLs.

## 7. Where to start by role

- **Cabinet / Ministry decision-maker** → POSITIONING → LOCAL_VALUE → ROADMAP → SUSTAINABILITY.
- **NITA-U / MoH technical lead** → ARCHITECTURE → REQUIREMENTS → DEPLOYMENT → RUNBOOK.
- **Security / privacy auditor** → DPIA → COMPLIANCE → SECURITY → RUNBOOK.
- **Onboarding engineer** → README (root) → BACKEND_SETUP → FRONTEND_SETUP → TESTING → adr/.
- **Pilot facility ICT focal point** → DEPLOYMENT → RUNBOOK → DEMO_SCRIPT.
