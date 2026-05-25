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

## 12. Forward-looking architecture (2026+)

The architecture is **not** designed to chase trends, but the platform is engineered so that the following 2026-era concerns can be adopted without rewrite. Each line carries a stable identifier (`FA-NN`) and a target window aligned with [THREAT_MODEL.md §7 Roadmap Closure Plan](./THREAT_MODEL.md#7-roadmap-closure-plan).

### Zero-trust architecture

The detailed posture and roadmap live in [SECURITY.md §"Zero-trust elements"](./SECURITY.md#zero-trust-elements). Architecturally relevant items:

| ID    | Item                                                                                                                              | Target          |
| ----- | -------------------------------------------------------------------------------------------------------------------------------- | --------------- |
| FA-01 | Per-request JWT verification (already implemented) — no session-cookie trust path                                                 | Implemented     |
| FA-02 | Production IdP (Keycloak / Authentik / NIRA OIDC) issuing RS256 tokens; JWKS rotation                                              | Pre-national    |
| FA-03 | Service mesh (Istio or Linkerd) for in-cluster mTLS and NetworkPolicy enforcement                                                  | Pre-national    |
| FA-04 | Device attestation (FIDO L3 / WebAuthn) for the worker fleet                                                                       | Pre-national    |
| FA-05 | Continuous behavioural validation via OpenTelemetry — already exposes the signals that AL-12 … AL-14 in [OBSERVABILITY.md](./OBSERVABILITY.md) consume | Implemented     |

The pilot ships with FA-01 and FA-05 implemented; FA-02 → FA-04 are scheduled per the closure plan.

### Differential privacy for analytics

`/api/v1/analytics/*` returns aggregates only (DPPA s.31; [COMPLIANCE.md](./COMPLIANCE.md)). Aggregate output below a k-anonymity threshold can still leak when an attacker correlates multiple queries over time. The path forward:

| ID    | Item                                                                                                                                                                                                       | Target          |
| ----- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------- |
| FA-06 | **k-anonymity guard** on every analytics response: when a cell's underlying cohort is smaller than *k* (default *k* = 20), the cell returns `null` with a `"suppressed_for_privacy": true` flag.            | Pre-pilot       |
| FA-07 | **Laplace-noise injection** on integer counts and rate denominators for cells above *k* but below a second threshold (`k_noise = 100`). Magnitude calibrated to (ε, δ)-DP with ε ≤ 1 over a 24 h budget.    | During pilot    |
| FA-08 | **Per-actor query budget** — cumulative ε is tracked per `actor_id` per day; exceeding the budget downgrades responses to k-only suppression.                                                              | Pre-national    |
| FA-09 | **DP audit trail** — every DP-modified response carries a structured note in the audit log so reviewers can distinguish noise from data.                                                                    | Pre-national    |

This places HealthSync ahead of the typical 2026 East African digital-health baseline (which is usually plain k-anonymity at best).

### AI governance readiness

The platform does **not** train AI models on patient data in the pilot. The architecture nonetheless prepares for the inevitable: clinical decision-support, predictive stock-out alerts, NLP on clinical notes, image classification for AMR surveillance.

| ID    | Principle                                                                                                                                                              | Target / status                                                                                                                  |
| ----- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| FA-10 | **No model trained on identifiable data without explicit consent** (DPPA s.22). Training pipelines must consume the differential-privacy-protected analytics surface.    | Policy from day one; enforced at the data-access layer.                                                                          |
| FA-11 | **Model cards** for every deployed model — input schema, training data provenance, fairness evaluation across districts and gender, intended use, known failure modes. | Required at first model deployment (currently none). Card template in `docs/models/_template.md` to be added when first needed. |
| FA-12 | **Human-in-the-loop on clinical decisions.** AI outputs are advisory only; the clinician records the final decision in the encounter.                                  | Architecturally enforced via the existing `Encounter.diagnosis_codes` write path (clinician-authored only).                       |
| FA-13 | **Inference logging** — every AI-driven recommendation surfaced to a user produces an `audit_log` row with `action="ai-inference"` so the recommendation chain is auditable. | When first AI feature ships.                                                                                                     |
| FA-14 | **Africa CDC AI governance alignment** — track and implement Africa CDC AI-in-health framework recommendations as they ratify.                                          | Continuous.                                                                                                                       |

The principles are derived from the WHO *Ethics & Governance of AI for Health* guidance (2021, updated 2024) and the emerging Africa CDC Digital Transformation Strategy AI principles. They are *policy* commitments; the *technical* primitives (audit log, structured analytics, model-card template) are either implemented or scaffolded.

### Cross-references

- [SECURITY.md §"Zero-trust elements"](./SECURITY.md#zero-trust-elements) — operational counterpart of FA-01 … FA-05.
- [THREAT_MODEL.md §7 Roadmap Closure Plan](./THREAT_MODEL.md#7-roadmap-closure-plan) — the RR closures that the zero-trust roadmap rests on.
- [INTEROPERABILITY.md §"Forward-looking trends (2026+)"](./INTEROPERABILITY.md#forward-looking-trends-2026) — FHIR R5, IHE, Africa CDC.
- [COMPLIANCE.md](./COMPLIANCE.md) — DPPA controls already in place that FA-06 … FA-09 strengthen.
