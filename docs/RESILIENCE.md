# Resilience playbook

> "The system works when the network doesn't."

The patterns in [`backend/app/core/resilience.py`](../backend/app/core/resilience.py) and [`frontend/src/lib/offline`](../frontend/src/lib/offline) compose into a single guarantee: **no clinical work is lost, and no upstream outage cascades**.

This page is the field operator's reference for what those patterns do, how to tune them, and how to verify them under load.

## Circuit breakers

Three states: `closed → open → half_open`.

```python
from app.core.resilience import resilient

@resilient(breaker="nira", retry_attempts=4)
async def lookup_nin(nin: str) -> dict:
    ...
```

| Setting | Default | Where set |
|---|---|---|
| Failure threshold | 5 consecutive failures | `CIRCUIT_BREAKER_FAILURE_THRESHOLD` env |
| Recovery timeout | 30 seconds | `CIRCUIT_BREAKER_RECOVERY_TIMEOUT_SECONDS` env |
| Per-breaker override | constructor kwargs on `CircuitBreaker(name=, …)` | code |

State transitions emit OTel span events (`circuit.failure`, `circuit.opened`, `circuit.half_open`, `circuit.closed`) and structured logs at the appropriate level. Dashboards should chart **closed→open transitions per breaker per minute** — that's the leading indicator of upstream pain.

### Verifying the breaker

```bash
# Trip the dhis2 breaker on demand (demo-only endpoint)
curl -X POST http://localhost:8000/api/v1/interop/circuits/dhis2/trip \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# Inspect breaker state
curl http://localhost:8000/api/v1/interop/circuits \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

## Retry with backoff

Exponential backoff with full jitter, capped per attempt. Applied automatically by `@resilient` and the frontend's `apiRequest`.

| Setting | Default |
|---|---|
| Max attempts | 4 |
| Base delay | 200 ms |
| Cap per delay | 5,000 ms |
| Retry-only-on | network errors, 5xx, 408, 429 |
| Never-retry-on | `UpstreamUnavailable`, 4xx (except above) |

## Bulkhead

A bounded semaphore per upstream. The first 16 requests pass; subsequent requests fail fast with `BulkheadFull` rather than queue and starve the FastAPI worker.

```python
bh = get_bulkhead("nira", max_concurrent=8)
async with bh:
    ...
```

Sizing rule of thumb: `max_concurrent ≤ p99_latency_seconds × upstream_qps`.

## Idempotency

The middleware honours `Idempotency-Key` for all unsafe methods. Cached responses are stored in Redis for 24 hours, keyed by `(method, path, key)`. Replays carry an `X-Idempotent-Replay: true` response header — useful for distinguishing real new writes from retries in logs.

## Frontend offline queue

- Mutations that fail because `navigator.onLine === false` are pushed onto an **IndexedDB FIFO** with the full request descriptor.
- The drainer wakes on `online` events and on a 30-second pulse, replaying entries.
- Each entry has an **idempotency key** generated client-side. The server dedupes if the same key is replayed.
- **4xx errors** mark the entry as *permanently failed* — surfaced in the sync drawer for human review rather than retried forever.

## DHIS2 outbox

Aggregated tally pushes that fail land in a Redis list (`dhis2:pending`). The next successful client call drains them; the admin endpoint `POST /api/v1/interop/dhis2/drain-queue` does it on demand; a cron / Arq worker should do it in production.

## Stale-while-revalidate

Frontend GETs go through TanStack Query with:

- `staleTime: 60s`
- `gcTime: 7 days` (persisted to IndexedDB)
- `networkMode: "offlineFirst"`

The service worker doubles up: every `GET /api/...` or `GET /fhir/...` is stored and served when fetch fails.

## Graceful degradation by feature

| Feature | Network healthy | Network degraded |
|---|---|---|
| Citizen identity lookup | Live NIRA verify | Cached NIN result |
| Encounter recording | Live POST | Queued in IndexedDB |
| Stock dashboards | Fresh query | Last cached response |
| DHIS2 tally push | Live | Queued in Redis |
| Analytics aggregates | Recomputed | Last 60s cache |
| Patient search | Live | Persisted query cache (filtered) |

## Load-test recipe

```bash
# requires `vegeta` or `k6`
echo "GET http://localhost:8000/api/v1/patients?page=1" | vegeta attack -duration=30s -rate=200 | vegeta report
```

p95 budget for the prototype on a single replica: **< 80 ms** at 200 req/s for `/api/v1/patients`.

## Audit your resilience posture

A 5-minute check before any demo or pilot:

- [ ] `curl /healthz` returns `ok` and `curl /readyz` returns `ready`.
- [ ] `curl /api/v1/interop/circuits` shows all breakers `closed`.
- [ ] `redis-cli llen dhis2:pending` is 0.
- [ ] Frontend sync indicator shows "Online · 0 pending".
- [ ] `pg_dump --schema-only` of `audit_log` shows the `INSERT`-only role grant (production only).
