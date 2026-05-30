# ADR 0009: Field-level encryption for special-category PHI

- **Status:** Proposed
- **Date:** 2026-05-25
- **Closes residual gap:** "Field-level encryption for HIV / mental health / GBV" from [SECURITY.md §"What is *not* in this prototype"](../SECURITY.md) — moved from roadmap into pre-pilot scope.
- **Deciders:** Architecture Review Board + DPO

## Context

DPPA 2019 s.30 calls out special-category data for stricter controls. Within clinical observations, certain codes carry materially higher sensitivity than others: HIV status, mental health diagnoses, sexual and reproductive health, gender-based violence (GBV), abortion. Even authorised clinicians should access these only with declared clinical justification — and the data should be **unreadable to anyone with database-only access** (DBA performing routine maintenance, backup operator restoring to a scratch instance, an attacker who exfiltrates a `pg_dump`).

The current model encrypts at-rest at the volume level only (cloud-provider KMS for the backup tarball; nothing inside the database itself). That protects against tape theft; it does not protect against insider misuse, lateral DB access, or a compromised replica.

## Decision

Implement **envelope encryption** at the application tier for designated high-sensitivity `Observation` fields and for new tables for HIV status, mental health, and GBV when those are added.

### Encryption design

- **Algorithm:** AES-256-GCM (authenticated; tamper-evident).
- **Key hierarchy:**
  - **DEK (data encryption key)** — 256-bit, randomly generated per row, stored alongside the ciphertext, itself wrapped by the KEK.
  - **KEK (key encryption key)** — managed by the deployment-environment KMS (AWS KMS, GCP CMEK, NITA-U Vault transit). Rotated annually or on incident.
- **Wrapped DEK storage:** in a sidecar column `value_dek_wrapped` per encrypted field. Each row has its own DEK; compromise of one row does not compromise others.
- **Key identifier (`kid`):** every encrypted cell carries the KEK `kid` that wrapped its DEK. Reads dispatch to the right KEK; old `kid`s remain readable after rotation; new writes use the latest `kid`.
- **Nonce:** 96-bit random per encryption; stored with the ciphertext.
- **Additional Authenticated Data (AAD):** `f"{observation_id}|{column_name}"` is bound into GCM. A row that gets copied to a different `observation_id` fails to decrypt — defends against record-level swapping attacks.

### Schema

For the `observations` table — additive, not breaking:

```sql
ALTER TABLE observations
    ADD COLUMN value_ciphertext  bytea,        -- AES-GCM ciphertext + auth tag
    ADD COLUMN value_nonce       bytea,        -- 12-byte GCM nonce
    ADD COLUMN value_dek_wrapped bytea,        -- KEK-wrapped DEK
    ADD COLUMN value_kek_kid     varchar(80),  -- KEK key id used to wrap
    ADD COLUMN value_classification varchar(20); -- e.g. "sensitive-hiv", "sensitive-mh"

-- The legacy plaintext columns (value_quantity, value_unit, value_string)
-- remain NULLable. For sensitive rows they are NULL; for non-sensitive rows
-- the new columns are NULL. Exactly one side is populated per row.
```

### Sensitivity classification

A new module `backend/app/core/sensitive_codes.py` declares the codes that *must* be encrypted. Examples (illustrative — the real list is maintained jointly with the clinical advisor):

```python
SENSITIVE_CODES: dict[tuple[str, str], str] = {
    # (code_system, code): classification
    ("http://loinc.org",   "75622-1"): "sensitive-hiv",   # HIV-1 RNA
    ("http://loinc.org",   "31201-7"): "sensitive-hiv",   # HIV-1 Ab
    ("http://snomed.info/sct", "165816005"): "sensitive-hiv",
    ("http://snomed.info/sct", "35489007"):  "sensitive-mh",  # Depressive disorder
    ("http://snomed.info/sct", "95930005"):  "sensitive-gbv", # Sexual abuse
    # ... maintained by the clinical advisor
}
```

The write path inspects `(code_system, code)`; if it matches, the value is encrypted and the plaintext columns stay NULL. The read path is symmetric.

### Read-path policy

Reading an encrypted observation requires **all** of:

