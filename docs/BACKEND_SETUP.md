# Backend setup

**Audience:** engineers, SREs, pilot partners running the platform on their own infrastructure.
**Time to working API:** ~10 minutes on a clean Ubuntu/macOS workstation.

This document is the authoritative bootstrap for the `backend/` FastAPI service. Every command in this file is a real command in this repository — copy-paste should work without edits.

---

## 1. Prerequisites

| Tool       | Version  | Why                                                            | How to install                                                |
| ---------- | -------- | -------------------------------------------------------------- | ------------------------------------------------------------- |
| Python     | **3.12**+| Backend runtime.                                               | `https://www.python.org/downloads/`                           |
| uv         | 0.5+     | Dependency manager (replaces pip / poetry).                    | `curl -LsSf https://astral.sh/uv/install.sh \| sh`            |
| Docker     | 24+      | Postgres + Redis + OTLP collector via compose.                 | `https://docs.docker.com/engine/install/`                     |
| Docker Compose | v2   | Multi-container orchestration.                                 | Bundled with modern Docker Desktop / `docker-compose-plugin`. |
| Make       | any      | Task runner (`make help` lists the verbs).                     | Pre-installed on Linux / macOS.                               |
| curl + jq  | any      | `scripts/fhir-conformance.sh` uses them.                       | `sudo apt install curl jq` / `brew install jq`.               |

Confirm in one go:

```bash
python3 --version && uv --version && docker --version && \
  docker compose version && jq --version
```

You do **not** need to create a virtualenv yourself. `uv` manages a project-local one under `backend/.venv` automatically.

---

## 2. Clone and configure

```bash
git clone https://github.com/mpairwe7/HealthSyncUganda.git
cd HealthSyncUganda
cp .env.example .env
```

Open `.env` and rotate the development secret:

```bash
sed -i.bak "s|change-me-to-32-bytes-of-randomness-please|$(openssl rand -hex 32)|" .env
rm -f .env.bak
```

The file is generously commented; every variable explains its purpose, default, and the production override pattern. Two notes:

- `DATABASE_URL` defaults to `postgresql+asyncpg://healthsync:healthsync@localhost:5432/healthsync`. Docker Compose overrides this to in-network hostnames automatically — you do **not** edit `.env` to switch between local and docker.
- `NIRA_BASE_URL` / `DHIS2_BASE_URL` default to internal mock endpoints (`/api/v1/interop/mock/*`). Production overrides point at `https://api.nira.go.ug/...` / `https://dhis2.moh.go.ug/...`.

---

## 3. Install dependencies

```bash
cd backend
uv sync
```

`uv sync` reads `pyproject.toml` + `uv.lock` and materialises the exact dependency set into `backend/.venv`. The whole tree resolves in ~30 seconds on a warm cache.

What you get (full list in `backend/pyproject.toml`):

- **Web**: FastAPI, uvicorn[standard]
- **Validation**: pydantic v2, pydantic-settings, email-validator
- **Persistence**: SQLAlchemy 2 (async), asyncpg, aiosqlite (laptop fallback), alembic
- **Cache / queue**: redis-py + hiredis
- **Resilience**: tenacity (retry), purgatory (async circuit breaker), httpx
- **Auth**: bcrypt, pyjwt
- **Observability**: opentelemetry-{api,sdk,exporter-otlp-proto-grpc} + instrumentations for FastAPI, SQLAlchemy, Redis, httpx, structlog
- **Standards**: `fhir.resources` (HL7-published Pydantic models for FHIR R4)
- **Misc**: orjson, python-ulid

Dev-only extras (linters, pytest, etc.) are in the `[dependency-groups].dev` table and are installed by default.

---

## 4. Start supporting services

Two infrastructure containers are required: Postgres (clinical data) and Redis (cache, idempotency, DHIS2 outbox).

```bash
# From the repo root
make stack
```

Behind the scenes (see `scripts/dev-stack.sh`): `docker compose up -d postgres redis`. The compose file pins both to versions that match the production targets in `DEPLOYMENT.md`.

Verify both are healthy:

```bash
docker compose ps              # both should show "healthy"
docker compose logs --tail=20 postgres | grep "ready to accept connections"
```

If Redis is unavailable the API will still boot and serve, but `/readyz` returns HTTP 503 with `redis_unavailable` and several demo moments (idempotency replay, analytics cache, DHIS2 graceful degradation) cannot be exercised. See [RESILIENCE.md](./RESILIENCE.md) §"Redis down".

---

## 5. Run the API

```bash
make backend
```

Equivalent to: `cd backend && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`.

Smoke-test:

```bash
curl -s http://localhost:8000/healthz | jq .
# {"status":"ok","version":"0.1.0","redis":"ok","db":"ok"}

curl -s http://localhost:8000/openapi.json | jq '.info.title'
# "HealthSync Uganda API"

open http://localhost:8000/docs            # Swagger UI
open http://localhost:8000/fhir/metadata   # FHIR CapabilityStatement
```

Hot-reload watches `backend/app/**`. Config changes (`.env`) require a manual restart because `pydantic-settings` reads them once on boot.

---

## 6. Seed demo data

The seeder is idempotent — re-running it is safe.

```bash
make seed
```

It creates:

