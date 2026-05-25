# Changelog

All notable changes to **HealthSync Uganda** are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This file is the canonical, audit-facing history of user-visible changes. It is *not* a substitute for `git log`; it is the curated narrative an auditor reads to understand what shipped and when.

**Conventions:**
- Every PR with a user-visible change adds an entry under `## [Unreleased]`. Release tags promote the section to a dated version heading.
- Sections within a release follow Keep-a-Changelog: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`.
- Security-related changes also reference the row in [docs/SECURITY.md "Known advisories and waivers"](./docs/SECURITY.md) — that table is the canonical advisory log; this file only links to it.
- Documentation-only changes are recorded under a `Docs` subsection per release.
- Dates use ISO-8601 (`YYYY-MM-DD`) in `Africa/Kampala` (UTC+03:00).

---

## [Unreleased]

### Changed (CI/CD)
- `build-push.yml` and `deploy-cranecloud.yml` now use **Docker Hub** (`docker.io/mpairwe7/...`) instead of GHCR. Crane Cloud's RENU and AHUMAIN ML clusters cannot pull from `ghcr.io` (confirmed 2026-05-26 via control-deploy); Docker Hub pulls work cleanly. Requires repo variable `DOCKERHUB_USER` + repo secret `DOCKERHUB_TOKEN`.

### Known follow-ups (pre-pilot)

- **Wire up Alembic migrations.** `alembic>=1.13.0` is in `backend/pyproject.toml` and `uv.lock` but `alembic.ini` / `env.py` / migration revisions do not exist yet. Until then the backend uses `Base.metadata.create_all` on startup (`auto_create_schema=true` in `Settings`) — idempotent for adding new tables but does not handle ALTERs. This is acceptable for the pilot's initial fresh-DB deploy but must be replaced with real migrations before production schema evolution.

### Added (CI/CD)
- `.github/workflows/build-push.yml` — multi-image GHCR build & push on `main` / `v*` tag / `workflow_dispatch`, with auto-dispatch to staging (on `main`) and pilot (on `v*`).
- `.github/workflows/deploy-cranecloud.yml` — operator-led Crane Cloud rollout via the `cranecloud` CLI; keyring disabled with `PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring`; environment-scoped secrets; loud fallback to `make update-*` when the CLI cannot authenticate.
- `.github/workflows/ci.yml` — new `docker-build` matrix job that verifies both Dockerfiles still build on every PR (no push).
- `infra/cranecloud/README.md` §9 — full CI/CD documentation: triggers, secrets, environment-gated deploys, typical flow.

### Added
- New audit-grade documentation set:
  - `docs/INCIDENT_RESPONSE.md` — breach playbook (DPPA s.19, NIST SP 800-61r2 phases, PDPO notification template).
  - `docs/DATA_MODEL.md` — ER overview + per-table inventory derived from `backend/app/db/models/`.
  - `docs/ACCESS_CONTROL.md` — consolidated RBAC matrix; role-to-endpoint table; citizen-self rule.
  - `docs/THREAT_MODEL.md` — STRIDE-per-asset, trust boundaries, residual-risk register, Roadmap Closure Plan (§7).
  - `docs/OBSERVABILITY.md` — SLO contract, `AL-NN` alert catalogue, telemetry contract.
  - `docs/BACKUP_RESTORE.md` — RPO/RTO per tier, backup taxonomy, drill plan.
  - `CHANGELOG.md` — this file.
- Showcase-readiness documentation:
  - `docs/SHOWCASE_EVALUATION_MAPPING.md` — criterion-to-evidence map (`EV-CC-NN` IDs) for the MoICT&NG Showcase panel.
  - `docs/IMPACT_EVIDENCE.md` — measurement methodology for impact commitments, Lighthouse / axe-core targets, and clinical rehearsal protocol.
  - `docs/adr/0000-governance.md` — open-source governance model (consensus-seeking maintainer tiers + DPO veto on privacy invariants).
- Architecture Decision Records (Proposed, awaiting ADR-0000 review window):
  - `docs/adr/0005-facility-scoped-patient-reads.md` — closes RR-02. Adds treatment-relationship / consent / role-elevation / emergency-override basis for `GET /patients/{id}`.
  - `docs/adr/0007-district-scope-claim.md` — closes RR-09. Adds `assigned_districts` JWT claim and analytics-endpoint filtering.
  - `docs/adr/0009-field-level-phi-encryption.md` — AES-GCM envelope encryption for HIV / mental-health / GBV observations; KMS-managed KEK; per-row DEK.
  - `docs/adr/0010-db-append-only-enforcement.md` — closes RR-01 / RR-03 / RR-05. Postgres triggers + least-privilege role for `audit_log` and `stock_events`; chain-verify in Alembic migrations.
  - `docs/adr/0012-differential-privacy-analytics.md` — implements FA-06…FA-09. k-anonymity + Laplace noise + per-actor ε budget on `/api/v1/analytics/*`.
  - `docs/adr/0013-shared-circuit-breaker-state.md` — Redis-coordinated breaker probe + bulkhead cap on top of per-process breakers (closes herd effect at national scale).
  - `MAINTAINERS.md` (root) — machine-checkable maintainer roster (template with `[Role to populate]` placeholders; no fabricated names).
  - `docs/TEAM.md` — fully restructured with governance summary, contribution model, capacity-building commitments, and named placeholders for individuals.

### Changed
- `docs/THREAT_MODEL.md` added §7 Roadmap Closure Plan — per-RR owner, target date, evidence-of-closure for `RR-01` through `RR-12`.
- `docs/SECURITY.md` added §"Penetration testing & vulnerability management" (continuous + scheduled cadence, triage SLA) and §"Zero-trust elements" (principle-by-principle status).
- `docs/INTEROPERABILITY.md` added FHIR R5 migration path (`IO-R5-NN`), OpenHIE component-by-component alignment (`IO-OHIE-NN`), IHE profile mapping (`IO-IHE-NN`), and a forward-looking trends section.
- `docs/ARCHITECTURE.md` added §12 "Forward-looking architecture (2026+)" — zero-trust roadmap (`FA-01`…`FA-05`), differential-privacy plan for analytics (`FA-06`…`FA-09`), AI governance readiness (`FA-10`…`FA-14`).
- `docs/SCALABILITY.md` added §6 "Load-test methodology & reproducibility" — reproduction recipe, expected outputs, national-scale projection rules, and reproducibility caveats. Renumbered original §6 to §7.
- `docs/RUNBOOK.md` RB-13 now links to `INCIDENT_RESPONSE.md` (was an unsatisfied reference to a non-existent SECURITY.md section).
- `docs/SECURITY.md` gained an "Incident response" section that points to the new playbook; the PyJWT CVE-2025-45768 advisory row now documents the follow-up cadence.
- `docs/COMPLIANCE.md` rows for DPPA s.19 and NITA-U CERT-UG reporting now link to the live `INCIDENT_RESPONSE.md` (were marked "post-pilot").
- `docs/FRONTEND_SETUP.md` Bun version requirement corrected to `>= 1.1.0` to match `frontend/package.json` (`engines.bun >= 1.1.0`).
- `docs/README.md` index updated to list every new audit + showcase document, extended role-based start paths (added "Showcase panel reviewer" path), and extended the stable-identifier convention list.
- Root `README.md` updated to reflect Next.js 16.2.6 (was 16.2.3 — see `[0.1.0-pre-pilot.2]` Security entry).

---

## [0.1.0-pre-pilot.2] — 2026-05-21

### Added
- Production-readiness sweep: lint configuration, test wiring, CI for backend (ruff + mypy + pytest) and frontend (typecheck + ESLint + Next build), OSV-Scanner on `uv.lock` and `bun.lock`, Dependabot for `uv`, `npm`, GitHub Actions, and Docker (commit `7add819`).

### Security
- Patched 14 Dependabot findings on `next` and `postcss` — Next.js bumped from 16.2.3 to ^16.2.6, `postcss` resolved to 8.5.x via `overrides` (commit `af68bdd`). See [docs/SECURITY.md "Known advisories and waivers"](./docs/SECURITY.md) rows dated 2026-05-20 (GHSA-267c-6grr-h53f, GHSA-qx2v-qp2m-jg93).

---

## [0.1.0-pre-pilot.1] — 2026-05-20

### Added
- Audit-ready documentation dossier — setup guides, API reference, operations runbook, requirements traceability (commit `4275bde`).
- HealthSync design tokens applied across the UI (commit `d127862`).
- Design-system documentation aligned to Uganda government digital-identity tokens (commit `3af6e46`).
- Demo-script narrative leading with the resilience moment (commit `a175a9a`).
- Open-source community health files: `LICENSE` (Apache-2.0), `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `SECURITY.md`, issue and PR templates (commit `4666fea`).
- Four foundational ADRs in `docs/adr/` — FHIR R4 clinical data model, resilience circuit breakers, offline-first frontend, supply hash-chain ledger (commit `de67f8f`).
- Governance, compliance, and capability dossier — DPIA, COMPLIANCE, MOH_ALIGNMENT, ROADMAP, SUSTAINABILITY, TEAM, LOCAL_VALUE (commit `7c380e7`).
- Architecture, interoperability, resilience, and positioning documents (commit `b5900ed`).
- Operational and conformance script harness — preflight, demo reset, dev stack, FHIR conformance, load tests (commit `3ae0e53`).
- Postgres initialisation + OpenTelemetry collector configuration (commit `f675b55`).
- Next.js offline-first PWA with i18n (English + Luganda), Tailwind tokens, Zustand stores, TanStack Query with IndexedDB persistence, idempotency-keyed mutation queue (commit `3956b90`).
- FastAPI backend service with FHIR R4 (`fhir.resources` 8), async SQLAlchemy 2, JWT auth, RBAC (`citizen < worker < pharmacist < district_admin < ministry_admin`), audit log, consent records, supply hash-chain ledger, NIRA / DHIS2 adapter clients with circuit breakers + bulkheads, structured logging with OpenTelemetry trace correlation (commit `8ee23d5`).
- Initial project scaffolding — Makefile, docker-compose, .env.example, repository skeleton (commit `4494505`).

---

## Versioning notes

Pre-pilot iterations are tagged `0.1.0-pre-pilot.N` rather than `0.1.0` because the platform has not yet been formally accepted by MoH. The first acceptance milestone — successful completion of the showcase on **25 June 2026** and the DPIA / penetration-test reviews listed in [docs/COMPLIANCE.md §E](./docs/COMPLIANCE.md#e-independent-verifications-scheduled-before-pilot) — will promote the platform to `0.1.0`. The Roadmap milestones documented in [docs/ROADMAP.md](./docs/ROADMAP.md) drive subsequent minor and major versions.

A change that breaks an external contract — FHIR wire format, REST endpoint shape, JWT claim semantics, audit-log field set — requires a major-version bump and an [ADR](./docs/adr/) documenting the decision.

A change that adds a column to a PII-bearing table requires an entry under `Security` linking to [docs/DATA_MODEL.md](./docs/DATA_MODEL.md) and (if classification changes) [docs/COMPLIANCE.md](./docs/COMPLIANCE.md).

---

## Cross-references

- [docs/SECURITY.md](./docs/SECURITY.md) — canonical advisories table; this file links to it rather than duplicating.
- [docs/ROADMAP.md](./docs/ROADMAP.md) — what is coming.
- [docs/adr/](./docs/adr/) — architecture decisions binding on contributors.
- [docs/REQUIREMENTS.md](./docs/REQUIREMENTS.md) — stable FR-IDs cross-referenced from individual changes when applicable.
- [docs/INCIDENT_RESPONSE.md](./docs/INCIDENT_RESPONSE.md) — incident timelines live in `docs/incidents/` and are referenced from a `Security` entry here.
