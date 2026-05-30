# HealthSync Uganda

> **Interoperable National Digital Health Platform**
> Patient records · Supply-chain visibility · FHIR-based exchange · Offline-first

HealthSync Uganda is a prototype starter for a national digital health backbone designed for adoption by the Ministry of Health of Uganda. It links citizens' health records to the National Identification Number (NIN), exposes a FHIR R4 exchange layer for interoperability with existing systems (DHIS2, eHMIS, OpenMRS), and gives the Ministry real-time visibility into the medical supply chain — all while remaining usable on low-bandwidth and intermittently-connected devices.

Built for the **Uganda National Innovator Registry**, showcased at the **Government Systems Prototype Showcase, 25 June 2026**.

---

## Why this prototype

| Concern of the Ministry | How HealthSync answers it |
| --- | --- |
| Fragmented patient data across 6,937+ facilities | One canonical, NIN-linked patient record exposed via FHIR R4 |
| Drug stock-outs detected weeks late | Live facility-level inventory ledger with low-stock & expiry alerts |
| Poor connectivity in rural districts | Offline-first PWA; mutations queued and synced when online |
| Existing investment in DHIS2 / OpenMRS / eHMIS | Adapter layer with circuit-breaker isolation — never breaks legacy |
| Citizens' privacy & consent | Explicit consent records; immutable audit trail on every access |
| Vendor lock-in | Open standards (FHIR R4, OAuth2/OIDC, OpenTelemetry); open-source stack |

---

## Architecture at a glance

```
┌───────────────────────────────────────────────────────────────────────┐
│                        CITIZEN / WORKER / ADMIN                       │
│       Next.js 16 (App Router · Server Components · PWA · Offline)     │
└───────────────────────────────────────────────────────────────────────┘
                                  │  HTTPS / mTLS
                                  ▼
┌───────────────────────────────────────────────────────────────────────┐
│                          FastAPI Gateway                              │
│   Auth · Audit · Rate-limit · OpenTelemetry · Circuit-breaker         │
└──┬───────────────┬───────────────┬───────────────┬────────────────────┘
   ▼               ▼               ▼               ▼
┌────────┐   ┌──────────┐   ┌────────────┐   ┌──────────────┐
│ FHIR   │   │  Supply  │   │  Analytics │   │  Interop     │
│ Server │   │  Chain   │   │  & M&E     │   │  Adapters    │
└────┬───┘   └────┬─────┘   └────┬───────┘   └──────┬───────┘
     │            │              │                  │
     ▼            ▼              ▼                  ▼
┌─────────────────────────────┐  ┌───┐  ┌─────────────────────────┐
│      PostgreSQL (async)     │  │ R │  │  NIRA · DHIS2 · eHMIS   │
│   FHIR resources · ledger   │  │ed │  │   (resilient adapters)  │
└─────────────────────────────┘  └───┘  └─────────────────────────┘
```

A full architectural deep-dive is in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Tech stack

**Frontend** — Next.js 16.2.6 (App Router, streaming, RSC), TypeScript (strict), Bun, Zustand, TanStack Query v5 (persisted IndexedDB cache + offline mutation queue), shadcn/ui, Tailwind CSS.

**Backend** — FastAPI, Pydantic v2 (strict), uv, Python 3.12+, SQLAlchemy 2 async, asyncpg, Redis, OpenTelemetry.

**Standards** — FHIR R4, OAuth2 / OIDC-ready, ISO 8601, HL7 terminologies (LOINC, SNOMED CT, ICD-10) — abstracted so they can be swapped for Uganda Clinical Guidelines code systems.

**Infrastructure** — Docker Compose for local; Kubernetes-ready (12-factor, stateless workers, externalised state).

---

## Quick start

### Prerequisites