- Facilities at every level of the Uganda hierarchy (HC II → NRH) across six districts.
- Demo users for each role (passwords match `docs/DEMO_SCRIPT.md`):
  - `admin / admin1234` (ministry_admin)
  - `district.kampala / demo1234` (district_admin)
  - `nurse.gulu / demo1234` (worker)
  - `pharmacist.mbarara / demo1234` (pharmacist)
- Citizens (Akello, Mukasa, Nansamba, …) with NINs matching the format documented in [INTEROPERABILITY.md](./INTEROPERABILITY.md).
- Encounters spanning the last 90 days for time-series analytics.
- Stock balances with one item deliberately below threshold (Mbarara RRH, Artemether/Lumefantrine) to exercise the alert path.

Source of truth: `backend/app/seed/run.py`.

---

## 7. Run the tests

```bash
make test
# equivalent: cd backend && uv run pytest -q
```

What runs:

- Unit tests for FHIR validators, the resilience decorator, security helpers, hash-chain verification.
- Integration tests with a transient SQLite test database (`aiosqlite`) for fast CI.
- Contract tests that hit the running mocks (idempotency replay, breaker trip, audit recording).

For coverage:

```bash
cd backend
uv run pytest --cov=app --cov-report=term-missing
```

Target: ≥ 70 % (NFR-070 in [REQUIREMENTS.md](./REQUIREMENTS.md)).

---

## 8. Lint and type-check

```bash
make lint
```

Backend lints with ruff (`backend/pyproject.toml` → `[tool.ruff]`). Type checks run with mypy in strict mode:

```bash
cd backend
uv run mypy app
```

CI runs both on every push.

---

## 9. Database migrations

Migrations are managed by Alembic. The seeder calls them automatically.

```bash
cd backend
uv run alembic upgrade head        # apply all pending
uv run alembic revision --autogenerate -m "add foo column"   # new migration
uv run alembic history             # view applied + pending
uv run alembic downgrade -1        # roll back the last
```

Migration safety rules — see [RUNBOOK.md](./RUNBOOK.md) §"Schema changes":

- Never drop or rename a column in a single migration. Use the **add → backfill → switch reads → switch writes → drop** sequence.
- Never write a non-trivial migration without a tested rollback.
- Migrations that touch `ledger_entry` MUST preserve the append-only invariant (see ADR 0004).

---

## 10. Common errors

| Symptom                                                                    | Likely cause                                  | Fix                                                                                          |
| -------------------------------------------------------------------------- | --------------------------------------------- | -------------------------------------------------------------------------------------------- |
| `asyncpg.exceptions.InvalidCatalogNameError: database "healthsync" does not exist` | Postgres container started but DB not yet created. | `docker compose down -v && make stack` (the init SQL runs on a fresh volume).                |
| `ConnectionRefusedError: redis://localhost:6379`                            | Redis container not running.                  | `make stack`, then verify with `docker compose ps`.                                          |
| `passlib`/`bcrypt` startup crash                                            | Version mismatch.                             | We use bcrypt directly with 72-byte truncation — see `backend/app/core/security.py`.         |
| `pydantic.ValidationError` on boot, complaining about `SECRET_KEY`         | The default placeholder is still in `.env`.   | Rotate per §2 above.                                                                          |
| `/readyz` returns 503 `redis_unavailable`                                   | Backend booted before Redis was healthy.      | Wait 5 s and re-check, or `docker compose restart backend` (full stack path).                 |
| Tests pass locally but fail in CI on `test_idempotent_replay`              | Test run shared the same Redis DB index.      | Tests use `db=15` reserved for tests; ensure CI Redis is fresh per run.                       |
| `module 'fhir.resources' has no attribute 'Patient'`                        | Old `fhir.resources` (<8.0).                  | Re-run `uv sync` after pulling.                                                              |

---

## 11. Project layout (backend)

```
backend/
├── app/
│   ├── api/v1/         # HTTP routers — auth, patients, encounters, supply, ...
│   ├── core/           # Security, settings, resilience decorator
│   ├── db/             # SQLAlchemy models, async engine, repositories
│   ├── fhir/           # FHIR profiles and serialisers (Uganda extensions)
│   ├── middleware/     # Audit, idempotency, X-Trace-Id, request logger
│   ├── schemas/        # Pydantic v2 request/response schemas (non-FHIR)
│   ├── seed/           # Idempotent demo data
│   ├── services/       # External clients (NIRA, DHIS2) + domain logic
│   ├── supply/         # Hash-chain ledger
│   ├── workers/        # Background queue drainers
│   ├── config.py       # Settings (pydantic-settings)
│   └── main.py         # FastAPI app factory + lifespan
├── tests/              # pytest
├── Dockerfile          # Production image (multi-stage, distroless)
├── pyproject.toml      # Dependencies + tool config
└── uv.lock             # Pinned dependency tree
```

For the wider architecture context see [ARCHITECTURE.md](./ARCHITECTURE.md).

---

## 12. Next steps after a clean bootstrap

1. Run `scripts/preflight.sh` — verifies every load-bearing service end-to-end.
2. Run `scripts/fhir-conformance.sh` — 18-check FHIR R4 round-trip suite.
3. Read [API.md](./API.md) to call the endpoints.
4. Walk the demo path in [DEMO_SCRIPT.md](./DEMO_SCRIPT.md).
