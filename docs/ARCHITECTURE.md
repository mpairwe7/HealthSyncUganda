# Architecture

> **Reading audience:** Government CTOs, MoH technical leads, and competitors who want to know if this prototype is just a demo or actually production-ready.
>
> **TL;DR:** Stateless services, open standards, observability-first, designed to be operated by NITA-U or the Ministry of Health without lock-in.

---

## 1. Goals & non-goals

### Goals
- **Single source of truth** for patient records across Uganda's facility network.
- **Interoperability** with existing investments (DHIS2, eHMIS, OpenMRS) via FHIR R4, not replacement.
- **Resilience under hostile network conditions** — Uganda's connectivity is uneven; the system must be useful in a HC II in Karamoja as well as Mulago.
- **Compliance-by-construction** — Uganda Data Protection & Privacy Act (2019), audit by default, explicit consent.
- **No vendor lock-in** — every dependency is open source; every data format is an open standard.

### Non-goals
- Replacing DHIS2 or eHMIS. We integrate with them.
- Implementing every FHIR resource. We implement Patient, Encounter, Observation, MedicationDispense, SupplyDelivery, Bundle — what the demonstrated workflows need.
- Billing / insurance / health economics. Separate problems with separate experts.

## 2. System context (C4 Level 1)

```
                  ┌──────────────────────────────────────────────────────────┐
                  │                       Citizens                            │
                  │                  (web · PWA · USSD bridge)                │
                  └─────────────────────────┬────────────────────────────────┘
                                            │
   ┌──────────────────────┐                 │                  ┌──────────────────────┐
   │  Healthcare workers  │─────────────────┼─────────────────│  District/Ministry   │
   │  (PWA on tablets)    │                 │                  │  analysts & admins   │
   └──────────────────────┘                 │                  └──────────────────────┘
                                            ▼
                           ┌────────────────────────────────┐
                           │       HealthSync Platform       │
                           └──┬───────────────┬──────────────┘
              ┌───────────────┘               └─────────────────┐
              ▼                                                 ▼
   ┌──────────────────────┐                          ┌───────────────────────┐
   │       NIRA           │                          │   DHIS2 / eHMIS /     │
   │ (national identity)  │                          │   OpenMRS / external   │
   └──────────────────────┘                          └───────────────────────┘
```

## 3. Containers (C4 Level 2)

| Container | Role | Tech |
|---|---|---|
| `frontend` | Citizen, worker, admin PWAs | Next.js 16 (App Router, RSC, Streaming), TanStack Query, Zustand, IndexedDB |
| `api` | REST + FHIR R4 gateway | FastAPI, Pydantic v2, async SQLAlchemy |
| `postgres` | Canonical store | PostgreSQL 16 (with `pg_trgm`, `pgcrypto`) |
| `redis` | Cache · rate-limit · idempotency · DHIS2 queue | Redis 7 |
| `otel-collector` | Telemetry | OpenTelemetry Collector → tracing/metrics/logs backend |
| `interop-adapters` | NIRA, DHIS2 clients (in-process) | Resilient HTTPX clients |

## 4. Component view of `api`

```
                                         ┌─────────────────────────┐
HTTP ─►  CORSMiddleware ─►  RateLimit ─►  │  IdempotencyMiddleware  │
                                         └────────────┬────────────┘
                                                      ▼
                          ┌──────────────  AuditContextMiddleware  ─────────┐
                          │                                                 │
                          ▼                                                 ▼
                ┌──────────────────┐                              ┌────────────────────┐
                │  /api/v1 routes  │                              │   /fhir routes     │
                │  (Pydantic DTO)  │                              │   (FHIR R4 JSON)   │
                └────────┬─────────┘                              └─────────┬──────────┘
                         ▼                                                  ▼
                ┌──────────────────────────  service layer  ─────────────────────────┐
                │  supply_ledger · nira_client (resilient) · dhis2_client (resilient) │
                └────────┬───────────────────────┬───────────────────┬───────────────┘
                         ▼                       ▼                   ▼
                ┌─────────────────┐   ┌────────────────────┐   ┌──────────────┐
                │  SQLAlchemy ORM │   │ Redis (cache/queue)│   │  OTel SDK    │
                └─────────────────┘   └────────────────────┘   └──────────────┘
```

## 5. Data model

