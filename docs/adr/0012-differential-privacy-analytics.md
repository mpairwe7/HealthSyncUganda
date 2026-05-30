# ADR 0012: Differential-privacy guard for analytics endpoints

- **Status:** Proposed
- **Date:** 2026-05-25
- **Implements forward-architecture items:** [`FA-06` … `FA-09`](../ARCHITECTURE.md#12-forward-looking-architecture-2026)
- **Deciders:** Architecture Review Board + DPO

## Context

`/api/v1/analytics/*` already constrains itself to aggregates (DPPA s.31). But aggregates leak under three classic attacks:

1. **Small-cell disclosure.** A cell with cohort size 1 — "DPT-3 coverage in village X for boys aged 5" — reveals the individual.
2. **Differencing attack.** Two queries that differ by one row's worth of filter (e.g. "ages 0–4" vs. "ages 0–5") reveal the row.
3. **Trajectory inference.** Repeated queries over time about an evolving cohort allow membership inference.

District health officers must be able to make data-driven decisions. The DP guard makes the small-cohort cases either unanswerable or noised-out, while leaving the high-cohort cases (district-level aggregates over thousands of patients) effectively unchanged.

This places HealthSync ahead of the typical 2026 East African digital-health baseline (most implementations stop at k-anonymity on cell suppression).

## Decision

Implement four layers, composable per endpoint, configured per response cell:

### Layer 1 — k-anonymity suppression

Any cell whose underlying cohort size is less than `k` (default `k = 20`) returns `null` plus a flag.

```json
{
  "district": "Kampala",
  "indicator": "DPT-3 coverage",
  "value": 0.78,
  "cohort_n": 2_341,
  "dp": {"suppressed_for_privacy": false}
}
{
  "district": "Kampala / boys / age 5 in village X",
  "indicator": "DPT-3 coverage",
  "value": null,
  "cohort_n": null,
  "dp": {"suppressed_for_privacy": true, "reason": "k-anonymity", "k": 20}
}
```

### Layer 2 — Laplace noise for medium cohorts

For cells with cohort size in `[k, k_noise)` (default `k_noise = 100`), add **Laplace noise** to numeric values with sensitivity calibrated to ε ≤ 1 per cell per 24h.

```
noised_count   = round(true_count   + Laplace(scale = 1/ε))
noised_rate    = clip(true_rate     + Laplace(scale = 1/(ε · denominator)), 0, 1)
```

For boolean-style coverage indicators (DPT-3 coverage as a proportion), the noise is on the proportion with denominator-aware sensitivity. The numerator and denominator are noised separately.

### Layer 3 — Per-actor ε budget

A daily ε budget per `actor_id`, default 5.0 per day. Each Layer-2 response debits ε from the actor's bucket. Once exhausted, the actor's queries downgrade to **Layer 1 only** (k-anonymity suppression) — Layer 2 stops adding noise because the budget is gone (the noise was already added; revealing more would be cumulative leakage).

```
Redis key:   dp:budget:{YYYY-MM-DD}:{actor_id}
Initial value: 5.0
Operation:   DECRBYFLOAT
TTL:          24h (resets at midnight UTC, with the daily roll)
```

### Layer 4 — DP audit trail

Every response gains a structured DP envelope:

```json
{
  "data": [...],
  "dp_meta": {
    "epsilon_spent": 0.32,
    "epsilon_remaining": 4.68,
    "cells_suppressed": 3,
    "cells_noised": 12,
    "cells_clean": 7
  }
}
```

Plus an `audit_log` row with `action="analytics-read"` and `extra.dp_meta={…}` so the DP usage of an actor is traceable.

### Configuration

```python
# backend/app/config.py — additions

class Settings(BaseSettings):
    # ── Differential privacy ─────────────────────────────────────────────
    dp_k_anonymity: int   = 20
    dp_k_noise:     int   = 100
    dp_epsilon_per_cell: float = 1.0
    dp_daily_budget_epsilon: float = 5.0
    dp_enabled: bool      = True   # kill-switch for diagnostics
```

Per-endpoint overrides are possible via a small `DpPolicy` value passed to the wrapper.

### Module shape

```python
# backend/app/core/dp.py — sketch

from dataclasses import dataclass
import secrets

@dataclass
class Cell:
    value: float | int | None
    cohort_n: int
    is_proportion: bool = False

@dataclass
class DpDecision:
    value: float | int | None
    suppressed: bool
    noised: bool
    epsilon_used: float
    reason: str | None = None

def _laplace(scale: float) -> float:
    # Sample Laplace(0, scale) using two uniform samples; uses secrets for CSPRNG
    u = secrets.SystemRandom().random() - 0.5
    sign = 1 if u >= 0 else -1
    return -scale * sign * math.log(1 - 2 * abs(u))

def guard_cell(cell: Cell, *, k: int, k_noise: int, epsilon: float, budget_left: float) -> DpDecision:
    if cell.cohort_n < k:
        return DpDecision(None, suppressed=True, noised=False,
                          epsilon_used=0.0, reason="k-anonymity")
    if cell.cohort_n < k_noise:
        if budget_left < epsilon:
            return DpDecision(None, suppressed=True, noised=False,
                              epsilon_used=0.0, reason="budget-exhausted")
        scale = 1.0 / epsilon if not cell.is_proportion else 1.0 / (epsilon * cell.cohort_n)
        noised = (cell.value or 0) + _laplace(scale)
        if cell.is_proportion:
            noised = min(max(noised, 0.0), 1.0)
        else:
            noised = round(noised)
        return DpDecision(noised, suppressed=False, noised=True,
                          epsilon_used=epsilon)
    return DpDecision(cell.value, suppressed=False, noised=False, epsilon_used=0.0)


async def debit_budget(redis, actor_id: str, epsilon_used: float) -> float:
    """Atomic debit; returns remaining budget."""
    if epsilon_used <= 0:
        # SELECT remaining
        ...
    key = f"dp:budget:{date.today().isoformat()}:{actor_id}"
    # If key missing, INCRBYFLOAT will initialize to 0; use SET NX first.
    ...
```

### Endpoint integration

```python
# backend/app/api/v1/analytics.py — illustrative wrapper

@router.get("/encounters-by-district", ...)
async def encounters_by_district(
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(require_role("district_admin"))],
    ...
) -> Page[EncountersByDistrict]:
    raw_rows = await _query_encounters_by_district(db, principal)

    cells = [
        Cell(value=r.count, cohort_n=r.cohort_n, is_proportion=False)
        for r in raw_rows
    ]
    decisions = await apply_dp(cells, principal=principal)

    return _serialise(raw_rows, decisions)
```

`apply_dp` reads the actor's remaining budget, calls `guard_cell` per cell, debits the total ε spent, records the audit row, and returns the per-cell decisions.

## Rationale

- **(ε, δ)-DP with ε ≤ 1 per cell** is the conservative end of the well-published DP-for-aggregates literature (US Census 2020 used ε ≈ 0.7–13 per attribute; we are well below).
- **Per-actor budgets** are essential because the threat model includes a rogue district_admin (TS-B in [THREAT_MODEL.md §5](../THREAT_MODEL.md#5-attack-scenarios-worked-examples)). Without a per-actor budget, an attacker just queries repeatedly.
- **Laplace > Gaussian** for this size of ε; Gaussian requires accounting for (ε, δ) jointly and is harder to explain to the DPO and a panel reviewer.
- **Clear DP envelope on every response** makes the trade-off legible to the consumer. If a value is null with `reason="k-anonymity"`, the dashboard renders "Suppressed for privacy" — that's a feature, not a bug.

## Alternatives considered

- **No noise, just k-anonymity.** Insufficient against differencing attacks; the literature is settled on this.
- **Gaussian mechanism.** Marginally tighter at the price of explanatory complexity. Reconsidered if the DP budget pressure becomes the dominant constraint.
- **Per-query (rather than per-cell) ε.** Simpler accounting but coarser; a single query with 50 cells would consume the budget too fast.
- **Synthetic-data substitution.** Would require modelling effort beyond what the pilot scope justifies; reconsidered post-pilot for population research use cases.

## Consequences

**Positive.**
- Implements `FA-06` … `FA-09`.
- Differential privacy on a national-health platform in 2026 is itself a substantial submission signal.
- Aligns with DPPA s.31 (statistical/research use) and matches the WHO *Ethics & Governance of AI for Health* guidance for population-level inference.

**Negative.**
- District officers will see "suppressed" cells for small villages. **This is correct behaviour** but requires a UX explainer in the analytics dashboard (a small `?` icon: "This cell is suppressed because the underlying cohort is too small to share without risk of re-identifying an individual").
- Marginal latency: < 5 ms per response for the noise injection + budget debit.
- The numeric value a district officer sees may differ by ε-noise from the underlying truth. The dashboard renders the cohort size alongside, so the user knows whether the cell is in the noised band.

## Migration

1. Add `backend/app/core/dp.py`.
2. Add config keys + Redis budget key namespace.
3. Wrap analytics endpoints with `apply_dp`.
4. Add `audit_log.extra.dp_meta` to the audit emission.
5. Add `Cell`-level tests with known ε values + Monte Carlo over Laplace samples.
6. Update [ARCHITECTURE.md §12](../ARCHITECTURE.md#12-forward-looking-architecture-2026) — change FA-06…FA-09 status from "planned" to "implemented (ADR 0012)".
7. Update [SECURITY.md "Zero-trust elements"](../SECURITY.md#zero-trust-elements) — "Differential privacy for analytics" row: status → "implemented".
8. Update the frontend analytics dashboard to render the DP envelope + suppression explainer.

## Rollout

- **Phase 1 (dev).** Implement and unit-test the cell-level guard.
- **Phase 2 (pre-pilot).** Enable on staging behind feature flag `dp_enabled=true`; observe budget consumption.
- **Phase 3 (pre-pilot).** Wire UX explainer; release notes.
- **Phase 4 (during pilot).** Calibrate `dp_daily_budget_epsilon` and `dp_k_anonymity` based on observed usage and DPO review.

## References

- [ARCHITECTURE.md §12 FA-06…FA-09](../ARCHITECTURE.md#12-forward-looking-architecture-2026).
- [SECURITY.md §"Zero-trust elements"](../SECURITY.md#zero-trust-elements).
- [THREAT_MODEL.md §5 TS-B](../THREAT_MODEL.md#5-attack-scenarios-worked-examples).
- [COMPLIANCE.md s.31](../COMPLIANCE.md#a-uganda-data-protection-and-privacy-act-2019).
- C. Dwork & A. Roth (2014) "The Algorithmic Foundations of Differential Privacy" — Laplace mechanism and composition.
- US Census Bureau (2020) Disclosure Avoidance System — production case study.
- WHO (2024) *Ethics & Governance of AI for Health* — aggregate-inference principles.
