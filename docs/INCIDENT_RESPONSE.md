# Incident Response

**Audience:** Data-Protection Officer (DPO), MoH liaison, on-call engineers, SREs, security responders.
**Pager target (forthcoming):** `oncall@healthsync.go.ug`.
**Legal anchor:** Uganda Data Protection & Privacy Act 2019 (DPPA), s.19 — notification of breach within 72 hours.
**Last reviewed:** 2026-05-25.

This document is the operational breach playbook. It complements — and does not duplicate — the security *posture* in [SECURITY.md](./SECURITY.md) and the day-2 *operations* in [RUNBOOK.md](./RUNBOOK.md). The runbook tells you what to do when the platform is degraded; **this document tells you what to do when the platform is compromised, or when the compromise is suspected.**

Every step has a stable ID (`IR-NN`) so monitoring rules, ADRs, and post-mortems can reference it without rot.

---

## 1. Activation

### IR-01 — Triggers

This playbook is triggered when *any* of the following is true:

- An on-call engineer suspects PHI/PII has been exposed, exfiltrated, or modified by an unauthorised party.
- The supply-chain ledger verification (`GET /api/v1/supply/ledger/verify`) returns `{"ok": false}` — see [RUNBOOK.md RB-07](./RUNBOOK.md#rb-07).
- The audit log shows access patterns inconsistent with normal clinical workflow (cross-district queries by a single worker, bulk reads, off-hours bursts).
- A device known to hold cached PHI in IndexedDB is reported lost or stolen.
- A staff credential is leaked, phished, or shared.
- An external party (researcher, journalist, citizen) reports an information disclosure.
- A subprocessor (NIRA, DHIS2, cloud host) notifies us of a breach affecting our data.

When in doubt: **activate**. Standing down an unjustified activation costs less than missing the PDPO notification window.

### IR-02 — First five minutes

The first responder (typically the on-call engineer who detected the signal) does exactly these five things, in order:

1. **Acknowledge.** Mark the alert acknowledged in the on-call tool. Note the wall-clock time — this is `T0`. The DPPA 72-hour clock starts now.
2. **Open the encrypted incident channel.** Do *not* use the public engineering Slack (`#healthsync-dev`). Use the dedicated encrypted channel (see §6).
3. **Page the second engineer.** Two-person rule for any potential PHI breach. The second engineer becomes the *scribe* (see IR-03).
4. **Notify the DPO.** A single line: "Activating IR. Trigger: <one sentence>. T0=<HH:MM UTC>." The DPO decides whether MoH liaison and PDPO are looped in immediately or after triage.
5. **Do NOT remediate yet.** Do not delete suspicious rows, do not roll back deployments, do not flush Redis, do not restart containers. Forensic preservation comes before remediation. See [IR-12](#ir-12).

### IR-03 — Roles during the incident

| Role | Responsibility |
| --- | --- |
| **Incident Commander (IC)** | First responder by default; can hand over. Owns sequencing, decisions, communication tree. Does *not* type commands at the database. |
| **Scribe** | The second engineer. Records every observation, command, timestamp into the incident channel as it happens. The scribe's transcript becomes the audit pack. |
| **Subject-matter expert (SME)** | Whoever knows the affected subsystem best. Pulled in by the IC. |
| **Data-Protection Officer (DPO)** | Decides whether to notify PDPO and affected citizens; writes the official notification; interfaces with MoH legal. The DPO is **not** the IC. |
| **MoH liaison** | Single channel to Ministry of Health communications. The IC and DPO speak through this person to the ministry — not directly. |
| **CERT-UG contact** | NITA-U incident reporting per `docs/COMPLIANCE.md §D`. Engaged by the DPO once classification is clearer than "maybe". |

Roles can be held by the same person only if no alternative exists. The IC and Scribe must be different people.

---

## 2. Severity & escalation

Severity follows the same ladder as the runbook to avoid drift. **Canonical source:** [RUNBOOK.md §Severity & escalation](./RUNBOOK.md#severity--escalation). The mapping for IR purposes:

| Runbook severity | IR classification | PDPO notification | Citizen notification |
| --- | --- | --- | --- |
| SEV-1 (patient safety / PHI exposure / national outage) | **Confirmed breach** or **patient-safety incident** | Yes, within 72 h of T0 | Yes, where DPPA s.19 requires |
| SEV-2 (district-scale degradation) | **Suspected breach** under investigation | Tentative — DPO decides after triage | No (unless confirmed) |
| SEV-3 / SEV-4 | **Security event** under investigation | No | No |

Reclassification is allowed at any point — record the change in the incident channel with timestamp and reason.

---

## 3. NIST 800-61r2 phases

The playbook follows the NIST Computer Security Incident Handling Guide (SP 800-61 rev 2) phases. Each phase has explicit entry and exit criteria so the team knows when to move on.

### Phase A — Preparation (always-on)

These are the things that must be true *before* an incident, owned by the platform team:

- [IR-04] On-call rota with primary + secondary contactable within 5 min for SEV-1.
- [IR-05] DPO contact details published in the citizen portal (DPPA s.20).
- [IR-06] PDPO contact details and the official notification template held in `docs/templates/` (forthcoming) and known to the DPO.
- [IR-07] Encrypted incident channel exists, with membership reviewed quarterly.
- [IR-08] Forensic preservation runbook (this document) rehearsed twice a year in tabletop form. See [§7 Tabletop](#7-tabletop-exercises).
- [IR-09] Audit log retention ≥ 1 year (see [DATA_MODEL.md](./DATA_MODEL.md) retention table).
- [IR-10] OpenTelemetry traces retained ≥ 30 days. See [OBSERVABILITY.md](./OBSERVABILITY.md) §retention.

### Phase B — Detection & Analysis

Signals that flow into IR-01:

| Signal | Source | Threshold |
| --- | --- | --- |
| Audit log anomaly: cross-district worker reads | `audit_log` query (Grafana → Loki) | > 5 patients outside actor's facility scope in 5 min |
| Bulk reads: single actor pulling many records | `audit_log` query | > 50 `Patient` reads in 5 min by one `actor_id` |
| Off-hours bursts | log time-of-day | > 20 PHI reads between 22:00 and 05:00 Africa/Kampala |
| Supply ledger broken | `GET /api/v1/supply/ledger/verify` nightly cron | `ok=false` |
| Auth anomaly | rate-limit metrics | sustained 429s on `/auth/citizen/login` from one IP > 10 min |
| Subprocessor notification | NIRA / DHIS2 / cloud provider email | any |
| External report | `security@healthsync.go.ug` inbox | any |

[IR-11] **Initial triage** (target: within 30 min of T0):

1. Capture the original signal — exact query, exact timestamps, screenshot or log slice — into the incident channel.
2. Determine the **blast radius**: how many records, which districts, which actors, which time window.
3. Determine the **classification** (per §2): confirmed breach / suspected breach / security event.
4. Determine whether the activity is still ongoing (active session, in-flight job, persistent backdoor) or historical.
5. Decide on early containment (see Phase C) — only if doing so does not destroy evidence.

### Phase C — Containment, Eradication, Recovery

<a id="ir-12"></a>
[IR-12] **Forensic preservation — rules of engagement.** Read this before anything in this phase.

> Forensic preservation outranks remediation. A breached system that has been "cleaned up" cannot be characterised, cannot be reported accurately to PDPO, and cannot be defended against the next attempt.

Concretely:

- **No `DELETE` and no `UPDATE`** on rows you suspect were touched. Even legitimate-looking cleanup destroys evidence.
- **No `pg_terminate_backend`** on suspicious connections without explicit IC approval.
- **No container restart** on a backend pod that holds the attacker's session. Restarting drops in-memory state (token cache, idempotency keys, rate-limit windows) that may be the only place evidence exists.
- **No `FLUSHALL` on Redis.** Same reason.
- **No log rotation force.** The current log file is evidence.
- **No deploy** to `main` until the IC explicitly clears it. Rolling forward over an attacker's footprint is the deploy equivalent of `DELETE`.

<a id="ir-13"></a>
[IR-13] **Snapshot the world** (target: within 1 h of T0):

```bash
# DB snapshot — runs against the read replica to avoid disturbing primary
scripts/preflight.sh                                # confirms target replica is healthy
# (forthcoming) scripts/snapshot-now.sh ir-${TICKET}  # tagged, encrypted snapshot to evidence bucket
```

If `scripts/snapshot-now.sh` is not yet available (pilot phase), the manual procedure is:

1. Pause writes if possible (maintenance toast via admin endpoint).
2. `pg_basebackup` from the replica into the evidence object-store bucket, encrypted with the evidence-bucket KMS key.
3. `redis-cli --rdb evidence-${TICKET}.rdb` (no FLUSH).
4. `tar` and upload application logs, OpenTelemetry traces (Tempo export), and the OTel Collector receiver buffer.

Evidence is stored in an object-store bucket with **legal-hold enabled** and an ACL that excludes the engineers normally on call. Only the DPO and the appointed forensics lead can read it back.

<a id="ir-14"></a>
[IR-14] **Containment options**, in order of preference (least → most destructive):

1. **Revoke a single token.** If the suspect actor is identified, force-expire the JWT by rotating their session secret (admin endpoint). Other users unaffected.
2. **Disable a single account.** `UPDATE users SET active=false WHERE id=...` — recorded in the audit log. The user is informed via official channel only after the IC approves.
3. **Block an IP at the WAF / Cloudflare layer.** Document the exact rule in the incident channel.
4. **Rate-limit a route to 0** via `RATELIMIT_OVERRIDE` env var + rolling restart of the *frontend* (the backend stays up to preserve in-memory state).
5. **Read-only mode** — flip the platform to read-only via the maintenance flag. Citizens see a banner; staff see a toast.
6. **Full disconnect** — stop accepting any traffic by cutting load-balancer health. Last resort.

[IR-15] **Eradication.** Once containment holds and evidence is captured:

1. Patch the vulnerability that allowed entry — code fix, config fix, dependency bump, secret rotation.
2. Rotate all secrets that *might* have been exposed: JWT signing key (`SECRET_KEY`), database passwords, integration credentials (NIRA_API_KEY, DHIS2_PASSWORD), object-store keys.
3. Verify the patch against a representative test case in staging before deploying.
4. Deploy with the IC's explicit go-ahead.

[IR-16] **Recovery.** Bring the platform back to full service:

1. Re-enable writes, lift read-only mode.
2. Force a session expiry for *all* users on the affected scope (district / facility / national) — citizens and staff re-authenticate.
3. Drain any queued mutations from offline devices through a fresh, post-patch backend.
4. Run the post-deploy smoke test (`scripts/preflight.sh`).
5. Announce recovery on the official channels per the communication plan ([§6](#6-communication-tree)).

### Phase D — Post-Incident Activity

Within five working days of recovery the team runs a blameless post-mortem using the runbook's template (single source of truth: [RUNBOOK.md §"After every incident"](./RUNBOOK.md#after-every-incident)). Outputs:

- A timeline document filed in `docs/incidents/${YYYY-MM-DD}-${slug}.md` (the `docs/incidents/` directory is created on first incident).
- A list of follow-ups with owners and dates — new RB-NN procedures, new monitoring rules, schema changes, ADRs.
- A sanitised version is shared with MoH and (where the DPPA requires) with PDPO.
- An update to this document — new IR-NN steps if any phase was found insufficient.

---

## 4. Specific incident classes

Each subsection compresses the playbook to the specific signals, evidence, and decisions for one class of incident. Always read [§3 NIST phases](#3-nist-800-61r2-phases) first — the class-specific guidance refines, it does not replace.

### IR-20 — Suspected PHI breach

The default class. Use unless one of the more specific classes below clearly applies.

- **Specific evidence to capture:** the `audit_log` rows for the suspect access window; the OpenTelemetry trace_ids tied to those rows; the `purpose` field declared on each access; the IP and user-agent from the trace metadata.
- **Specific containment:** see IR-14 step 2 (disable account) and step 4 (rate-limit) — preferred over disabling the whole platform.
- **DPPA notification:** the DPO drafts the PDPO notice from `docs/templates/pdpo-notification.md` (forthcoming); fields needed are listed in [IR-30](#ir-30--pdpo-notification-template).

### IR-21 — Supply ledger broken

Triggered by [RUNBOOK.md RB-07](./RUNBOOK.md#rb-07). This is a high-severity event because the supply-chain hash-chain is a forensic primitive — if it is broken, the historical integrity of stock movements is in question.

- **Specific evidence to capture:** the `broken_at` row id from the verify response; that row, the row before it, and the row after it; the application logs between those rows' `signed_at` timestamps; the deployment history for the 24 h preceding the break.
- **Specific containment:** **do not "fix" the chain by rewriting hashes**. The chain's value is precisely that it cannot be silently fixed. Operations may continue from the post-break entry forward; the historical chain is preserved as evidence.
- **Notification:** the DPO judges. A broken supply chain is not, by default, a PHI breach — but if the cause was unauthorised access, it is. Re-classify accordingly.

### IR-22 — Lost or stolen device with cached PHI

A worker's phone or tablet, holding IndexedDB cache from the offline-first PWA, is reported lost or stolen.

- **Specific evidence to capture:** the device's last-known `actor_id` session; the audit log entries from that session for the past 7 days (the offline cache TTL); the offline mutation queue, if it had drained server-side.
- **Specific containment:** rotate that account's session immediately (force re-auth). The cached data on the device is bounded — only patients the worker had viewed in the past 7 days, and only those facility-scoped reads the worker was authorised to perform. The cache is unencrypted on the device but bound to the session token; an attacker without the JWT cannot decrypt or refresh it.
- **Notification:** depends on what was cached. If sensitive special-category data (HIV status, mental health) was in scope, treat as IR-20. Otherwise the bounded exposure may not meet the DPPA s.19 threshold — the DPO decides.

### IR-23 — Credential compromise

A staff credential (username + password, or JWT) is phished, shared in plain text, or found in a public paste / git history.

- **Specific containment:** disable the account (IR-14 step 2) and force re-auth on all sessions. Rotate JWT signing key if the leaked credential is a token (any token signed before the rotation becomes invalid).
- **Forensic review:** trace the account's audit log for the period between leak and disable; classify by the most sensitive data accessed.
- **Notification:** depends on whether the credential was used by the unauthorised party; the audit trail tells you.

### IR-24 — Spoofed integration

A system pretending to be NIRA or DHIS2 calls our endpoints or accepts our calls. Detection signals: circuit-breaker traces that succeed against an unexpected hostname; TLS pinning failures (when implemented); responses whose schema does not match the expected `CapabilityStatement`.

- **Specific containment:** disable the relevant integration via env var (set `NIRA_BASE_URL` / `DHIS2_BASE_URL` to an empty value and rolling-restart). The platform degrades gracefully — see [RESILIENCE.md](./RESILIENCE.md).
- **Evidence:** the breaker telemetry, the suspicious certificate, DNS resolution records.
- **Notification:** subprocessor classification — report to the legitimate NIRA/DHIS2 contacts as well as PDPO.

### IR-25 — Subprocessor breach

Notification arrives from NIRA, DHIS2, or the cloud provider that *they* were breached and our data may be in scope.

- The DPO leads. Engineering supports: confirms what data flowed to that subprocessor, when, in what shape.
- The DPPA s.21 chain means we notify PDPO independently, regardless of the subprocessor's own filing.

---

## 5. PDPO notification

### IR-30 — PDPO notification template

The notification follows the form prescribed by the Personal Data Protection Office under DPPA s.19. The DPO writes it; engineering supplies the evidence pack. The required fields:

| Field | Source |
| --- | --- |
| Nature of breach | DPO summary, drawn from the IR timeline |
| Categories of personal data affected | Reference to [DATA_MODEL.md](./DATA_MODEL.md) PII inventory — name the tables and the sensitive columns |
| Categories and approximate number of data subjects | `SELECT count(DISTINCT resource_id) FROM audit_log WHERE …` constrained to the breach window |
| Likely consequences | DPO assessment; may include identity theft, social stigma (HIV/mental health), or financial loss |
| Measures taken or proposed | The containment / eradication / recovery steps from §3 |
| Contact point | The DPO |
| Date and time of breach detection (T0) | Captured at IR-02 step 1 |
| Date and time of breach occurrence (if different) | Best estimate from the audit log / trace timeline |

### IR-31 — Citizen notification

Required by DPPA s.19 where the breach is *likely to result in high risk to rights and freedoms*. The DPO and MoH legal decide. When required:

- Channel: the official MoH SMS gateway and / or postal addresses on file in the patient record.
- Content: plain language; what happened, what data was involved, what we are doing, what they can do.
- Language: English + Luganda by default; other locales as the affected districts dictate.
- Cadence: a single, complete message — not a stream of updates.

---

## 6. Communication tree

| Audience | Channel | Who speaks | Cadence |
| --- | --- | --- | --- |
| Incident team | Encrypted incident channel | IC + Scribe + SME | Continuous, every observation |
| DPO | Direct call, then the encrypted channel | IC | At T0, at classification, at containment, at recovery |
| MoH liaison | Direct call to the named liaison | DPO | Within 1 h of classification |
| PDPO | Official letter / portal submission | DPO | Within 72 h of T0 if classification is "confirmed breach" |
| CERT-UG (NITA-U) | Per `docs/COMPLIANCE.md §D` | DPO | Within 24 h of classification |
| Affected citizens | MoH SMS / post | MoH communications (drafted by DPO) | Once, when scope is final |
| Press | Through MoH communications only | MoH spokesperson | Never directly by engineering |
| Public engineering Slack | After PDPO is notified, at DPO's discretion | DPO | One-time post-incident note |

The encrypted incident channel is the **only** place engineering discusses an open incident. Side-channels (DM, voice notes, personal email) leak the timeline and break the audit pack.

---

## 7. Tabletop exercises

Twice a year — once before pilot go-live, once mid-year — the platform team runs a tabletop exercise against this playbook. Scenarios rotate through:

- IR-20 PHI breach (rogue admin querying outside their district)
- IR-21 Supply ledger broken (a careless migration UPDATEs a `stock_events` row)
- IR-22 Lost device (a nurse's tablet stolen from a clinic)
- IR-23 Credential compromise (a worker's password posted to a WhatsApp group)
- IR-24 Spoofed DHIS2 (an attacker stands up a fake DHIS2 endpoint)
- IR-25 Subprocessor breach (NIRA notifies us)

Each exercise produces a short report filed alongside the incident-folder template (`docs/incidents/tabletop-${YYYY-MM-DD}-${scenario}.md`) and any updates to this document are made via PR with the same review discipline as a real incident review.

---

## 8. Cross-references

- [SECURITY.md](./SECURITY.md) — security posture, threat model, advisories.
- [THREAT_MODEL.md](./THREAT_MODEL.md) — STRIDE walkthrough that names the assets and trust boundaries referenced here.
- [ACCESS_CONTROL.md](./ACCESS_CONTROL.md) — role hierarchy and facility-scoping rules used to interpret audit log anomalies.
- [RUNBOOK.md](./RUNBOOK.md) — day-2 operations; RB-07, RB-09, RB-10, RB-13 link in here.
- [OBSERVABILITY.md](./OBSERVABILITY.md) — where to find the audit log, traces, and alerts that fire IR-01.
- [DATA_MODEL.md](./DATA_MODEL.md) — what counts as personal data; canonical for the PDPO notification field "categories of personal data affected".
- [COMPLIANCE.md](./COMPLIANCE.md) — DPPA s.19, s.20, s.21 mapping; CERT-UG / NITA-U reporting chain.
- [DPIA.md](./DPIA.md) — risk register; an incident is a realised risk and the DPIA may need updating after recovery.
