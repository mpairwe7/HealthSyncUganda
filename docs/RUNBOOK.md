# Operations runbook

**Audience:** on-call engineers, SREs, ministry IT staff operating a pilot installation.
**Pager target:** `oncall@healthsync.go.ug` (forthcoming).
**Severity definitions:** §"Severity & escalation" below.

This runbook documents the day-2 procedures for a running HealthSync Uganda installation. Each procedure carries a stable ID (`RB-NN`) referenced from monitoring rules, ADRs, and CONTRIBUTING.md.

The principle: **diagnose, then act**. Do not pull the database, restart the service, or wipe Redis as a first move. If you are tempted to, page a second engineer.

---

## Quick reference

| Symptom                                                  | First step                                   | Procedure |
| -------------------------------------------------------- | -------------------------------------------- | --------- |
| `/readyz` red                                            | Check `/healthz` first.                       | [RB-01](#rb-01) |
| Circuit breaker stuck open                               | Inspect breaker state.                       | [RB-02](#rb-02) |
| DHIS2 outbox not draining                                | Inspect queue depth.                          | [RB-03](#rb-03) |
| Patient search slow                                      | Confirm DB connection pool.                  | [RB-04](#rb-04) |
| Login rate-limited at unusual scale                      | Confirm IP, then check abuse log.            | [RB-05](#rb-05) |
| Citizen reports a record missing                         | Check audit + ledger before changing data.   | [RB-06](#rb-06) |
| Supply ledger verification failed                        | **Stop.** Page second engineer.              | [RB-07](#rb-07) |
| Offline mutation queue not draining on a client device   | Browser-side procedure.                      | [RB-08](#rb-08) |
| Backup did not run                                       | Confirm cron + storage. Do not restore yet.  | [RB-09](#rb-09) |
| Database failover required                               | Promote read replica.                         | [RB-10](#rb-10) |
| TLS certificate expiring                                 | Renew via ACME / pilot CA.                   | [RB-11](#rb-11) |
| Schema migration to apply                                | Add → backfill → switch → drop.              | [RB-12](#rb-12) |
| Suspected PHI breach                                     | **Trigger §"Incident response".**            | [RB-13](#rb-13) |

---

## Common starting points

### Where to look first

| Question                          | Source                                                  |
| --------------------------------- | ------------------------------------------------------- |
| Is the API alive?                 | `GET /healthz`                                          |
| Is it ready to serve?             | `GET /readyz`                                           |
| What is the request error rate?   | Grafana board `HealthSync — overview`                   |
| What are the breakers doing?      | `GET /api/v1/interop/circuits` (admin)                  |
| What is the DHIS2 queue depth?    | Same call returns it.                                   |
| What does a specific trace say?   | Grafana → Tempo → search by `X-Trace-Id`.               |
| What did this user do today?      | Grafana → Loki → `actor_id="…"`.                        |

### Useful commands

```bash
# Liveness + readiness
curl -s https://api.healthsync.go.ug/healthz | jq
curl -s https://api.healthsync.go.ug/readyz  | jq

# Breaker state
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
  https://api.healthsync.go.ug/api/v1/interop/circuits | jq

# Trace by id (Tempo CLI)
tempo-cli query traces $TRACE_ID

# Container restart (pilot single-host)
docker compose restart backend
```

---

## Procedures

### RB-01 — `/readyz` is red

1. Read `/readyz` body. It enumerates which subsystem failed (`db`, `redis`).
2. If `db` is red: check Postgres logs (`docker compose logs --tail=200 postgres`). Common cause: connection pool exhausted — see RB-04.
3. If `redis` is red: try `docker compose exec redis redis-cli PING`. If PING fails, restart redis. The platform still serves degraded — `/readyz` returns 503 but `/healthz` stays green and clinical reads continue from cache.
4. If both are red: page second engineer; do not restart anything yet.

Do not restart the backend container before confirming the root cause. A flapping `/readyz` is meaningful telemetry.

### RB-02 — Circuit breaker stuck open

A breaker that does not transition `open → half_open` after the recovery window points at one of three causes.

1. **Downstream is truly down.** Confirm by hitting it directly (e.g. `curl -i https://api.nira.go.ug/...`). If so, the breaker is doing its job; communicate the partial outage and wait.
2. **Replicas are observing the breaker independently** (this is expected — see ADR 0002). One replica may report `open` while another reports `closed`. The aggregate metric `breaker_state{name=…}` averaged across replicas tells you the true picture.
3. **Code path bug — every probe fails identically.** If the downstream is up but the breaker still trips, capture a failing trace id and file a P2 issue with the trace attached.

To force a probe (use sparingly):

```bash
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
  https://api.healthsync.go.ug/api/v1/interop/circuits/dhis2/halfopen
```

### RB-03 — DHIS2 outbox not draining

1. Check queue depth: `GET /api/v1/interop/circuits` — the `dhis2.outbox.depth` field.
2. If depth is rising **and** breaker is `open`: this is correct. Wait for the breaker to recover.
3. If depth is rising **and** breaker is `closed`: the draining worker is stuck. Inspect `docker compose logs backend | grep dhis2_drain`. Likely a poison message at the head — capture its id, mark it `failed`, drain.
4. To force drain (admin only):

   ```bash
   curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
     https://api.healthsync.go.ug/api/v1/interop/dhis2/drain-queue
   ```

5. If draining a single message takes more than 30 s, suspect DHIS2 throttling; back off and retry with smaller batches.

### RB-04 — Patient search slow

1. Confirm symptom in Grafana: `GET /api/v1/patients` p95 > 500 ms.
2. Check the Postgres connection pool: `SELECT count(*) FROM pg_stat_activity WHERE state != 'idle';` Compare against `max_connections`. If saturated, look for slow queries: `SELECT query, state, query_start FROM pg_stat_activity WHERE state != 'idle' ORDER BY query_start;`
3. Check the application logs for `slow query` events (logged by SQLAlchemy when > 200 ms).
4. If the pool is healthy but search is still slow, the cause is usually a missing index on a search field. Compare against the canonical indexes in `backend/app/db/models/patient.py`.
5. Never `pg_terminate_backend` a query without paging the DBA. A long-running query may be a backup or a migration.

### RB-05 — Login rate-limit at unusual scale

1. Identify the IP and route from the 429s: Grafana → Loki → `status=429 path=~"/auth/.*"`.
2. If the IP belongs to a known legitimate aggregator (e.g. NIRA), increase its bucket by adding it to the `RATELIMIT_ALLOWLIST` env var and restart. Document the change in CHANGELOG.md.
3. If the IP is unknown and the pattern looks like credential stuffing, block at the WAF (NITA-U cloud) or the cloudflare layer.
4. **Never** raise the citizen-login limit globally without a written request from MoH security. The 5/5min/NIN limit is the only thing preventing OTP enumeration on stolen NINs.

### RB-06 — Citizen reports a missing record

This is the most common operational ticket. Do not edit the database to "restore" the record before doing this analysis.

1. Ask the citizen which facility, when, what.
2. Lookup audit log: `GET /api/v1/audit/by-subject/{nin}?since=...`
3. Check the supply / encounter ledger entry for the same time window. If a `create` entry exists but the record is not visible, the issue is access control (consent, role) — not data loss.
4. If no `create` entry exists, the encounter was never persisted. Likely cause: offline-only mutation that never drained because the device was reset. Recoverable only from the device's IndexedDB queue — see RB-08.
5. Document the finding in the ticket. Do not insert clinical data without a clinician's countersignature.

### RB-07 — Supply ledger verification failed

The verification job runs nightly and on demand: `GET /api/v1/supply/ledger/verify`. If it returns `{"ok": false}`:

1. **Stop.** Do not restart anything. Do not run migrations.
2. Page the on-call second engineer and the data-protection officer.
3. The response body includes `broken_at` (the row id where the chain breaks). Capture the row, the previous row, the application logs around `signed_at`, and any recent migrations.
4. The append-only invariant has been violated. The forensic question is *how*: a careless `UPDATE` permission, a migration that rewrote a row, or — worst case — adversarial action.
5. Do not "fix" the chain by rewriting hashes. The chain's value is precisely that it cannot be silently fixed. The integrity of the historical ledger is preserved; downstream operations may continue from the post-break entry forward.

See ADR 0004 and DPIA §5.3 for the policy basis.

### RB-08 — Offline mutation queue not draining on a client device

On the citizen / worker device:

1. DevTools → Application → IndexedDB → `healthsync.mutations`. Inspect the queue.
2. Common cause: the device has been offline for > 7 days and the cache TTL has expired. The user sees a banner asking them to consult IT.
3. If a single mutation is the head and has retried > 5 times, mark it `failed` (the UI offers a "discard" button after 5 attempts). Capture the payload before discarding — it goes to the lost-and-found bucket in the support log.
4. Server-side: confirm the idempotency key the client thinks is still pending is not already accepted (`SELECT * FROM idempotency_keys WHERE key = '<ulid>';`).

### RB-09 — Backup did not run

1. Check the cron logs (`/var/log/healthsync/backups.log`).
2. Confirm the previous successful backup. If < 24 h ago, you have time.
3. **Do not run `pg_restore` against a live database without disabling writes first.** A restore on top of live state is destructive.
4. Trigger a manual backup: `scripts/backup-now.sh`. Confirm it landed in the configured object store with checksum.
5. Investigate the cron failure separately. Common causes: storage quota, expired credentials, network policy change.

### RB-10 — Database failover required

The pilot ships with a primary + one streaming replica. To promote:

1. Confirm the primary is irrecoverable (not just slow).
2. Verify replica lag is < 60 s (`SELECT now() - pg_last_xact_replay_timestamp() FROM pg_stat_replication;`).
3. Run the promote script: `scripts/db-promote-replica.sh <replica-host>`. It performs `pg_ctl promote`, updates the connection string in the secret store, and triggers a rolling backend restart.
4. Announce a brief read-only window during the failover. Citizens see a banner; staff see a maintenance toast.
5. After promotion, immediately provision a new replica from the new primary. Do not run without a replica for more than 8 hours.

### RB-11 — TLS certificate expiring

Pilot deployments use Let's Encrypt via ACME (cert-manager on Kubernetes, certbot on bare VM). Renewal is automatic; manual intervention is needed only if:

1. The certificate has < 7 days remaining and no renewal attempt is visible in the logs.
2. The DNS or HTTP-01 challenge is failing (firewall change, DNS provider issue).

Do not rotate cert manually unless the automated path is genuinely broken — every manual rotation is a foot-gun for the next on-call.

### RB-12 — Schema migration to apply

Migrations are tested in staging first. To apply in production:

1. Read the migration file. Reject any single-step `DROP COLUMN` or `RENAME COLUMN` — those require the **add → backfill → switch reads → switch writes → drop** sequence.
2. Confirm the rollback path is tested in staging.
3. Announce a maintenance toast (UI auto-shows when the version skew exceeds tolerance).
4. Apply: `cd backend && uv run alembic upgrade head`. Watch the logs.
5. Smoke-test: `scripts/preflight.sh`. If it fails, rollback per the migration's down-script.

### RB-13 — Suspected PHI breach

This procedure has the highest precedence. It supersedes all other runbook items.

1. **Do not** discuss the suspected breach in public channels (Slack #healthsync-dev). Use the encrypted incident channel.
2. Notify:
   - The data-protection officer.
   - The Ministry of Health liaison.
   - PDPO (Personal Data Protection Office) — within 72 hours per DPPA 2019. (The DPO writes the notification; engineering provides the evidence pack.)
3. Capture the evidence pack: relevant trace ids, audit log slices, application logs, breaker state, recent deployments. Freeze the cluster state if possible (snapshot the DB, dump Redis, archive logs).
4. **Do not** "remediate" by deleting suspicious rows. Forensic preservation is more important than cosmetic cleanup.
5. The DPO files the notification with PDPO and (where required) the affected citizens. Engineering supports.

The detailed playbook is in [SECURITY.md](./SECURITY.md) §"Incident response".

---

## Severity & escalation

| Severity | Definition                                                                                       | Pager | Response time |
| -------- | ------------------------------------------------------------------------------------------------ | ----- | ------------- |
| **SEV-1** | Patient safety affected, PHI exposure suspected, or full national outage.                       | Yes   | 5 min         |
| **SEV-2** | Significant feature degraded for one or more districts (e.g. DHIS2 outbox stuck > 1 h).         | Yes   | 30 min        |
| **SEV-3** | Single feature degraded but workaround exists (e.g. analytics cache cold).                       | No    | 4 h           |
| **SEV-4** | Cosmetic or local issue.                                                                         | No    | next business day |

Page the on-call via the bridge at the top of this document. If you are unsure of severity, go higher.

---

## After every incident

A blameless post-mortem within five working days. Use the template at `docs/incidents/_template.md`. Outcomes:

1. Whether to update this runbook with a new RB-NN procedure.
2. Whether to write a new ADR for the underlying decision.
3. Whether to add a monitoring rule or a load-shedding mechanism.
4. Whether to amend [REQUIREMENTS.md](./REQUIREMENTS.md) (new NFR).

Post-mortems are public to all contributors; sanitised versions are shared with MoH.
