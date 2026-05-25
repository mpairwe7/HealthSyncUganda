# ADR 0013: Shared circuit-breaker and bulkhead state via Redis

- **Status:** Proposed
- **Date:** 2026-05-25
- **Targets gap:** RUNBOOK [RB-02](../RUNBOOK.md#rb-02--circuit-breaker-stuck-open) note 2 ("replicas observe the breaker independently") — accepted in [ADR 0002](./0002-resilience-circuit-breakers.md) but increasingly costly as replicas grow.
- **Deciders:** Architecture Review Board

## Context

The current `CircuitBreaker` and `Bulkhead` in `backend/app/core/resilience.py` are **process-local**. Each FastAPI replica has its own breaker state. This was a deliberate choice (per [ADR 0002](./0002-resilience-circuit-breakers.md)): in-process breakers are simpler, faster, and survive Redis outages. The trade-off was acknowledged in [RUNBOOK.md RB-02 note 2](../RUNBOOK.md#rb-02--circuit-breaker-stuck-open): one replica may show `open` while another shows `closed`.

At pilot scale (2 replicas) this is fine. At regional scale (4 replicas) it's noisy. At national scale (12 replicas), 12 replicas independently probing a flaky DHIS2 endpoint means **12× the upstream load** during a partial outage — exactly when the upstream is most fragile.

The same applies to bulkheads: 12 replicas × 16 slots = 192 concurrent calls against an upstream that might only support 32.

## Decision

Add an **optional Redis-coordinated layer** on top of the existing per-process breakers and bulkheads. The per-process layer remains the primary defence; the Redis layer is a coordination signal that prevents the herd effect.

### Coordination, not replacement

The per-process breaker still trips on local failures (fast). The Redis layer is consulted only at state transitions:

```
┌─ FastAPI replica ──────────────────────────────────────────────┐
│                                                                │
│  call ──► CircuitBreaker (local)                               │
│             │                                                  │
│             ├── if local-OPEN: short-circuit (unchanged)       │
│             ├── if local-CLOSED:                               │
│             │     check Redis hint:                            │
│             │       if Redis says >N replicas reporting failures  │
│             │       → treat as half-open (probe sparingly)     │
│             │       else → proceed                             │
│             ▼                                                  │
│           upstream call                                         │
│             │                                                  │
│             └── on failure: incr Redis counter                 │
│             └── on success: optionally decay Redis counter      │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### Redis schema

| Key                                  | Type       | TTL  | Semantic                                                                                |
| ------------------------------------ | ---------- | ---- | --------------------------------------------------------------------------------------- |
| `breaker:{name}:failures:{window}`   | counter    | 60s  | Failures across all replicas in the current 1-minute window.                            |
| `breaker:{name}:probes`              | sorted-set | 60s  | Replica IDs that have probed in half-open state, with timestamps. Cap at N=1.            |
| `bulkhead:{name}:inflight`           | counter    | none | Cluster-wide in-flight count. `INCR` on enter, `DECR` on exit.                          |
| `bulkhead:{name}:max`                | integer    | none | Cluster-wide cap, set by ops.                                                           |

### Behaviour

**Coordinated probe.** In half-open, exactly one replica probes at a time. A replica that wants to probe `ZADD breaker:{name}:probes {ts} {replica_id} NX` with a 30s expiry; only the winner proceeds. Others stay open.

**Coordinated bulkhead.** A replica that wants to enter the bulkhead `INCR bulkhead:{name}:inflight`; if the result exceeds `bulkhead:{name}:max`, it `DECR`s and raises `BulkheadFullError`. On exit, `DECR`. Local semaphore remains as the inner ring.

**Graceful degradation.** If Redis is unreachable, the coordination layer is skipped and we fall back to per-process behaviour (today's exact semantics). The breaker never gets *less* protective for Redis failing.

### Configuration

```python
# backend/app/config.py — additions

class Settings(BaseSettings):
    # ── Resilience coordination ──────────────────────────────────────────
    breaker_coordination_enabled: bool = True
    breaker_coordination_window_seconds: int = 60
    bulkhead_coordination_enabled: bool = True
```

### Module shape

```python
# backend/app/core/resilience.py — additions (illustrative)

@dataclass
class CircuitBreaker:
    # ... existing fields ...
    coordinator: BreakerCoordinator | None = None  # Redis-backed; injected at boot

    async def _before(self) -> None:
        async with self._lock:
            if self._state is BreakerState.OPEN:
                # ... existing recovery check ...
                pass
        # New: even if local-CLOSED, ask the coordinator if there's a cluster signal.
        if self.coordinator and self._state is BreakerState.CLOSED:
            cluster_failures = await self.coordinator.cluster_failures(self.name)
            if cluster_failures > self.failure_threshold * REPLICAS_HINT:
                # Soft trip: don't fully open, but probe rarely
                if not await self.coordinator.try_acquire_probe(self.name):
                    raise UpstreamUnavailableError(
                        f"Circuit breaker '{self.name}' deferred to cluster probe"
                    )


class BreakerCoordinator:
    """Optional Redis-backed coordinator. Methods are best-effort; failures are logged and ignored."""

    def __init__(self, redis_url: str) -> None:
        self._redis = redis.from_url(redis_url)

    async def cluster_failures(self, name: str) -> int:
        try:
            v = await self._redis.get(f"breaker:{name}:failures:{_window()}")
            return int(v or 0)
        except Exception:
            return 0

    async def record_failure(self, name: str) -> None:
        try:
            key = f"breaker:{name}:failures:{_window()}"
            pipe = self._redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, 60)
            await pipe.execute()
        except Exception:
            pass

    async def try_acquire_probe(self, name: str) -> bool:
        try:
            return bool(await self._redis.set(
                f"breaker:{name}:probe-lock", _replica_id(),
                nx=True, ex=30,
            ))
        except Exception:
            return True  # Redis down → don't add extra friction
```

## Rationale

- **Coordination layered on top of (not replacing) local breakers.** Pilot single-replica deployments remain identical to today.
- **Best-effort, never blocking.** Redis failures must not cause platform-wide breaker storms. Every coordinator method is wrapped in try/except.
- **Probe acquisition via Redis `SET NX EX`** is the canonical single-leader pattern; correct under network partitions.
- **Window-bucketed counter** with TTL = window size gives natural memory cleanup without explicit reset jobs.

## Alternatives considered

- **Replace local breakers entirely with Redis-backed.** Rejected: every breaker decision becomes a network round-trip. Local breakers at sub-millisecond latency are the right primary defence.
- **Gossip-based coordination among replicas.** Rejected: adds a third dependency (libp2p, Serf, or similar). Redis already exists and is operationally familiar to NITA-U engineers.
- **Per-upstream max-concurrency at the upstream's API gateway.** Reasonable when feasible (e.g. NIRA OIDC quota), but we cannot control DHIS2's gateway.

## Consequences

**Positive.**
- During upstream outages, cluster sends ~1 probe per recovery window rather than 12.
- Bulkhead semantics become a hard cluster cap, not a per-replica one — preserves an upstream that has a hard concurrency limit.
- Operational visibility: a Grafana panel on `breaker:*:failures:*` shows the cluster's view in one place.

**Negative.**
- Small additional Redis QPS on each upstream call (1–2 reads on hot path; 1 write on failure).
- New configuration to reason about; default ON in production, OFF in tests.

## Implementation

1. Add `BreakerCoordinator` and `BulkheadCoordinator` classes; wire into `CircuitBreaker` and `Bulkhead`.
2. Pass the coordinator at boot when `breaker_coordination_enabled` and Redis is reachable.
3. Add cluster-wide metrics to the Grafana board "HealthSync — interop".
4. Add tests: stub Redis; assert cluster-failure threshold trips; assert probe acquisition is single-leader.
5. Update [ADR 0002](./0002-resilience-circuit-breakers.md) with a "**Superseded in part by ADR 0013**" note (the per-replica observation premise is retained as the *primary* mechanism, but the herd effect is no longer accepted).
6. Update [RUNBOOK.md RB-02 note 2](../RUNBOOK.md#rb-02--circuit-breaker-stuck-open) to reference the coordinated behaviour.

## Rollout

- **Phase 1 (dev/staging).** Implement; enable coordination; chaos test by killing the mock NIRA upstream and confirming a single probe occurs.
- **Phase 2 (pilot single-host).** No change in behaviour (one replica), but the code path runs and is exercised.
- **Phase 3 (regional).** Enable in production; observe.
- **Phase 4 (national).** Calibrate `REPLICAS_HINT` and the failure threshold based on observed traffic.

## References

- [ADR 0002 — Resilience: circuit breakers, bulkheads, fallbacks](./0002-resilience-circuit-breakers.md).
- [RUNBOOK.md RB-02](../RUNBOOK.md#rb-02--circuit-breaker-stuck-open).
- [OBSERVABILITY.md AL-05, AL-06](../OBSERVABILITY.md#2-alert-catalogue).
- M. Nygard (2018) *Release It! Second Edition* — circuit-breaker chapter, cluster-coordination considerations.
- Netflix Hystrix retrospective on per-process vs. shared state (the in-process-default convention).