1. `principal.role` ∈ {`worker`, `pharmacist`, `district_admin`, `ministry_admin`} — citizens read their own non-encrypted observations via the standard path; sensitive observations require an explicit citizen-self code path (a separate rule).
2. `purpose` declared and non-empty (already required by the audit layer).
3. A *separate* audit row is written with `action="phi-sensitive-read"` and `extra.classification=value_classification`. The `AL-13` bulk-read alert in [OBSERVABILITY.md](../OBSERVABILITY.md#2-alert-catalogue) uses this distinct action as a higher-sensitivity signal.

### Crypto module

```python
# backend/app/core/crypto.py  (sketch)

from dataclasses import dataclass
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os

@dataclass(frozen=True, slots=True)
class EncryptedCell:
    ciphertext: bytes
    nonce: bytes
    dek_wrapped: bytes
    kek_kid: str


class FieldCipher:
    """AES-GCM envelope encryption with KMS-backed KEK.

    KMS interface is pluggable: AwsKmsClient, GcpKmsClient, VaultTransitClient.
    In tests, an InMemoryKmsClient with a fixed KEK is sufficient.
    """

    def __init__(self, kms: KmsClient) -> None:
        self._kms = kms

    async def encrypt(self, plaintext: bytes, *, aad: bytes) -> EncryptedCell:
        dek = AESGCM.generate_key(bit_length=256)
        nonce = os.urandom(12)
        ciphertext = AESGCM(dek).encrypt(nonce, plaintext, aad)
        wrapped, kid = await self._kms.wrap(dek)
        return EncryptedCell(ciphertext, nonce, wrapped, kid)

    async def decrypt(self, cell: EncryptedCell, *, aad: bytes) -> bytes:
        dek = await self._kms.unwrap(cell.dek_wrapped, kid=cell.kek_kid)
        return AESGCM(dek).decrypt(cell.nonce, cell.ciphertext, aad)
```

The KMS interface is intentionally narrow (`wrap(dek) -> (bytes, kid)`, `unwrap(wrapped, kid) -> bytes`). Three implementations land at the same time:

| Implementation        | Use                          |
| --------------------- | ---------------------------- |
| `InMemoryKmsClient`    | Tests; laptop demo            |
| `VaultTransitKmsClient` | Pilot, regional (NITA-U Vault) |
| `AwsKmsClient` / `GcpKmsClient` | National (cloud-tier deployments) |

### Observation marshalling

```python
# backend/app/db/models/encounter.py — Observation (illustrative addition)

class Observation(Base, IdMixin, TimestampMixin):
    # ... existing columns ...
    value_ciphertext:   Mapped[bytes | None]  = mapped_column(LargeBinary)
    value_nonce:        Mapped[bytes | None]  = mapped_column(LargeBinary)
    value_dek_wrapped:  Mapped[bytes | None]  = mapped_column(LargeBinary)
    value_kek_kid:      Mapped[str  | None]   = mapped_column(String(80))
    value_classification: Mapped[str | None]  = mapped_column(String(20))
```

```python
# backend/app/api/v1/encounters.py — at write time

cipher = get_field_cipher()  # singleton, configured per deployment
classification = classify(observation.code_system, observation.code)
if classification:
    plain = (observation.value_string or str(observation.value_quantity or "")).encode()
    aad   = f"{obs_id}|value".encode()
    cell  = await cipher.encrypt(plain, aad=aad)
    obs.value_ciphertext   = cell.ciphertext
    obs.value_nonce        = cell.nonce
    obs.value_dek_wrapped  = cell.dek_wrapped
    obs.value_kek_kid      = cell.kek_kid
    obs.value_classification = classification
    obs.value_string = obs.value_quantity = obs.value_unit = None
else:
    # Plaintext path — unchanged
    ...
```

```python
# At read time, *only* when caller is authorised AND purpose is declared

if obs.value_classification:
    await audit.record_access(
        db, principal=principal,
        resource_type="Observation", resource_id=obs.id,
        action="phi-sensitive-read", purpose=purpose,
        extra={"classification": obs.value_classification},
    )
    plain = await cipher.decrypt(
        EncryptedCell(obs.value_ciphertext, obs.value_nonce,
                      obs.value_dek_wrapped, obs.value_kek_kid),
        aad=f"{obs.id}|value".encode(),
    )
    return plain.decode()
```

## Rationale

- **Envelope encryption is the standard pattern** for production health records (HIPAA hosting examples, NHS England, Norway helseplattformen). Per-row DEKs prevent a single-key compromise from yielding bulk plaintext.
- **AES-GCM** is FIPS-validated and authenticated — tampering with the ciphertext column produces a decryption failure rather than wrong plaintext.
- **AAD bound to `(observation_id, column_name)`** is a quiet but important defence: an attacker who can move bytes between rows in the DB cannot cause a row to decrypt under a different identity.
- **KMS-backed KEK** keeps the master key out of the application's environment and out of any DB dump.
- **`value_classification` column** makes the encrypted set queryable for audit (e.g. "how many HIV observations were created in District X this month?") without decrypting.

## Alternatives considered

- **pgcrypto symmetric encryption.** Rejected: the key sits in the application or — worse — in the DB. Defeats the purpose of protecting against DB-tier access.
- **Postgres TDE.** Useful for at-rest disk encryption but does *not* protect against an authenticated DB user reading rows.
- **Encrypt every observation, not just sensitive ones.** Rejected for now: index-supported analytics on common observations (BP, weight) would require homomorphic encryption or queryable encryption schemes that are not field-mature in 2026. Sensitive observations rarely participate in aggregate analytics — they are read individually by a clinician.
- **Application-tier Fernet** (mentioned in current settings.py). Fernet is fine for opaque blobs but Fernet's key rotation story is weaker than KMS-managed KEK with per-row DEKs.

## Consequences

**Positive.**
- Closes the "field-level encryption" line item in [SECURITY.md §"What is *not* in this prototype"](../SECURITY.md).
- Provides defence-in-depth against DB-tier compromise.
- Aligned with DPPA s.30 ("processing of special-category data") and ISO 27799.

**Negative.**
- Read latency on sensitive observations gets ~5–15 ms for the KMS unwrap (cached per-session reduces this to first-read-per-DEK). Acceptable for the clinical-care hot path where sensitive observations are read rarely.
- Encrypted observations cannot be searched by value at the DB layer. The clinical model does not require this; if it ever does, a deterministic-encryption side index would be the answer (separate ADR).
- Backups containing encrypted columns are useless without the KMS — desirable property, but it must be reflected in [BACKUP_RESTORE.md](../BACKUP_RESTORE.md) restore procedure (KMS must be accessible to the restore target).

## Migration

1. **`0009_phi_field_encryption.sql`** — adds the new columns; no backfill required (legacy rows remain plaintext until they are rewritten or migrated by a one-off job).
2. **`backend/app/core/crypto.py`** — new module + three KMS-client impls.
3. **`backend/app/core/sensitive_codes.py`** — classification table; maintained jointly with the clinical advisor.
4. **Migration of existing observations:** a one-off script `scripts/encrypt-sensitive-observations.py` scans `observations` for rows matching the classification set and re-writes them with the new columns populated. Idempotent. Runs in a controlled maintenance window.
5. **Update [DATA_MODEL.md §3.5](../DATA_MODEL.md#35-observations--vitals-labs-immunisations)** — add the new columns + classification semantics.
6. **Update [THREAT_MODEL.md §4 A-1](../THREAT_MODEL.md#4-stride-per-asset)** — Patient PHI [I]: lateral SQL/DB read no longer yields plaintext for sensitive rows.
7. **Update [SECURITY.md "Data at rest"](../SECURITY.md)** — promote field-level encryption from "follow-up" to implemented for sensitive observations.

## Rollout

- **Phase 1 (pre-pilot, dev/staging).** Encryption on writes for sensitive codes; decryption on reads; tests against a known plaintext fixture.
- **Phase 2 (pre-pilot, production).** Backfill via `scripts/encrypt-sensitive-observations.py` during a maintenance window.
- **Phase 3 (during pilot).** Monitor `phi-sensitive-read` audit volume; calibrate the alert thresholds.
- **Phase 4 (pre-national).** Add `sensitive_codes` reload-without-restart (clinical advisor may want to add codes mid-cycle).

## References

- [SECURITY.md §"Data at rest"](../SECURITY.md), §"What is *not* in this prototype".
- [DATA_MODEL.md §3.5 observations](../DATA_MODEL.md#35-observations--vitals-labs-immunisations).
- [THREAT_MODEL.md §3 A-1](../THREAT_MODEL.md#3-assets).
- DPPA 2019 s.30 (special-category data); ISO 27799 (health-informatics security).
- WHO/HRP HIV/STI guidelines on data handling; Africa CDC HIV data protection framework.
- NIST SP 800-38D (GCM mode); NIST SP 800-57 (key management).
