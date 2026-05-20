# ADR 0002 — Resilience via per-dependency circuit breakers

- **Status**: Accepted
- **Date**: 2026-04-22
- **Decision-makers**: Backend lead, SRE lead
- **Consulted**: Ministry network engineering team

## Context

HealthSync depends on at least four downstream systems, each with its own
reliability profile:

| Dependency | Typical latency | Observed downtime / month | Failure mode |
| ---------- | ---------------- | -------------------------- | -------------- |
| NIRA NIN verification | 300-2000 ms     | 1-4 h                       | 5xx, timeouts |
| DHIS2 push       | 500-1500 ms     | 30 min-2 h                  | 5xx, malformed JSON |
| Redis (cache, idempotency) | < 5 ms | < 5 min                    | connection refused |
| Postgres         | < 20 ms          | < 5 min                    | connection pool exhaustion |

If any one of these fails the wrong way, the API becomes unusable for the
others. We measured this empirically in Q1 2026: a DHIS2 outage drove the
entire `/api/v1/patients` p95 from 80 ms to 9 s because every login spent its
budget waiting for an unrelated DHIS2 sync.

## Decision

We isolate every external dependency behind a `@resilient(...)` decorator that
combines:

1. **Bulkhead** — a per-dependency semaphore caps concurrency so a slow
   dependency cannot exhaust the FastAPI worker pool.
2. **Timeout** — every call has a finite deadline, defaulting to 5 s.
3. **Circuit breaker** — after N consecutive failures the breaker trips
   *open* and short-circuits subsequent calls for a configurable cooldown
   window. Half-open probing decides when to close.
4. **Retry** — exponential backoff with jitter, **only** on idempotent calls,
   capped at 3 attempts.

The decorator emits OpenTelemetry spans and Prometheus counters so we can see
breaker state from Grafana without redeploying.

State is held **in-process** (no shared store). Each backend replica observes
the dependency independently — we accept that as the price of zero coordination
cost. A single tripped replica recovers in tens of seconds.

## Consequences

**Positive**

- A single downstream outage degrades only the feature that needs it. The
  ministry analytics page can still render even if DHIS2 is down (cached
  values served with a "stale" banner).
- We can simulate dependency failure in the demo by flipping an env var — see
  `docs/DEMO_SCRIPT.md` step 9.
- Breaker metrics drive the operations runbook (`docs/RUNBOOK.md`).

**Negative**

- A trip on one replica does not propagate to its peers. Under heavy load
  this can produce mixed behaviour (some requests fast-fail, others wait).
  Mitigation: shared breaker state via Redis is on the roadmap (see ADR 0002
  follow-up).
- We must keep the retry policy honest — retrying non-idempotent writes is a
  patient-safety bug. We enforce this via the `idempotent=False` flag on the
  decorator.

## Alternatives considered

- **Service mesh-level breakers (Envoy/Istio)** — too much operational
  overhead for the pilot scale. Revisit at national rollout.
- **No breakers, generous timeouts** — fails for the reason described in
  Context.
- **Bulkhead only** — preserves the worker pool but still blocks each in-
  flight request until it times out. Breakers fail fast, which is what users
  need.

## How we will know if this was wrong

- p95 latency on `/api/v1/patients` exceeds 250 ms during a planned DHIS2
  outage (signal: isolation isn't working).
- Breaker oscillation rate > 5 trips/hour on any dependency in steady state
  (signal: thresholds wrong, or the dependency is unsuited to retry).
- Patient-safety incidents traced to a duplicate write caused by retry
  (signal: idempotency contract broken).

## Links

- Implementation — `backend/app/core/resilience.py`
- Runbook — `docs/RUNBOOK.md` § "Breaker tripped"
- Grafana board — `infra/grafana/dashboards/resilience.json`