- [Bun](https://bun.sh) ≥ 1.1 (`curl -fsSL https://bun.sh/install | bash`)
- [uv](https://docs.astral.sh/uv/) ≥ 0.5 (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Docker + Docker Compose (for Postgres / Redis / OTel collector)

```bash
cp .env.example .env
```

### One-shot, all services in Docker

```bash
make full              # or: docker compose --profile full up --build
```

- Frontend → http://localhost:3000
- API      → http://localhost:8000/docs (Swagger)
- FHIR     → http://localhost:8000/fhir/metadata

### Local dev (recommended for engineers)

The local-dev flow runs the **databases in Docker** and the **services on the host** so reloads are instant.

```bash
make stack             # Postgres + Redis only (waits for healthchecks)
make seed              # idempotent demo data (~1 second)
make backend           # FastAPI + auto-reload on :8000
make frontend          # Next.js dev server on :3000   (separate shell)
```

Other useful targets — run `make help`:

| Target | What it does |
|---|---|
| `make full` | Full Docker stack (Postgres, Redis, backend, frontend) |
| `make stack` | Just Postgres + Redis for local dev |
| `make reset` | Drop DB + flush Redis + re-seed (between rehearsals) |
| `make preflight` | Pre-show health check — verifies every load-bearing service |
| `make test` | Backend tests |
| `make typecheck` | Frontend TypeScript check |
| `make lint` | ruff + eslint |

### Why Redis matters

The service boots even if Redis is down — every middleware degrades open — but several demo moments only shine when Redis is healthy:

- **Idempotency replay** (`X-Idempotent-Replay: true` on retried mutations)
- **Analytics cache** (60-second TTL on heavy dashboards)
- **DHIS2 outbox** (failed pushes queued in `dhis2:pending`)
- **NIRA fallback cache** (last-known-good NIN response served when NIRA is unreachable)

`make stack` and `make full` both start Redis automatically. The backend logs a clear `redis_unavailable` warning at startup if it can't reach Redis, and `/readyz` returns 503 with a structured body listing exactly what's broken.

### Per-environment URLs

`.env.example` defaults to **localhost** so `make stack && make backend && make frontend` works out of the box. The Docker Compose file **explicitly overrides** the hostnames inside the network (`postgres`, `redis`, `backend`) so you don't edit `.env` for the Docker path. For production, override `NIRA_BASE_URL` / `DHIS2_BASE_URL` / `DATABASE_URL` etc. via the deploying shell — the precedence is `shell env` > `compose environment:` > `.env`.

---

## Demo script (25 June 2026 showcase)

A complete 8-minute walkthrough is in [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md). Highlights:

1. **Citizen logs in with NIN** (mocked NIRA verification with circuit breaker shown failing-open).
2. **A nurse in Gulu enrols a patient offline** — service worker queues; the sync indicator lights up; tab is closed; another tab reopens online and the record materialises.
3. **A district pharmacist sees a low-stock alert for ACT** in Mbarara HC IV and initiates a transfer from the Regional Referral store; the ledger entry is shown.
4. **The MoH analytics view** lights up: immunisation coverage by district, supply-chain heat-map.
5. **Audit trail** is shown — every access traced to a user, purpose, and consent record.
6. **Resilience demo** — we kill the DHIS2 mock; the dashboard degrades gracefully, banner indicates "DHIS2 read-only fallback", core flows keep working.

---

## Project layout

```
HealthSyncUganda/
├── backend/                    FastAPI · FHIR · supply chain
│   ├── app/
│   │   ├── api/v1/             versioned REST endpoints
│   │   ├── core/               resilience, security, telemetry, audit
│   │   ├── db/                 async SQLAlchemy models + session
│   │   ├── fhir/               FHIR R4 resources & exchange layer
│   │   ├── services/           interop adapters (NIRA, DHIS2…)
│   │   ├── schemas/            Pydantic v2 strict schemas
│   │   └── seed/               realistic Uganda demo data
│   └── tests/
├── frontend/                   Next.js 16 PWA
│   └── src/
│       ├── app/                citizen / worker / admin route groups
│       ├── components/         shadcn/ui + domain widgets
│       ├── lib/                offline queue, FHIR client, stores
│       └── hooks/
├── docs/                       architecture, security, demo, interop
├── infra/                      OTel collector, postgres init
└── docker-compose.yml
```

---

## Positioning for the National Innovator Registry

Beyond the code, this prototype is positioned to address what the Registry evaluation committee actually weighs (see [`docs/POSITIONING.md`](docs/POSITIONING.md)):

- **Production-readiness** — observability, audit, graceful degradation are first-class, not afterthoughts.
- **Standards-first** — FHIR R4 means MoH never has to migrate again to integrate the next vendor.
- **Sovereignty** — runs on-premise or in NITA-U's cloud; no data leaves Uganda by default.
- **Local fit** — built for variable networks, mobile-first, designed around NIN and Uganda's facility hierarchy (HC II → III → IV → HC, RRH, NRH).
- **Open** — every line is open source; the MoH can fork and own its own destiny.

---

## Documentation & change history

The complete audit-facing documentation set lives in [`docs/`](docs/README.md) — start with the role-based reading paths in §7 of that index. User-visible changes between releases are recorded in [`CHANGELOG.md`](CHANGELOG.md).

## License

Apache-2.0. Designed to be donated to the Government of Uganda under permissive terms.
