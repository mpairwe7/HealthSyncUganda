# ADR 0007: District scope claim for district_admin

- **Status:** Proposed
- **Date:** 2026-05-25
- **Closes residual risk:** [RR-09](../THREAT_MODEL.md#6-residual-risk-register)
- **Deciders:** Architecture Review Board + DPO

## Context

`district_admin` is privileged for the `/api/v1/analytics/*` endpoints and (post-[ADR 0005](./0005-facility-scoped-patient-reads.md)) for cross-facility `Patient` reads within their assigned district. The role hierarchy in `app/core/security.py` knows that a district_admin sits above `pharmacist` and below `ministry_admin`, but the *which district* dimension is implicit. Today a district_admin user can read aggregates and patient records from any district — defeating the principle of district-bounded administration that the role exists to express.

## Decision

Extend the `Principal` to carry **the set of districts the actor is administratively responsible for**, source it from a new JWT claim, and enforce district bounding at every endpoint that consumes the claim.

### JWT claim

A new claim `assigned_districts` carries a list of district names (strings, matching `facilities.district` and `patients.district`).

```json
{
  "sub": "district.kampala",
  "role": "district_admin",
  "facility_id": null,
  "assigned_districts": ["Kampala", "Wakiso"],
  "name": "District Health Officer — Kampala",
  "iat": 1748169600,
  "exp": 1748198400,
  "iss": "healthsync-uganda"
}
```

- Empty or absent for `citizen`, `worker`, `pharmacist`.
- For `ministry_admin`, the claim is the literal `["*"]` (national scope).
- For `district_admin`, exactly one or more named districts.

### Principal extension

```python
@dataclass(frozen=True, slots=True)
class Principal:
    subject: str
    role: Role
    facility_id: str | None = None
    name: str | None = None
    assigned_districts: tuple[str, ...] = ()      # NEW

    def can_access_district(self, district: str) -> bool:
        if self.role == "ministry_admin":
            return True
        if self.role == "district_admin":
            return district in self.assigned_districts
        # workers/pharmacists are bounded by facility_id, not district claim
        return self.role in {"worker", "pharmacist"} or self.role == "citizen"
```

### Endpoint enforcement

**Analytics:**

```python
# backend/app/api/v1/analytics.py — every endpoint
@router.get("/encounters-by-district", ...)
async def encounters_by_district(
    principal: Annotated[Principal, Depends(require_role("district_admin"))],
    ...
) -> Page[EncountersByDistrict]:
    rows = await db.execute(stmt)
    if principal.role == "district_admin":
        rows = [r for r in rows if r.district in principal.assigned_districts]
    return ...
```

**Patient cross-facility reads (composes with [ADR 0005](./0005-facility-scoped-patient-reads.md)):**

```python
# In require_patient_read_access (ADR 0005 sketch), the "role-elevated" branch:
if principal.role == "district_admin":
    if not principal.can_access_district(patient.district):
        raise HTTPException(403, "Patient is outside your assigned districts")
    return AccessBasis("role-elevated")
if principal.role == "ministry_admin":
    return AccessBasis("role-elevated")
```

### Issuance

District-admin tokens are issued by the staff login flow. Until ADR 0006 (planned, pre-national) (IdP) lands, the claim source is the `users` table augmented with a new `user_district_assignments` table:

```sql
CREATE TABLE user_district_assignments (
    user_id     varchar(26)  NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    district    varchar(80)  NOT NULL,
    assigned_at timestamptz  NOT NULL DEFAULT now(),
    assigned_by varchar(80)  NOT NULL,
    PRIMARY KEY (user_id, district)
);
CREATE INDEX ix_uda_district ON user_district_assignments (district);
```

`issue_token` reads from this table for `district_admin` users and embeds the list in the JWT payload. For `ministry_admin`, it emits `["*"]`.

When ADR 0006 (planned, pre-national) lands, the same claim is sourced from the IdP's group/role mapping (Keycloak realm role mapper) and the `user_district_assignments` table is retired.

### Audit log

Audit rows from district_admin reads gain `extra.assigned_districts = principal.assigned_districts` for traceability. Cross-district *attempts* (denied 403s) emit an audit row with `action="read-denied"` and `extra.reason="outside-district"` — these feed alert `AL-12` directly.

## Rationale

- **Aligns role authority with administrative reality.** A district health officer in Kampala has authority in Kampala, not in Mbarara.
- **Composes cleanly with ADR 0005.** The two ADRs together close RR-02 and RR-09 with overlapping but distinct concerns.
- **JWT-level enforcement is hard to bypass.** The claim is signed; tampering invalidates the token. The endpoint-level check is the defence in depth.

## Alternatives considered

- **Per-request district query parameter** (e.g. `?district=Kampala`). Rejected: requires every consumer to handle 403s; doesn't constrain *all* districts the admin queries; trivial to bypass by enumerating districts.
- **No claim — server-side lookup at every request.** Rejected: an extra DB query per analytics call; the claim is exactly the right place for an identity attribute.

## Consequences

**Positive.**
- Closes RR-09.
- Makes the audit trail richer (denied attempts are first-class).
- Sets up cleanly for ADR 0006 (planned, pre-national) — the IdP becomes the canonical source of the claim.

**Negative.**
- Issuing a new district_admin requires populating the assignment table (admin operation; covered by a small admin endpoint).
- A user whose assignments change must re-authenticate to get a fresh token (consistent with our no-refresh-tokens policy).

## Implementation sketch

```python
# backend/app/core/security.py — issue_token

def issue_token(principal: Principal, *, ttl: timedelta = timedelta(hours=8)) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": principal.subject,
        "role": principal.role,
        "facility_id": principal.facility_id,
        "name": principal.name,
        "assigned_districts": list(principal.assigned_districts) or None,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
        "iss": settings.app_name,
    }
    return jwt.encode(payload, settings.secret_key.get_secret_value(), algorithm="HS256")


def _decode_token(token: str) -> Principal:
    # ... existing decode ...
    districts = claims.get("assigned_districts") or []
    return Principal(
        subject=claims["sub"],
        role=claims["role"],
        facility_id=claims.get("facility_id"),
        name=claims.get("name"),
        assigned_districts=tuple(districts) if districts != ["*"] else ("*",),
    )
```

### Migration

1. `0007_user_district_assignments.sql` Alembic migration adds the table.
2. Admin endpoint `POST /api/v1/admin/users/{id}/districts` (ministry_admin only) populates assignments.
3. Existing district_admin users in seed data + production are assigned via a one-off script `scripts/assign-default-districts.py`.
4. Token-issuance path reads the assignments table at login.
5. Analytics endpoints add the filter — behind the feature flag `enforce_district_claim=false` initially.
6. Audit-log enrichment: `record_access` already takes `extra`; the additional `assigned_districts` key is a no-op for older actors.

### Rollout

- **Phase 1 (pre-pilot, dev/staging).** Deploy the table, the issuance, the claim, the filter behind the flag. Observe audit log for cross-district reads that *would* be denied.
- **Phase 2 (pre-pilot, production).** Flip the flag on.
- **Phase 3 (during pilot).** Remove the flag.
- **Phase 4 (pre-national, ADR 0006).** Source the claim from Keycloak realm roles; retire `user_district_assignments`.

## References

- [THREAT_MODEL.md §6 RR-09](../THREAT_MODEL.md#6-residual-risk-register).
- [ACCESS_CONTROL.md §2](../ACCESS_CONTROL.md#2-role-to-endpoint-matrix).
- [OBSERVABILITY.md AL-12](../OBSERVABILITY.md#2-alert-catalogue).
- [ADR 0005 — Facility-scoped patient reads](./0005-facility-scoped-patient-reads.md) (composes with this ADR).
- ADR 0006 — Production IdP (planned for pre-national; future canonical source of the claim). Owner + target tracked under [THREAT_MODEL.md §7 RR-07](../THREAT_MODEL.md#7-roadmap-closure-plan).