```
Patient ──┬─< Encounter ──< Observation
          ├─< Consent
          └─< AuditLog   (also referenced by every other resource)

Facility ─< StockBatch  ─< StockEvent  (append-only, hash-chained)
         └< Encounter
         
SupplyItem ─< StockBatch
            ─< StockTransfer
```

Notable decisions:

- **ULID primary keys** (26-char base32). Sortable by creation time, URL-safe, work in Postgres + SQLite identically.
- **`pg_trgm` indexes** on patient family names for instant fuzzy search.
- **`JSONBOrJSON` type decorator** so the same models run on Postgres (production) or SQLite (laptop demos) without a fork in the code.
- **Append-only ledger** for stock events with SHA-256 hash chaining (predecessor included in payload). The system is ready to anchor chain-heads to an external notary (Stellar, Hyperledger Iroha, public Merkle root) without altering business logic.

## 6. Resilience patterns

Implemented in [`backend/app/core/resilience.py`](../backend/app/core/resilience.py):

| Pattern | Where it applies | Behaviour on failure |
|---|---|---|
| **Retry** with exponential backoff + jitter | Every external HTTP call, idempotent reads | Up to 4 attempts with capped delay |
| **Circuit breaker** (3-state: closed → open → half-open) | Per-upstream (NIRA, DHIS2) | Trips after N consecutive failures; auto-recovers after timeout |
| **Bulkhead** (bounded concurrency) | Per-upstream | Excess requests fail fast instead of starving the worker pool |
| **Fallback to cache** | NIRA NIN verification | Last-known-good served from Redis with `via_fallback=true` flag |
| **Pending queue + replay** | DHIS2 tally pushes | Stored in Redis list, drained on the next successful call or by the `/interop/dhis2/drain-queue` endpoint |
| **Idempotency-Key** middleware | All unsafe HTTP methods | 24h replay window for safe client retries |
| **Stale-while-revalidate** | Frontend GETs | Cached via TanStack Query persisted store; service worker doubles up |
| **Offline mutation queue** | Frontend writes | IndexedDB-backed FIFO; replays on `online` event with the original idempotency key |

## 7. Observability

- **Structured logs** — JSON-shaped, every line carries `trace_id` / `span_id` so logs/traces correlate in any backend (Tempo, Honeycomb, Grafana Loki).
- **OpenTelemetry traces** — FastAPI, SQLAlchemy, Redis and HTTPX all instrumented. Custom spans on each `@resilient` call so dashboards show breaker trips & fallbacks distinctly.
- **Health probes** — `/healthz` (liveness) and `/readyz` (Redis + DB reachability) for Kubernetes.
- **OpenAPI 3** at `/openapi.json` for API consumers and code generators.

## 8. Security

See [`SECURITY.md`](SECURITY.md) for the full posture. Briefly:

- TLS 1.2+ enforced at the edge (HSTS preload-ready).
- Short-lived JWTs (HS256 by default; switch to RS256 / asymmetric for NIRA OIDC).
- Argon2 / bcrypt password hashing (bcrypt enabled by default for portability).
- Role-based access control with five tiers from `citizen` upwards.
- Every PII access goes through `record_access` → immutable `audit_log` table.
- CORS allow-list, no wildcards in production.
- Hardened response headers (`X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, HSTS).

## 9. Scalability

Stateless API workers scale horizontally behind a load balancer. Sticky sessions are *not* required. The only stateful components are Postgres (HA via patroni / managed RDS) and Redis (sentinel / managed). Bulk imports go through async tasks (a Celery / Arq variant can be dropped into `app.workers` without disturbing the request path).

## 10. Deployment

Local: `docker compose up`.

Production (recommended): Kubernetes — one Deployment per service, HorizontalPodAutoscaler on the API by request-per-second & p95 latency. A Helm chart can be derived from the Docker Compose without rewriting any service code.

## 11. Path to government adoption

The architecture deliberately matches the constraints of being *adopted* by the MoH or NITA-U:

- **Sovereignty.** Runs entirely on-premise or in the NITA-U government cloud. No data leaves Uganda.
- **Open formats.** Backups are Postgres `pg_dump` + Redis RDB. Migration to a different vendor is `pg_restore`, not a rewrite.
- **Operator-friendly.** Health probes, structured logs, OpenAPI, OTel — standard tooling a NITA-U engineer already knows.
- **No proprietary glue.** Every connector is HTTP + JSON over FHIR, easy to extend.
