# Contributing to HealthSync Uganda

Thank you for your interest in HealthSync Uganda. This project powers public-sector
clinical workflows in Uganda, so we take change management seriously.

## Code of Conduct

All contributors must follow the [Code of Conduct](./CODE_OF_CONDUCT.md). Report
violations to **conduct@healthsync.ug**.

## Reporting security issues

**Do not** open a public issue for security vulnerabilities. See
[SECURITY.md](./SECURITY.md) for the coordinated-disclosure process.

## Ways to contribute

1. **Clinical review** — flag terminology, workflow or safety issues. We need
   nurses, clinical officers, pharmacists and DHOs more than we need code.
2. **Localisation** — extend `frontend/src/lib/i18n/dictionary.ts` with Runyankole,
   Luo, Lugbara and Ateso.
3. **FHIR profiles** — propose or refine national IGs in `backend/app/fhir/`.
4. **Bug reports** — please include the API version (`/healthz`), the request
   you sent, and the **`X-Trace-Id`** header from the response.
5. **Pull requests** — see "Development workflow" below.

## Development workflow

### Prerequisites

- **bun** ≥ 1.2 (frontend, tests)
- **uv** ≥ 0.5 (Python deps)
- **docker** + **docker compose** v2
- **make** (most workflows are exposed via the root `Makefile`)

### Bootstrap

```bash
make install   # bun install + uv sync
make up        # docker compose up -d
make seed      # demo facilities, citizens, encounters
```

Visit `http://localhost:3000` for the UI, `http://localhost:8000/docs` for the
OpenAPI explorer.

### Branching

- `main` is protected and always deployable.
- Feature branches: `feat/<short-slug>`, fixes: `fix/<short-slug>`,
  documentation: `docs/<short-slug>`.
- Rebase onto `main` before opening a PR; squash-merge is the default.

### Commit style

Conventional Commits:

```
feat(fhir): add Uganda Patient profile validator
fix(supply): retry breakers should fall closed under load
docs(adr): record FHIR R4 over openEHR decision
```

Reference issues in the commit body (`Refs: #123`, `Closes: #123`).

### Tests

| Layer    | Command                  | What it covers                           |
| -------- | ------------------------ | ---------------------------------------- |
| Backend  | `make test-backend`      | pytest + async SQLAlchemy + FHIR shapes  |
| Frontend | `make test-frontend`     | bun test + React Testing Library         |
| Types    | `make typecheck`         | `tsc --noEmit` + `mypy --strict`         |
| Lint     | `make lint`              | ruff + biome                             |
| Conformance | `scripts/fhir-conformance.sh` | FHIR R4 round-trip + Uganda profiles |

PRs must keep the full suite green. Tests are the smallest unit of trust in a
health system — please add them, don't skip them.

### Definition of done

A change is ready to merge when:

- [ ] All tests, type checks, and linters pass.
- [ ] Public API changes are reflected in `docs/API.md`.
- [ ] FHIR-touching changes pass `scripts/fhir-conformance.sh`.
- [ ] PHI-touching changes update [DPIA.md](./docs/DPIA.md) if the data flow
      changed.
- [ ] If you introduced a new external dependency, you have justified it on the
      PR (license, maintenance, security posture).
- [ ] Architectural decisions are captured as an ADR in `docs/adr/`.

### Documentation

Every behavioural change must update the user-facing docs:

- API additions → `docs/API.md`
- Operational changes → `docs/RUNBOOK.md`
- Strategy changes → `docs/ROADMAP.md` or `docs/MOH_ALIGNMENT.md`
- Architectural decisions → new ADR under `docs/adr/`

## Reviewing PRs

Reviewers look for:

1. **Patient safety** — does this change risk dropping, mis-attributing or
   misordering a clinical record?
2. **Data protection** — does this add a new PHI flow without DPIA coverage?
3. **Offline resilience** — does this assume the network is up?
4. **Observability** — can on-call diagnose this from logs/metrics/traces alone?

## Communication

- Day-to-day: GitHub Issues + Pull Requests.
- Real-time: `#healthsync-dev` on the MoICT&NG Slack workspace.
- Clinical/operational escalations: ministry liaison (see `docs/TEAM.md`).

## Licensing of contributions

By submitting a contribution you agree it is licensed under the Apache License,
Version 2.0 (see [LICENSE](./LICENSE)). Do not submit code you do not have the
right to license.
