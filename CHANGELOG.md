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

### Added (IM — Immunisation schedule + family graph, commit 8adb5eb..7a80d0b)
- `backend/app/clinical/unepi_schedule.py` (new) — Uganda UNEPI 2024 routine schedule encoded as a Python module: BCG, OPV0-3, DPT1-3 (pentavalent), PCV1-3, MR1-2, Yellow Fever — each row carries SNOMED CT code, min/max age window, minimum interval from previous dose. `compute_immunisation_status(birth_date, observations)` and `is_duplicate_dose(...)` are pure functions, unit-testable without a DB.
- `backend/app/db/models/caregiver.py` (new) — `CaregiverLink` ORM model `(caregiver_id, child_id, relationship)` with unique-pair constraint and indices in both directions. Alembic migration `c07e02b0024b_caregiver_links_table.py` creates the table with `ON DELETE CASCADE` FKs.
- **5 new backend endpoints**:
  - `GET  /api/v1/patients/{id}/immunisation-status` — per-antigen view (complete / due / due-soon / overdue / not-yet) with `next_due_date` + `overdue_days`.
  - `GET  /api/v1/patients/{id}/family[?direction=children|caregivers|auto]` — caregiver↔child graph view.
  - `POST /api/v1/patients/{id}/caregivers` — worker links a caregiver (by NIN) to a child; idempotent + updates relationship label.
  - `DELETE /api/v1/patients/{id}/caregivers/{link_id}` — unlink.
  - `GET  /api/v1/me/family` — citizen self-serve list of own children with overdue counts.
- **Permission helper `_citizen_can_read(principal, patient, db)`** in `app/api/v1/patients.py` replaces three copies of inline NIN-only checks. Now a citizen who is a registered caregiver can read their child's full record (`GET /patients/{id}` + `GET /patients/{id}/immunisation-status`) — closing the most-asked gap from the workflow review.
- `/worker/immunisations` rebuilt as a **3-step workflow**: find patient → see schedule status (overdue rows highlighted) → administer. The vaccine dropdown flags blocked options (series complete OR not yet due); a separate "Override" checkbox + reason field lets clinicians override for documented cases (catch-up campaigns, MoH advisories). Override reasons land in both the encounter and the audit log.
- `/citizen/family` (new) — list of children with overdue counts; `/citizen/family/[id]` (new) — per-child immunisation table reachable from the family list.
- `/worker/patients/[id]` gains a **Family** tab with caregiver link/unlink workflow + NIN search.
- New TS types + hooks: `useImmunisationStatus`, `useFamily`, `useMyFamily`, `useLinkCaregiver`, `useUnlinkCaregiver`.
- `_seed_caregivers()` seeds 4 plausible links so demos render meaningful data: Wakiso mother (`CF93081244778K`) → 2 children, Gulu mother → Jinja toddler, Lira guardian → Kampala child.
- **Playwright section K** (10 tests): immunisation-status shape, family lists, `/me/family`, caregiver-aware READ via `/patients/{id}`, non-caregiver blocked (403), link idempotency + relationship update, self-link rejected (422), unknown caregiver NIN (404), citizen JWT can't POST link (403), browser walk of `/citizen/family`.

