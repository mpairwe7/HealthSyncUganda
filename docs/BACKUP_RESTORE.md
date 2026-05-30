# Backup & Restore

**Audience:** SREs, DBAs, ministry IT staff operating a pilot or production installation.
**Source of truth for RPO/RTO:** [SCALABILITY.md §5](./SCALABILITY.md#5-operational-slos-post-pilot) and [OBSERVABILITY.md §1 SLO-9 / SLO-10](./OBSERVABILITY.md#1-service-level-objectives).
**Last reviewed:** 2026-05-25.

This document is the companion to [RUNBOOK.md RB-09 (Backup did not run)](./RUNBOOK.md#rb-09--backup-did-not-run) and [RB-10 (Database failover required)](./RUNBOOK.md#rb-10--database-failover-required). RB-09/RB-10 give you the on-the-night procedure; this document gives you the **design**, the **drill plan**, and the **restore-verification contract**.

---

## 1. Recovery objectives

These are operator-facing commitments, ratified in SCALABILITY.md and OBSERVABILITY.md:

| Objective | Pilot | Regional | National |
| --------- | ----- | -------- | -------- |
| **RPO** (max acceptable data loss) | 15 min | 5 min | 1 min |
| **RTO** (max acceptable downtime)  | 60 min | 30 min | 15 min |

The pilot RPO of 15 min is achievable with WAL archiving every 5 min and a 10-min processing tolerance. The pilot RTO of 60 min assumes a single primary + one streaming replica with manual promotion ([RB-10](./RUNBOOK.md#rb-10--database-failover-required)).

Production-tier deployments use Patroni or equivalent for automatic failover; the manual procedure documented here remains the fallback.

---

## 2. Backup taxonomy

| Class                 | Frequency       | Contents                                          | Retention                | Stored where                                  |
| --------------------- | --------------- | ------------------------------------------------- | ------------------------ | --------------------------------------------- |
| WAL archive            | Continuous (5-min push) | Postgres write-ahead log segments                | 7 days                   | Object store, encrypted (KMS/CMEK)            |
| Daily logical dump     | 24 h (off-peak)  | `pg_dump --format=custom` per database            | 35 days                  | Object store, encrypted                       |
| Weekly base backup     | 7 days           | `pg_basebackup` of the replica                    | 13 months                | Object store, encrypted; cold-tier after 35 d |
| Configuration snapshot | On every deploy  | `infra/postgres/init.sql`, Alembic head id, env-without-secrets | 13 months  | Object store + git tag                        |
| Evidence pack          | On IR activation | Targeted DB snapshot + Redis RDB + logs + traces  | Legal-hold (indefinite)  | Evidence bucket with restricted ACL           |

Backups are taken from the **read replica** to avoid disturbing primary write traffic. The application is paused only when explicitly required for a point-in-time consistency snapshot (rare).

At-rest encryption is via the deployment-environment KMS — AWS KMS, GCP CMEK, NITA-U Government Cloud KMS, or HashiCorp Vault transit — per [SECURITY.md](./SECURITY.md) "Data at rest". The KMS key for the **evidence bucket** is distinct from the regular-backup KMS key and rotates on a separate schedule.

---

## 3. What is *not* in the backups

Some state intentionally does not survive a restore:

- **Redis caches.** Idempotency keys, NIRA last-known-good cache, analytics cache, rate-limit token buckets. These are reconstructible (idempotency keys re-populate on retry; caches warm). A restore that loses Redis is fully recoverable.
- **DHIS2 outbox.** Persisted in Redis. Loss → outbox replays from the audit-log mirror (manual recovery path documented in [RB-03](./RUNBOOK.md#rb-03)).
- **In-flight HTTP requests.** TLS-terminated connections drop during failover. Clients retry with the same `Idempotency-Key` and the original result is replayed (SLO-12).
- **OpenTelemetry traces older than 30 days.** Not part of the DB; not restored from DB backups. See [OBSERVABILITY.md §3.2](./OBSERVABILITY.md#32-traces) retention.
- **Browser IndexedDB on worker / citizen devices.** Client-side; survives a server restore independently.

---

## 4. Backup procedure

The mature path is fully automated (cron + object-store lifecycle). The intermediate path (pilot) uses operator-run scripts. The minimum path (laptop) is just `pg_dump`.

### 4.1 Automated path (regional & national)

WAL archiving and base backups are configured in `infra/postgres/` and the deployment overlays. Operator action is limited to:

- Quarterly review of the backup-job logs.
- Quarterly review of the KMS key rotation schedule.
- The drill in §6 below.

### 4.2 Manual path (pilot)

> **Note:** `scripts/backup-now.sh` is referenced by RB-09 but is not yet present in the repository. The manual procedure below documents what that script will execute. When the script lands, this section will collapse to a one-liner.

Operator runs an on-demand backup:

```bash
# 1. Confirm the replica is healthy
scripts/preflight.sh

# 2. Take a logical dump from the replica
PGPASSWORD=$PG_REPLICA_PASS pg_dump \
  --host=$PG_REPLICA_HOST \
  --port=5432 \
  --username=healthsync_backup \
  --format=custom \
  --dbname=healthsync \
  --file=/tmp/healthsync-$(date -u +%FT%H%MZ).dump

# 3. Encrypt and upload
age -r $(cat /etc/healthsync/backup.age.pub) \
  -o /tmp/healthsync-$(date -u +%FT%H%MZ).dump.age \
  /tmp/healthsync-$(date -u +%FT%H%MZ).dump
aws s3 cp /tmp/healthsync-*.dump.age \
  s3://healthsync-backups-uganda/pilot/$(date -u +%F)/

# 4. Verify the checksum
aws s3api head-object --bucket healthsync-backups-uganda \
  --key pilot/$(date -u +%F)/healthsync-*.dump.age \
  | jq -r '.ChecksumSHA256'

# 5. Clean up the local file (the encrypted upload is the canonical artefact)
shred -u /tmp/healthsync-*.dump
```

Backup credentials (`healthsync_backup` DB user, age recipient public key, S3 IAM role) are vaulted in the deployment-environment secret store. The user is **read-only** on PHI tables; it can `pg_dump` but cannot mutate.

### 4.3 Laptop path

For development and demos:

```bash
make stack                          # Postgres in Docker
docker compose exec postgres pg_dump -U postgres healthsync > /tmp/healthsync.dump
```

No encryption required (development data is the seeded demo set, no real PHI). The seeded data set is reproducible from `app/seed/*` so backups are not load-bearing in this tier.

---

## 5. Restore procedure

Restore is **always** rehearsed against a **scratch instance** before being applied to production. Direct restore over a live primary is a SEV-1 operation requiring two-person approval.

### 5.1 Point-in-time recovery (PITR)

For "I need the database at exactly 14:32 UTC yesterday":

1. Provision a scratch Postgres instance, same major version as primary.
2. Restore the most recent base backup *before* the target timestamp:
   ```bash
   pg_basebackup --extract -D /var/lib/postgresql/restore /path/to/base.tar
   ```
3. Configure `recovery.target_time = '2026-05-24 14:32:00 UTC'` in `postgresql.auto.conf`.
4. Stage the WAL segments from the archive into `pg_wal/` of the restore directory.
5. Start Postgres; it replays WAL up to the target time and pauses.
6. Run the **post-restore verification** (§5.3).
7. If the verification passes, the IC + DPO decide whether to promote to primary (a destructive operation requiring [RB-10](./RUNBOOK.md#rb-10--database-failover-required) discipline).

### 5.2 Logical full restore

For "I need to bring up an independent copy of the database":

1. Provision a scratch Postgres instance.
2. Decrypt the dump:
   ```bash
   age --decrypt -i /etc/healthsync/backup.age.key \
     -o /tmp/healthsync.dump \
     /path/to/healthsync.dump.age
   ```
3. Restore:
   ```bash
   pg_restore --host=localhost --username=postgres --dbname=healthsync_scratch \
     --no-owner --no-acl --jobs=4 /tmp/healthsync.dump
   ```
4. Run the post-restore verification (§5.3).
5. Shred the decrypted dump.

### 5.3 Post-restore verification

After every restore — drill or real — these checks run before the restored database is trusted:

| Check | Command (logical) | Expected | If it fails |
| ----- | ----------------- | -------- | ----------- |
| Row counts match the pre-restore snapshot's manifest | `SELECT table_name, count(*) FROM …` per table | All tables match | Investigate; do not promote |
| Audit-log row count is monotonic vs. previous-day snapshot | `SELECT count(*) FROM audit_log` | ≥ previous count | Suspect tampering or partial restore |
| Supply ledger chain verifies | `GET /api/v1/supply/ledger/verify` against the restored DB | `{"ok": true}` | Treat as IR-21 against the historical state |
| Schema head matches the deployment's Alembic head | `alembic current` | Matches `git describe` for the deploy | Re-apply migrations carefully |
| Sample-patient round-trip | `GET /api/v1/patients/{id}` for a known seed patient | Returns expected record | Investigate index / data corruption |
| Audit log linkage (sample) | Pick 5 patients; assert ≥ 1 `audit_log` row for each | Holds | Investigate audit-write path |
| `consents` revoke timestamps are present where expected | Sample of known-revoked consents | `revoked_at` present | Investigate restore completeness |

A drill is not considered complete until every row above is green.

---

## 6. Quarterly restore drill

The drill is the only way to actually know the backups work. It is run quarterly and after any change to the backup pipeline.

**Scope:** one full logical restore + one PITR restore to a target 24 h in the past + the verification suite in §5.3.

**Evidence captured to:**

```
docs/incidents/restore-drill-YYYY-MM-DD.md   (created on first drill)
```

The drill report records:

- Drill date and operator(s).
- Source backup tarball IDs / WAL range used.
- Restore wall-clock time (validates RTO).
- Time of source backup vs. drill start (validates RPO).
- Each verification check from §5.3 with `pass` / `fail` + evidence.
- Any deviations from this document (and a PR to fix them).

The `docs/incidents/` directory is created on the first incident or first drill — there is no pre-created template subdirectory; the report is the seed.

---

## 7. Restoring evidence packs (post-incident)

After an incident, the evidence pack created in [IR-13](./INCIDENT_RESPONSE.md#ir-13) must remain restorable for forensic review by external parties (CERT-UG, MoH legal, PDPO).

- The evidence bucket retains snapshots under **legal hold** — no deletion until the DPO removes the hold.
- Read access is restricted to the DPO and the appointed forensics lead (engineering on-call rota is excluded by default).
- Restore of an evidence pack happens against a **fully isolated** scratch environment with no network egress, no production credentials, and no shared logging pipeline.
- The forensics environment is documented separately (out of scope for this document; tracked in `docs/incidents/_evidence-environment.md`, forthcoming).

---

## 8. Failover-related restore

When [RB-10](./RUNBOOK.md#rb-10--database-failover-required) is invoked, the restored state is the replica (already in sync). The "restore" step is:

1. Promote the replica (`pg_ctl promote`).
2. Run the post-restore verification (§5.3) against the newly promoted primary.
3. **Provision a new replica immediately.** Operating without a replica for more than 8 hours is itself a SEV-2.

The `scripts/db-promote-replica.sh` referenced by RB-10 is **not yet present in the repository**; the operator runs the manual sequence above until the script is added.

---

## 9. Known gaps

These are the items tracked for the production hardening pass beyond pilot:

- `scripts/backup-now.sh` and `scripts/db-promote-replica.sh` to be added (RB-09, RB-10 currently document the manual fallback).
- Automated quarterly-drill orchestration (a GitHub Actions workflow that spins up scratch infrastructure and runs the §5.3 verification).
- Continuous restore validation (a "restored shadow" replica that runs §5.3 checks daily against the live WAL archive).
- Cross-region replication for the National tier.

---

## 10. Cross-references

- [SCALABILITY.md §5](./SCALABILITY.md#5-operational-slos-post-pilot) — RPO/RTO canonical numbers.
- [OBSERVABILITY.md](./OBSERVABILITY.md) — `AL-09` (backup did not run), `AL-17` (restore drill failed).
- [RUNBOOK.md RB-09](./RUNBOOK.md#rb-09--backup-did-not-run), [RB-10](./RUNBOOK.md#rb-10--database-failover-required), [RB-12](./RUNBOOK.md#rb-12--schema-migration-to-apply).
- [INCIDENT_RESPONSE.md IR-13](./INCIDENT_RESPONSE.md#ir-13) — evidence pack capture.
- [SECURITY.md](./SECURITY.md) — at-rest encryption, KMS guidance.
- [DATA_MODEL.md §6](./DATA_MODEL.md#6-data-not-in-postgresql) — what lives outside Postgres.
- [DEPLOYMENT.md](./DEPLOYMENT.md) — tier-specific infrastructure that hosts the backup pipeline.
