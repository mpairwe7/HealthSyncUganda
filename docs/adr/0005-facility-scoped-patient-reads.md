# ADR 0005: Facility-scoped patient reads

- **Status:** Proposed
- **Date:** 2026-05-25
- **Closes residual risk:** [RR-02](../THREAT_MODEL.md#6-residual-risk-register)
- **Deciders:** Architecture Review Board + DPO (per [ADR 0000](./0000-governance.md))
- **Supersedes:** —

## Context

`GET /api/v1/patients/{id}` currently requires only authentication (any role) + the citizen-self check (`patients.py:118`). A worker at facility A can read any patient registered at facility B, by ID. The compensating controls today are the audit log entry and the cross-facility anomaly signal `AL-12` in [OBSERVABILITY.md](../OBSERVABILITY.md). DPPA s.10 (purpose specification) and the principle of least privilege both push for prevention, not detection alone.

Worker writes are already facility-scoped by the application (the create/encounter paths stamp `Principal.facility_id`). Reads are the asymmetry.

## Decision

A worker (or pharmacist) may read a `Patient` if **at least one** of the following holds at request time:

1. **Treatment relationship.** There is an `Encounter` with `facility_id = principal.facility_id` for the patient — current or historical.
2. **Explicit consent.** There is a non-revoked `Consent` row where:
   - `patient_id` matches, AND
   - `scope` ∈ {`share-with-facility:{principal.facility_id}`, `cross-facility-read`, `referral`}, AND
   - `revoked_at IS NULL` AND (`expires_at IS NULL` OR `expires_at > now()`).
3. **Role elevation.** `principal.role ∈ {district_admin, ministry_admin}`. District-admin reads are further bounded by `assigned_districts` (see [ADR 0007](./0007-district-scope-claim.md)).
4. **Emergency override.** `purpose = "emergency-care"` declared by the worker. Permitted, but:
   - Logged with `action="read-emergency"` (distinct from `action="read"`).
   - Triggers an out-of-band notification to the patient's home facility within 24 h.
   - Subject to a per-actor rate limit (max 5 emergency overrides per day) to deter abuse.

Citizens remain bound by the existing citizen-self rule. The current behaviour for `district_admin`+ is unchanged for routine reads (rule 3) but newly bounded by ADR 0007's district claim.

### Audit log basis

Every `read` row gains an `extra.access_basis` value identifying which rule applied:

```json
{"access_basis": "encounter-at-facility", "encounter_id": "01HV…"}
{"access_basis": "consent",                "consent_id":   "01HV…"}
{"access_basis": "role-elevated"}
{"access_basis": "emergency-override",      "notified":     true}
```

This lets the post-pilot audit answer "what fraction of cross-facility reads were emergency overrides?" without re-deriving from query joins.

## Rationale

- **Minimal latency cost.** One indexed query (`SELECT 1 FROM encounters WHERE patient_id=? AND facility_id=? LIMIT 1`) on the hot path — < 5 ms p95 in our benchmark shape.
- **Composable with existing consent model.** No new tables; `consents.scope` already accepts free-form strings. Two new well-known scope values plus the existing wildcard support are enough.
- **Emergency-override is real.** Pretending it isn't would push workers around the rule. Making it explicit, audit-distinct, rate-limited, and notification-triggering preserves the principle while accommodating reality.

## Alternatives considered

- **Pure consent-only model** (no implicit treatment relationship). Rejected: would require a worker to record a consent every time a patient walks in, which is paperwork-theatre. The `Encounter` itself is consent-equivalent for the facility that recorded it.
- **District-bounded reads** as the default for workers. Rejected: too narrow (referrals cross districts) and too wide (a worker at one HC III does not need to read another HC III's full patient roster).
- **Per-record ACL table.** Rejected: would require migration of every existing patient record and operational overhead at write time.

## Consequences

**Positive.**
- Closes RR-02 with a code-level guarantee, not a detection-only mitigation.
- Brings the read path in line with the write path (both facility-scoped).
- Improves audit-log informativeness via `access_basis`.

**Negative.**
- One additional indexed query per `Patient` read. Mitigated by the `encounters(patient_id, facility_id)` index (already present per [DATA_MODEL.md §4](../DATA_MODEL.md#4-index-strategy)).
- Workers at a new facility (no encounters yet) can't read incoming-referral patients without a consent row. The referral workflow becomes a *first-class* operation: a referring facility must grant `scope="referral"` consent that names the destination facility. This is correct behaviour but a UX shift.

## Implementation sketch

```python
# backend/app/api/v1/patients.py — replace ad-hoc check at line ~118

from app.core.access import (
    require_patient_read_access,
    AccessBasis,
)

@router.get("/{patient_id}", response_model=PatientOut)
async def get_patient(
    patient_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    purpose: str = Query("clinical-care"),
) -> PatientOut:
    p = await db.get(Patient, patient_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found")

    basis: AccessBasis = await require_patient_read_access(
        db, principal=principal, patient=p, purpose=purpose
    )

    action = "read-emergency" if basis.kind == "emergency-override" else "read"
    await record_access(
        db, principal=principal,
        resource_type="Patient", resource_id=p.id,
        action=action, purpose=purpose,
        extra=basis.audit_extra(),
        consent_id=basis.consent_id,
    )
    return _to_out(p)
```

```python
# backend/app/core/access.py — new module (sketch)

from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True)
class AccessBasis:
    kind: Literal["citizen-self", "encounter-at-facility", "consent",
                  "role-elevated", "emergency-override"]
    encounter_id: str | None = None
    consent_id: str | None = None

    def audit_extra(self) -> dict:
        return {
            "access_basis": self.kind,
            **({"encounter_id": self.encounter_id} if self.encounter_id else {}),
        }


async def require_patient_read_access(
    db: AsyncSession, *, principal: Principal, patient: Patient, purpose: str
) -> AccessBasis:
    if principal.role == "citizen":
        if principal.subject == patient.nin:
            return AccessBasis("citizen-self")
        raise HTTPException(403, "Not your record")

    if principal.is_at_least("district_admin"):
        # Bounded by ADR 0007 district claim — checked in the analytics layer
        # and again here when ADR 0007 lands.
        return AccessBasis("role-elevated")

    # worker / pharmacist — check encounter relationship first (cheapest)
    if principal.facility_id:
        enc = await db.scalar(
            select(Encounter.id)
            .where(
                Encounter.patient_id == patient.id,
                Encounter.facility_id == principal.facility_id,
            )
            .limit(1)
        )
        if enc:
            return AccessBasis("encounter-at-facility", encounter_id=enc)

        # Then consent
        consent_id = await db.scalar(
            select(Consent.id).where(
                Consent.patient_id == patient.id,
                Consent.revoked_at.is_(None),
                or_(Consent.expires_at.is_(None), Consent.expires_at > func.now()),
                Consent.scope.in_(_facility_consent_scopes(principal.facility_id)),
            ).limit(1)
        )
        if consent_id:
            return AccessBasis("consent", consent_id=consent_id)

    # Emergency override
    if purpose == "emergency-care":
        await _enforce_emergency_rate_limit(principal)        # Redis token bucket
        await _enqueue_home_facility_notification(db, patient, principal)
        return AccessBasis("emergency-override")

    raise HTTPException(403, "No facility relationship, consent, or override")


def _facility_consent_scopes(facility_id: str) -> list[str]:
    return [
        f"share-with-facility:{facility_id}",
        "cross-facility-read",
        "referral",
    ]
```

### Migration

1. Add an Alembic migration to populate `consents.scope` constants in the seed data; no schema change needed.
2. Backfill: for every patient currently visible cross-facility, the existing encounters table already establishes the relationship — no data migration needed.
3. Add the rate-limit Redis key `emergency-override:{actor_id}` with daily TTL.
4. Add the notification outbox (uses the same Redis-list pattern as the DHIS2 outbox).
5. Update [ACCESS_CONTROL.md §3](../ACCESS_CONTROL.md#3-facility-scoping) — remove the "current gap (tracked)" paragraph.
6. Update [THREAT_MODEL.md §6](../THREAT_MODEL.md#6-residual-risk-register) — change RR-02 status to "closed pre-pilot, ADR 0005".

### Rollout

- **Phase 1 (pre-pilot, dev/staging).** Deploy behind a feature flag `enforce_facility_scope_reads=false` by default; observe the audit log for cross-facility reads that *would* have been denied. Calibrate thresholds.
- **Phase 2 (pre-pilot, production).** Flip the flag to `true`. Workers see a structured 403 with a `referral` instruction; the citizen portal copy explains how to grant consent.
- **Phase 3 (during pilot).** Remove the flag.

## References

- [THREAT_MODEL.md §6 RR-02](../THREAT_MODEL.md#6-residual-risk-register), [§7 closure plan](../THREAT_MODEL.md#7-roadmap-closure-plan).
- [ACCESS_CONTROL.md §3 Facility scoping](../ACCESS_CONTROL.md#3-facility-scoping).
- [DATA_MODEL.md §3.10 consents](../DATA_MODEL.md#310-consents--explicit-granular-revocable).
- DPPA 2019 s.10 (purpose specification), s.22 (consent), s.27 (right to object).