### Added (WD — Worker dashboard pilot-tier, commit 82d4908)
- **5 new backend endpoints** (no migrations — all over existing tables):
  - `GET  /api/v1/me/staff` — staff profile + facility context (mirror of `/me` for non-citizen tokens).
  - `POST /api/v1/encounters/{id}/observations` — append late-arriving observations (lab results, follow-up vitals) to an existing encounter.
  - `PATCH /api/v1/patients/{id}/deceased` — reversible vital-status flag (audited under `mark-deceased` / `clear-deceased`).
  - `GET  /api/v1/supply/transfers?facility_id&since_days` — transfer history.
  - `GET  /api/v1/analytics/encounters-by-facility?facility_id&since_days` — per-facility analytics (auto-scopes to caller's facility for `worker`/`pharmacist`; admin can pass any).
- **Audit gap closure**: `POST /supply/dispense` now records access via `record_access()` and accepts `patient_id` + `purpose` query params (DPPA §12 + ISO 27001 A.12.4.1). The audit row carries `actor_role=pharmacist`, `action=dispense`, and the dispensing target's `resource_id`.
- 3 new worker pages: `/worker/supply/receive` (record an inbound batch), `/worker/supply/transfers` (history with facility/window filters), `/worker/profile` (identity + session timer + sign-out).
- `/worker/immunisations` shipped (later rebuilt under IM above) — replaces the previous `<ScopeNote>` stub with a real mass-vaccination workflow.
- `/worker/patients/[id]` encounter form now captures the full LOINC vitals set (temperature, BP, weight, height, pulse, oxygen saturation, respiratory rate) with min/max guards. New **Add observation** tab + **Admin** (mark-deceased) tab with inline confirm.
- `/worker` home gains a "This facility" card (today + 30-day encounter counts) and a "My profile" tile.
- Worker `/error.tsx` boundary, `<OfflineBanner />` component shared across all worker + admin + citizen pages, `useAuthHydrated()` applied to every session-gated worker page (closes the Zustand-persist redirect flash on browser reload).
- `_seed_transfers()` adds ~6 historical `StockTransfer` rows so the transfers list renders on first login.
- **Playwright section I** (14 tests): all new endpoints, role enforcement, the dispense-audit fix, citizen-token-against-staff-endpoint rejection, browser walks of every new worker page.

### Added (CP — Citizen portal /me/* surface, commit b7915fd)
- **6 new backend endpoints** under `/api/v1/me`:
  - `GET  /me` — own Patient (NIN-bridge primitive every other `/me/*` page uses).
  - `GET  /me/encounters` — own history, newest-first.
  - `GET  /me/immunisations` — SNOMED-coded vaccines only.
  - `GET  /me/audit?since_days=N` — own access log (1-365 day window).
  - `POST /me/consent/grant` — citizen self-grant consent.
  - `PATCH /me/profile` — update phone / email / sub_county / parish / village.
- **Safety fix**: `POST /api/v1/consents/{id}/revoke` previously had no patient-scoping check; any citizen JWT could revoke any consent by ID guess. Now mirrors the NIN-bridge guard from `patients.py`.
- 3 ScopeNote stubs replaced with real pages: `/citizen/immunisations`, `/citizen/audit` (DPPA §14 transparency view with 7/30/90-day filter chips), `/citizen/facilities` (sortable + OpenStreetMap directions).
- `/citizen/error.tsx` boundary; "Grant new consent" form added to `/citizen/consent`.
- `useAuthHydrated()` hook fixes the Zustand-persist hydration race that caused `/citizen/*` to flash to `/login` on browser reload.
- `_seed_self_audit_reads()` adds 3-5 synthetic prior worker reads per patient so the audit page is populated on first login.

### Added (MR — Mobile responsiveness pass, commit 71db247)
- New `<MobileNav>` component (`frontend/src/components/layout/mobile-nav.tsx`) — hamburger button + slide-down sheet at `<sm`. Before this, navigation links were `hidden sm:flex` with no fallback — phones literally had no way to switch between citizen/worker/admin sections after login.
- `Button` default + icon sizes bumped 40px → **44px** (Apple HIG minimum).
- `Table` wrapper extends to viewport edges on phones; tables forced to `min-w-[640px]` so they horizontally scroll instead of collapsing.
- `TabsList` wrapped in a horizontally scrollable container so 5-tab worker/patients/[id] header doesn't wrap.
- `viewportFit: "cover"` + `env(safe-area-inset-top)` padding on the sticky header.
- Container padding: `0.75rem` default → `1rem` sm → `1.5rem` lg.
- **Playwright section J** (6 tests at 390x844): login tappable, hamburger visible/hidden by viewport, sheet open/close + role-filtered links, table horizontal scroll, tabs reachable, sticky header.

### Fixed (CI — Crane Cloud deploy keyring bug, commit 2f417a2)
- `Deploy to Crane Cloud` workflow failed every run from `b7915fd` onward (8+ consecutive failures). Root cause: the workflow seeded `~/.cranecloud/token` from the GitHub secret, but the cranecloud CLI reads its token via `keyring.get_password('cranecloud', 'token')` — the file was decorative. Fixed by installing the `keyring` CLI and piping the secret into the file-backed keyring backend (`PYTHON_KEYRING_BACKEND=keyrings.alt.file.PlaintextKeyring`). "Verify CLI session" now explicitly probes the keyring entry before calling `cranecloud auth user` so a seeding failure is reported unambiguously. Cleanup step also clears `XDG_DATA_HOME/python_keyring/keyring_pass.cfg` to prevent stale-token leakage across runs on shared runners.

### Live (staging) — re-verified 2026-05-26 at sha-439fc79
- 96 Playwright tests pass against live Crane Cloud staging (across 11 describe blocks: Frontend pages, Backend documented endpoints, Auth & access control, Full login flows, Authenticated data flows, Frontend↔backend integration, Authenticated route walk, /me/* + safety, Worker dashboard, Mobile viewport, Immunisation schedule + family).
- Demo dataset: 26 patients (incl. ANC + paediatric + chronic + caregiver cohorts) across 8 districts, 14 facilities, 14 supply items, 4 caregiver links, 6 transfer history rows, populated audit log per patient.

### Added (P1 — Full CI/CD pipeline for Crane Cloud + Docker Hub)
- `.github/workflows/deploy-cranecloud.yml` overhauled: switched keyring backend from `null` to `keyrings.alt.file.PlaintextKeyring`; dropped `docker.io/` prefix on image refs; added pre-update capture of current image (for rollback); post-update health-check polling (6-min budget); **automatic rollback to previous image** if health check fails; smoke-test of `/fhir/metadata` + `/openapi.json` + `/api/v1/patients` 401 expectation; structured run-summary with live URLs + clickable probe links; PR comment with deployed URL when triggered with `pr_number`.
- `.github/workflows/deploy-databases.yml` (new): one-shot `workflow_dispatch` flow for Postgres + Redis (separate from rolling backend/frontend); five actions (`create-postgres`, `create-redis`, `create-both`, `update-postgres-image`, `update-redis-image`); surfaces ready-to-paste `gh secret set` commands in the run summary.
- `.github/workflows/release.yml` (new): on `v*` tag push, extracts the matching `CHANGELOG.md` section, lists the three Docker Hub image tags, marks pre-release for `v*-*` semver tags, creates the GitHub Release.

### Changed (CI/CD)
- `build-push.yml` and `deploy-cranecloud.yml` now use **Docker Hub** (`docker.io/mpairwe7/...`) instead of GHCR. Crane Cloud's RENU and AHUMAIN ML clusters cannot pull from `ghcr.io` (confirmed 2026-05-26 via control-deploy); Docker Hub pulls work cleanly. Requires repo variable `DOCKERHUB_USER` + repo secret `DOCKERHUB_TOKEN`.

### Live (staging) — verified 2026-05-26
- Backend: <https://healthsync-backend-staging-9b4ecff1.renu-01.cranecloud.io> — `/healthz` 200, `/readyz` `{status:"ready", database:"ok", redis:"ok"}`, `/fhir/metadata` returns FHIR R4 CapabilityStatement, `/openapi.json` lists 24 endpoints.
- Frontend: <https://healthsync-frontend-staging-b73f2f98.renu-01.cranecloud.io> — HTTP 200 with full security headers (`x-content-type-options`, `referrer-policy`, `permissions-policy`).
- All 4 Crane Cloud apps in project `healthsync-uganda-staging` (`572536c1-eee6-47a7-bff5-78e8bcc0d415`, RENU cluster) running.

### Added (P6 — Playwright E2E smoke tests against live staging)
- `frontend/e2e/playwright.config.staging.ts` — targets the deployed Crane Cloud URLs (`FE_URL`, `BE_URL` overrideable via env); single-worker (don't swamp single-replica staging); HTML reporter; trace + screenshot on failure. Workarounds for container/CI shells: `chromiumSandbox: false`, `--no-sandbox`, `--disable-dev-shm-usage`, `TMPDIR` redirected to local fs (default `/tmp` is on NFS where Chromium's `SingletonLock` fails with EOPNOTSUPP).
- `frontend/e2e/staging-smoke.spec.ts` — **19 tests covering** five describe blocks: landing + navigation (5 routes), PWA + security posture (3 — sw, manifest, headers), backend documented endpoints (5 — healthz, readyz, fhir/metadata, openapi.json, /docs), backend auth & access control (5 — 401/422/403 defenses), frontend↔backend integration (1 — no 5xx during login flow).
- `frontend/package.json` — adds `@playwright/test ^1.49.0` dev dep + three npm scripts (`e2e`, `e2e:staging`, `e2e:install`).
- `.gitignore` — adds `e2e-results/`, `**/test-results/`, `**/playwright-report/`.

**Last run:** 19/19 passed in 49.1 s against `https://healthsync-backend-staging-9b4ecff1.renu-01.cranecloud.io` + `https://healthsync-frontend-staging-b73f2f98.renu-01.cranecloud.io`.

**Wait-strategy note:** the frontend's TanStack Query + service-worker fetches keep the network perpetually busy, so `networkidle` never settles. Tests use `waitUntil: "domcontentloaded"` for navigation + an explicit `waitForTimeout(3000)` where bootstrap fetches matter — documented at the top of the spec file.

### Added (P5 — Submission packet rendered)
- `submission/HealthSync-Uganda-System-Description.pdf` — **4 pages A4, 41 KB**, rendered via `weasyprint` + Python `markdown` (no LaTeX needed). Recipe documented in `submission/README.md §3`.
- `submission/HealthSync-Uganda-System-Description.html` — HTML companion (~17 KB).
- `submission/figures/01-c4-context.png` … `04-security-boundaries.png` — **4 PNG diagrams** (60–130 KB each) rendered via `mmdc` with a no-sandbox Puppeteer config (required in container/CI shells).
- `submission/diagrams/01-c4-context.mmd` — patched: edge labels with `/` and `+` (which trip Mermaid 11.x's lexer in `-.label.->` syntax) are now quoted as `-. "label" .->`.
- `submission/README.md` — updated build recipe (weasyprint path replaces the previous pandoc+xelatex recipe; matches what was actually used to render); pre-submission checklist now reflects actual state (PDF 4 pages, 4/6 figures done, 2 UI screenshots still pending).
- All `submission/*` artefacts remain **gitignored** per project policy — exist only on the operator's local machine.

### Added (P4 — Crane Cloud operational quirks documented)
- `infra/cranecloud/README.md §10A` — captures every platform behaviour discovered during the live staging deploy: no `docker.io/` prefix on image URLs; containers must listen on port 3000 internally (cranecloud's ingress always proxies to :3000); `apps update -e` silently doesn't update env vars (delete + redeploy required); CLI positional-vs-flag quirks; keyring backend required for non-tty CI (`keyrings.alt.file.PlaintextKeyring`); TCP-service status flapping; URL-hex changes on every recreate; only RENU and AHUMAIN ML clusters available (makerere-1 disabled); no documented persistent volumes; `cranecloud apps info` exposes env values in plaintext.

### Added (P3 — Alembic migrations wired up)
- `backend/alembic.ini` + `backend/alembic/env.py` configured to read `DATABASE_URL` from the app's `Settings`, import `Base.metadata` + all 11 ORM models, and translate `asyncpg`/`aiosqlite` URLs to their sync equivalents (`psycopg`/`sqlite`) for Alembic's sync context.
- `backend/alembic/versions/498638f987ec_initial_schema_*.py` — initial migration auto-generated from `Base.metadata`; creates all 11 tables + indexes + GIN trigram index (on Postgres) and matches what `create_all` produces. Verified end-to-end against a fresh SQLite database.
- `backend/pyproject.toml` — added `psycopg[binary]>=3.2.0` to the `dev` dependency group (Alembic needs sync drivers).
- Backend's `auto_create_schema` setting remains the **default-on** behaviour for ephemeral envs. Production deployments where Alembic is run out-of-band should set `AUTO_CREATE_SCHEMA=false` and run `cd backend && uv run alembic upgrade head` as a pre-deploy step.

### Known follow-ups (pre-pilot)

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
