# Observability

**Audience:** SREs, on-call engineers, MoH operations, anyone wiring monitoring against the platform.
**Source of truth:** `backend/app/core/{logging,telemetry}.py` for the wiring; [SCALABILITY.md §1](./SCALABILITY.md#1-performance-budget) for per-endpoint budgets; this document for the SLO contract and alert catalogue.
**Last reviewed:** 2026-05-25.

This document is the **observability contract** — the SLOs we promise, the alerts that fire when we are breaching them, the telemetry signals that flow into those alerts, and the dashboards an operator opens first. [RUNBOOK.md](./RUNBOOK.md) is the canonical place for *what to do*; this document is *what to watch and why*.

Stable IDs: `SLO-NN` for service-level objectives, `AL-NN` for alerts (each `AL-NN` references a `RB-NN` procedure).

---

## 1. Service-Level Objectives

The operational SLO set is canonical here. Per-endpoint *performance budgets* (p50/p95/p99 per route at a given replica size) live in [SCALABILITY.md §1](./SCALABILITY.md#1-performance-budget); this document does not duplicate them.

| ID    | Objective                                | Target                            | Window     | Error budget                             | Owner          |
| ----- | ---------------------------------------- | --------------------------------- | ---------- | ---------------------------------------- | -------------- |
| SLO-1 | API availability                          | 99.5 %                            | 30 days    | ~3.6 h / month                            | Platform team  |
| SLO-2 | API latency p95 (read endpoints)          | < 250 ms                          | 30 days    | 5 % of requests can exceed                | Platform team  |
| SLO-3 | API latency p95 (write endpoints)         | < 500 ms                          | 30 days    | 5 % of requests can exceed                | Platform team  |
| SLO-4 | FHIR endpoint latency p95                 | < 350 ms                          | 30 days    | 5 % of requests can exceed                | Platform team  |
| SLO-5 | Interop adapter degradation               | Breaker open ≤ 5 % of any 5-min window | rolling | n/a — breaker open is *desired* during upstream outage; alert fires on sustained open without upstream confirmation | Platform team |
| SLO-6 | Data integrity — patient records          | 0 unrecoverable records           | unbounded  | None                                      | DPO + Platform |
| SLO-7 | Audit log durability                      | 0 lost rows                       | unbounded  | None                                      | DPO + Platform |
| SLO-8 | Supply ledger integrity                   | 0 hash-chain breaks               | unbounded  | None — break trips IR-21                  | Platform team  |
| SLO-9 | RPO (Recovery Point Objective)            | 15 min                            | per incident | n/a                                     | Platform team  |
| SLO-10 | RTO (Recovery Time Objective)            | 60 min                            | per incident | n/a                                     | Platform team  |
| SLO-11 | Citizen consent revocation propagation    | ≤ 60 s end-to-end                 | per revoke | n/a                                       | Platform team  |
| SLO-12 | Idempotency replay correctness            | 100 %                             | unbounded  | None — replay must return original result | Platform team  |

SLO-1 / SLO-2 / SLO-3 / SLO-4 are the **error-budget-bearing** SLOs. SLO-6 / SLO-7 / SLO-8 / SLO-12 are **invariants** — any breach is an incident under [INCIDENT_RESPONSE.md](./INCIDENT_RESPONSE.md), not a budget burn.

---

## 2. Alert catalogue

Each alert has a stable ID, a trigger expression, a severity (matching [RUNBOOK.md §Severity](./RUNBOOK.md#severity--escalation)), and a runbook procedure. Alerts route via the on-call pager for SEV-1/SEV-2 and via the engineering channel for SEV-3/SEV-4.

| ID    | Name                                   | Trigger (logical)                                                                                  | SLO breach    | Severity | Procedure                                       |
| ----- | -------------------------------------- | -------------------------------------------------------------------------------------------------- | ------------- | -------- | ----------------------------------------------- |
| AL-01 | API down                                | `/healthz` failing > 1 min on majority of replicas                                                 | SLO-1         | SEV-1    | [RB-01](./RUNBOOK.md#rb-01)                     |
| AL-02 | Readiness flapping                      | `/readyz` returning 503 > 5 min                                                                    | SLO-1 (partial)| SEV-2    | [RB-01](./RUNBOOK.md#rb-01)                     |
| AL-03 | p95 latency burn                        | Read-endpoint p95 > 250 ms for > 10 min (5-min windows)                                            | SLO-2         | SEV-2    | [RB-04](./RUNBOOK.md#rb-04)                     |
| AL-04 | Write-endpoint p95 burn                 | Write-endpoint p95 > 500 ms for > 10 min                                                           | SLO-3         | SEV-2    | RB-04 + check breakers                          |
| AL-05 | Breaker stuck open                      | Same breaker `open` > 15 min                                                                       | SLO-5         | SEV-2    | [RB-02](./RUNBOOK.md#rb-02)                     |
| AL-06 | DHIS2 outbox growing                    | `dhis2.outbox.depth` rising > 5 min with no drain                                                  | SLO-5         | SEV-2/3  | [RB-03](./RUNBOOK.md#rb-03)                     |
| AL-07 | DB connection pool saturated            | Active connections > 90 % of `max_connections` for > 2 min                                         | SLO-1, SLO-2  | SEV-2    | [RB-04](./RUNBOOK.md#rb-04)                     |
| AL-08 | DB replica lag                          | `pg_last_xact_replay_timestamp()` lag > 60 s                                                       | SLO-9         | SEV-2    | [RB-10](./RUNBOOK.md#rb-10) prep                 |
| AL-09 | Backup did not run                      | No new backup object in evidence bucket in > 26 h                                                  | SLO-9         | SEV-2    | [RB-09](./RUNBOOK.md#rb-09)                     |
| AL-10 | TLS cert expiring                       | < 14 days remaining and no successful ACME renewal                                                 | SLO-1 risk    | SEV-3    | [RB-11](./RUNBOOK.md#rb-11)                     |
| AL-11 | Auth rate-limit burst                   | Sustained 429 on `/auth/*` from a small IP set > 10 min                                            | n/a — attack indicator | SEV-2 | [RB-05](./RUNBOOK.md#rb-05)             |
| AL-12 | Cross-district worker reads             | A single `actor_id` reads > 5 patients outside their facility scope in 5 min                       | n/a — IR signal | SEV-1   | [IR-01](./INCIDENT_RESPONSE.md#ir-01--triggers) |
| AL-13 | Bulk PII read                           | A single `actor_id` reads > 50 `Patient` records in 5 min                                          | n/a — IR signal | SEV-1   | [IR-01](./INCIDENT_RESPONSE.md#ir-01--triggers) |
| AL-14 | Off-hours PHI access                    | > 20 PHI reads between 22:00 and 05:00 Africa/Kampala                                              | n/a — IR signal | SEV-2   | [IR-01](./INCIDENT_RESPONSE.md#ir-01--triggers) |
| AL-15 | Supply ledger broken                    | Nightly `GET /api/v1/supply/ledger/verify` returns `ok=false`                                      | SLO-8         | SEV-1    | [RB-07](./RUNBOOK.md#rb-07) + [IR-21](./INCIDENT_RESPONSE.md#ir-21--supply-ledger-broken) |
| AL-16 | Audit-write failure                     | Any 5xx whose root cause is "audit_log INSERT failed" (any non-zero count)                          | SLO-7         | SEV-1    | [RB-13](./RUNBOOK.md#rb-13)                     |
| AL-17 | Restore drill failed                    | Quarterly drill produces a checksum mismatch                                                       | SLO-9, SLO-10 | SEV-2    | [BACKUP_RESTORE.md](./BACKUP_RESTORE.md) §drill review |
| AL-18 | Consent revoke propagation lag          | A `revoke` returns success but a subsequent read within 60 s still returns the consented payload   | SLO-11        | SEV-2    | RB-04 + invalidate Redis NIRA/analytics caches  |
| AL-19 | Idempotency replay mismatch             | Replay returns a different result body or status than the cached original                          | SLO-12        | SEV-1    | [RB-13](./RUNBOOK.md#rb-13)                     |
| AL-20 | Dependency advisory unaddressed > 5 d   | OSV-Scanner or Dependabot alert open > 5 working days without a Disposition row in SECURITY.md      | n/a — process | SEV-3    | Triage; update [SECURITY.md](./SECURITY.md) advisories table |

Conventions:

- A SEV-1 alert pages two engineers (primary + secondary) and the DPO if the alert maps to an IR signal (AL-12, AL-13, AL-14, AL-15, AL-16, AL-19).
- AL-12 through AL-14 are detection signals only — they *fire* but they do not *classify*. The on-call activates [IR-01](./INCIDENT_RESPONSE.md#ir-01--triggers) for the classification step.
- Every alert that pages must have a corresponding `RB-NN` or `IR-NN`. New alerts without a procedure are not allowed in production.

---

## 3. Telemetry contract

### 3.1 Logs

**Format:** JSON, one event per line, written to stdout (collected by the container runtime, shipped to Loki/Elastic/SIEM).
**Library:** `structlog` configured in `backend/app/core/logging.py`.
**Per-event fields (always present):**

| Field        | Source                                          | Notes |
| ------------ | ----------------------------------------------- | ----- |
| `timestamp`  | `TimeStamper(fmt="iso", utc=True)`              | ISO-8601 UTC. |
| `level`      | stdlib log level                                 | `info`, `warning`, `error`, `critical`. |
| `logger`     | logger name                                      | E.g. `app.api.v1.patients`. |
| `event`      | the user-supplied message key                    | E.g. `"audit"`, `"patient.created"`, `"breaker.open"`. |
| `trace_id`   | OpenTelemetry active span (`_add_trace_context`) | 32-hex; absent when no span is active. |
| `span_id`    | OpenTelemetry active span                        | 16-hex; absent when no span is active. |

**Per-event fields (event-specific):** structlog keyword arguments are merged in. The audit event always carries `actor`, `role`, `resource_type`, `resource_id`, `action`, `purpose` (see [ACCESS_CONTROL.md §5](./ACCESS_CONTROL.md#5-audit-semantics)).

**Noisy libraries muted:** `uvicorn.access`, `sqlalchemy.engine.Engine`, `httpx`, `httpcore` are pinned to `WARNING` minimum so the signal-to-noise ratio stays usable.

**Retention:** ≥ 1 year for DPPA s.13/s.14 (see [DATA_MODEL.md §6](./DATA_MODEL.md#6-data-not-in-postgresql)). Cold-tier archive permitted after 30 days, but the index must remain searchable.

### 3.2 Traces

**Stack:** OpenTelemetry SDK with OTLP gRPC exporter (`backend/app/core/telemetry.py`).
**Activation:** only when `OTEL_EXPORTER_OTLP_ENDPOINT` is set; otherwise the SDK is a no-op (zero overhead on laptop demos).
**Resource attributes:** `service.name` (from env), `service.version=0.1.0`, `deployment.environment` (from env).
**Instrumentation:**

- `FastAPIInstrumentor` — request span per route. **Excluded:** `healthz`, `readyz`, `metrics` (to keep probe noise out of traces).
- `SQLAlchemyInstrumentor` with `enable_commenter=True` — SQL spans + statement comments for trace-to-query correlation in Postgres logs.
- `RedisInstrumentor` — command spans.
- `HTTPXClientInstrumentor` — outbound HTTP spans (NIRA, DHIS2).

**Span processor:** `BatchSpanProcessor` (asynchronous, low overhead).
**Sampler:** parent-based always-on by default; override via `OTEL_TRACES_SAMPLER` for high-traffic deployments.
**Retention:** 30 days target (Tempo). Required for IR forensics ([IR-10](./INCIDENT_RESPONSE.md#phase-a--preparation-always-on)).

### 3.3 Metrics

The current platform exports metrics through the OpenTelemetry pipeline (FastAPI instrumentation emits HTTP server metrics; SQLAlchemy and Redis emit client metrics). Metric names follow the OpenTelemetry semantic conventions (`http.server.duration`, `db.client.connections.usage`, etc.).

Custom metrics are emitted via the application logger as structured events (`event="breaker.state", state="open"`) and surfaced in Loki dashboards rather than a separate metric pipeline. This keeps the operational footprint small for pilot deployments; production-tier deployments may add a Prometheus exporter.

### 3.4 Correlation

A request flows through three pipelines (logs, traces, metrics) and three storage tiers (Loki, Tempo, Postgres for audit_log). Correlation is by `trace_id`:

- The HTTP request gets a `trace_id` from `FastAPIInstrumentor`.
- That `trace_id` is injected into every structlog event via `_add_trace_context`.
- The same `trace_id` is included in SQL statement comments (`enable_commenter=True`) so a Postgres slow-query log row can be backtracked to the originating request.
- Audit-log rows do **not** store the `trace_id` in a dedicated column (the schema does not have one); the linkage is via timestamps and the log mirror.

`X-Trace-Id` is exposed on outbound responses so support tickets can quote it.

---

## 4. Dashboards

| Dashboard                  | What it answers                                                                  | Required panels                                                                       |
| -------------------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| HealthSync — overview      | "Is the platform healthy right now?"                                              | Request rate, error rate by route, p50/p95/p99 latency, breaker states, DHIS2 outbox depth, DB pool utilisation, Redis connectivity |
| HealthSync — auth          | "Is anyone hammering the login endpoints?"                                       | 401/429 by route, login successes by role, citizen-OTP failures by NIN (top 20)        |
| HealthSync — supply         | "Is the supply chain healthy?"                                                   | Stock-event rate, ledger-verify status, low-stock alerts, transfers in flight          |
| HealthSync — interop        | "How are NIRA and DHIS2 behaving?"                                               | Breaker state timeline, retry budget consumption, outbox depth, response p95 per upstream |
| HealthSync — audit          | "Who did what?"                                                                   | Top actors by access count (24 h), cross-facility reads, off-hours bursts, action mix  |
| Tempo (trace search)        | "What did this specific request do?"                                              | Trace search by `trace_id`; spans across FastAPI → SQLAlchemy → Redis → NIRA/DHIS2     |
| Loki (log search)           | "What did actor X / endpoint Y do over time?"                                     | Free-text and structured filters: `actor_id`, `resource_type`, `purpose`, `event`     |

Dashboards are versioned alongside the code (`infra/grafana/dashboards/*.json`, where present); changes follow the same PR review discipline as code.

---

## 5. Deployment-shape differences

How observability lands at each [DEPLOYMENT.md](./DEPLOYMENT.md) tier:

| Tier                          | Logs                         | Traces                                | Metrics                  | Dashboards                |
| ----------------------------- | ---------------------------- | ------------------------------------- | ------------------------ | ------------------------- |
| Laptop demo                   | stdout (console renderer)     | OTel disabled (no exporter)           | n/a                      | n/a                        |
| Pilot single-host             | docker compose `observability` profile → OTel Collector → file or local Loki | OTel Collector → local Tempo | OTel server metrics in Collector | Local Grafana             |
| National Kubernetes           | Fluent Bit / Vector → SIEM (Loki/Elastic/Wazuh) | OTel Collector → managed Tempo | Prometheus exporter (optional) | Managed Grafana          |

The application *code* is identical across tiers. Only the operator-supplied infrastructure changes.

---

## 6. Cross-references

- [SCALABILITY.md](./SCALABILITY.md) — per-endpoint performance budgets and capacity sizing (the *what* this document monitors).
- [RUNBOOK.md](./RUNBOOK.md) — every `RB-NN` referenced by an `AL-NN` here.
- [INCIDENT_RESPONSE.md](./INCIDENT_RESPONSE.md) — every `IR-NN` signal mapped from `AL-12`…`AL-19`.
- [SECURITY.md](./SECURITY.md) — log redaction, advisories triage cadence behind `AL-20`.
- [RESILIENCE.md](./RESILIENCE.md) — breaker semantics behind `AL-05`, `AL-06`.
- [DATA_MODEL.md §6](./DATA_MODEL.md#6-data-not-in-postgresql) — log/trace retention windows.
- [DEPLOYMENT.md](./DEPLOYMENT.md) — tier-specific observability infrastructure.
