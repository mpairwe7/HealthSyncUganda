# Threat Model

**Audience:** security assessors, penetration testers, MoH/NITA-U cyber reviewers, contributors changing the trust boundary.
**Method:** STRIDE per asset, with trust-boundary diagram and explicit residual-risk register.
**Last reviewed:** 2026-05-25.

This document is the *systematic* threat enumeration that complements the narrative in [SECURITY.md](./SECURITY.md). SECURITY.md tells you the posture; this document tells you which threats that posture defends against, which it accepts, and which it pushes to the production roadmap.

Stable IDs: `T-NNN` (threats), `RR-NN` (residual risks). They are referenced from [INCIDENT_RESPONSE.md](./INCIDENT_RESPONSE.md), [RUNBOOK.md](./RUNBOOK.md) monitoring rules, and post-incident reports.

---

## 1. Scope and assumptions

**In scope:** the HealthSync Uganda platform as deployed for the pilot — FastAPI backend, Next.js PWA frontend, PostgreSQL, Redis, OpenTelemetry collector, NIRA and DHIS2 adapters.

**Out of scope (covered by the operator):**

- Physical security of the NITA-U / cloud-host data centre.
- Network security upstream of the load balancer.
- Endpoint security on staff devices beyond what the PWA enforces.
- Threats against NIRA, DHIS2, or other subprocessors *as systems* — we model only our interface with them.

**Assumptions:**

- The platform runs behind TLS 1.2+ at the load balancer.
- The deployment shape is one of those documented in [DEPLOYMENT.md](./DEPLOYMENT.md): laptop demo, pilot single-host, or national Kubernetes.
- The operator has rotated the demo `SECRET_KEY` and demo passwords before any production-like use.
- The audit log retention is honoured (≥ 1 year per [DATA_MODEL.md](./DATA_MODEL.md)).

---

## 2. Trust boundaries

```
  ┌──────────────────────────────────────────────────────────────────┐
  │  Citizen / worker device (browser)                               │
  │  ┌────────────────────────────────────────────────────────────┐  │
  │  │  Next.js PWA + Service Worker                              │  │
  │  │  - sessionStorage: JWT (cleared on tab close)              │  │
  │  │  - IndexedDB: TanStack Query cache (7d TTL),               │  │
  │  │    offline mutation queue, unencrypted at rest             │  │
  │  └────────────────────────────────────────────────────────────┘  │
  └─────────────────────────────────┬────────────────────────────────┘
                                    │  HTTPS (TLS 1.2+, HSTS preload-ready)
              ┌─────── TB-1 ────────┘
              │
              ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │  FastAPI gateway (per-pod)                                       │
  │  - HTTPBearer / require_role at every endpoint                   │
  │  - Middleware: idempotency, rate-limit, audit-context            │
  │  - In-memory: token cache, breaker state, rate-limit windows     │
  └─┬──────────┬────────────────────────┬─────────────────┬──────────┘
    │          │                        │                 │
    │TB-2      │TB-3                    │TB-4             │TB-5
    ▼          ▼                        ▼                 ▼
  ┌──────┐  ┌────────┐            ┌──────────┐      ┌──────────┐
  │ Pg   │  │ Redis  │            │  NIRA    │      │  DHIS2   │
  │ data │  │ cache  │            │ (extern) │      │ (extern) │
  └──────┘  └────────┘            └──────────┘      └──────────┘
   audit_log,                       NIN verify        analytics
   PHI, ledger                      OIDC (future)     push (outbox)

  ┌──────────────────────────────────────────────────────────────────┐
  │  Engineer workstation                                            │
  │  - Repo checkout, kubeconfig, admin tokens                       │
  └─────────────────────────────┬────────────────────────────────────┘
                                │  kubectl, ssh, admin bearer
                ┌─── TB-6 ──────┘
                ▼
            (production cluster + secret store)
```

Boundaries:

| ID    | Boundary                       | Crossing controls                                                                 |
| ----- | ------------------------------ | --------------------------------------------------------------------------------- |
| TB-1  | Internet → FastAPI             | TLS, HSTS, CORS allow-list, rate-limit, JWT, idempotency, request-size limits     |
| TB-2  | FastAPI → PostgreSQL           | Network ACL, password+TLS for connection; least-privilege DB user                  |
| TB-3  | FastAPI → Redis                | Network ACL, AUTH password; not exposed to internet                                |
| TB-4  | FastAPI → NIRA                 | TLS, API key, circuit breaker, response caching, retry budget                      |
| TB-5  | FastAPI → DHIS2                | TLS, basic-auth, circuit breaker, outbox queue                                     |
| TB-6  | Engineer → cluster             | mTLS / SSO to kube API, audit-logged kubectl, vaulted secrets, MFA on the IdP      |

---

## 3. Assets

The assets we are protecting, in priority order (highest blast radius first):

| Asset ID | Asset                          | Confidentiality | Integrity | Availability | Why it matters                                    |
| -------- | ------------------------------ | :-------------: | :-------: | :----------: | ------------------------------------------------- |
| A-1      | Patient PII/PHI                | **Critical**    | High      | Medium       | DPPA s.3 special-category; identity theft, stigma |
| A-2      | Audit log                      | Medium          | **Critical** | High      | Regulatory evidence (DPPA s.13/s.14); if tampered, accountability is lost |
| A-3      | Supply hash-chain ledger       | Low             | **Critical** | Medium    | Forensic primitive for stock movements; donor accountability |
| A-4      | Consent records                | Medium          | **Critical** | High      | Lawful-basis evidence (DPPA s.22, s.27)           |
| A-5      | JWT signing key (`SECRET_KEY`) | **Critical**    | Critical   | High        | Compromise = silent impersonation of any role     |
| A-6      | User password hashes           | High            | High      | Medium       | Hashed (bcrypt) but offline-cracking possible if leaked |
| A-7      | NIRA last-known-good cache     | High            | Medium     | Medium       | Degraded-mode trust signal; integrity matters for graceful failover |
| A-8      | Backups & evidence packs       | **Critical**    | **Critical** | High      | A breach of the backup is a breach of the data    |
| A-9      | Idempotency-key cache (Redis)  | Low             | Medium     | Medium       | Replay protection; loss → duplicate writes        |

---

## 4. STRIDE per asset

For each asset, the relevant STRIDE categories. Items marked **[mitigated]** are addressed by the current platform; **[accepted]** are explicit acceptances tracked in §6; **[roadmap]** are deferred to production.

### A-1 Patient PII/PHI

| Cat | Threat | Status | Control / link |
| --- | ------ | ------ | -------------- |
| **S** | Citizen logs in with stolen NIN + intercepted OTP | [mitigated] | NIRA OIDC in production (OTP stub in pilot); rate-limit on `/auth/citizen/login` (5 / 5 min / NIN) |
| **S** | Worker logs in with phished credentials | [mitigated] | bcrypt password; rate-limit; per [INCIDENT_RESPONSE.md IR-23](./INCIDENT_RESPONSE.md#ir-23--credential-compromise) the audit log detects abnormal access |
| **T** | Direct database update by privileged DB user | [accepted RR-01] | App-level convention; not enforced at DB; mitigated by audit log + `record_version` on Patient |
| **R** | Worker denies they read a record | [mitigated] | Every PII read emits an `audit_log` row with `actor_id`, `purpose`, mirrored to SIEM |
| **I** | Bulk export via API | [mitigated] | Pagination (`page_size <= 100`); `analytics/*` returns aggregates only (DPPA s.31); audit-log anomaly detection in [INCIDENT_RESPONSE.md §3 Phase B](./INCIDENT_RESPONSE.md#phase-b--detection--analysis) |
| **I** | Cross-facility worker reads | [accepted RR-02] | `GET /patients/{id}` is not facility-scoped at read time; compensated by audit log; see [ACCESS_CONTROL.md §3](./ACCESS_CONTROL.md#3-facility-scoping) |
| **I** | Lateral SQL injection | [mitigated] | SQLAlchemy parameterised queries; Pydantic `extra="forbid"` schemas; ruff lint catches f-string SQL |
| **I** | Cache leak on Redis (`patient` cached payloads) | [mitigated] | Redis is not exposed; NIRA cache contains coarse info (status), not full patient records |
| **D** | Search endpoint amplification (`q=` wildcard) | [mitigated] | Trigram index on `family_name`; rate-limit; pagination caps |
| **E** | Citizen escalates to worker | [mitigated] | Role claim signed in JWT; `require_role("worker")` denies; citizen-self check in `patients.py:118` |
| **E** | Worker escalates to ministry_admin | [mitigated] | Role hierarchy in `security.py:Principal.is_at_least`; tokens are HS256-signed |

### A-2 Audit log

| Cat | Threat | Status | Control / link |
| --- | ------ | ------ | -------------- |
| **T** | UPDATE / DELETE on `audit_log` rows | [accepted RR-03] | Append-only by application convention; DB-level `RULE` is a planned migration |
| **T** | Replay log mirror to SIEM | [mitigated] | Log records carry `trace_id`/`span_id`/`actor_id` — replays are detectable |
| **R** | Actor disclaims access | [mitigated] | JWT subject claim is authoritative; not user-controlled in the row |
| **I** | Direct read of audit_log via DB connection | [mitigated] | Least-privilege DB user for the app; the audit log is in the same DB but only operators with `ministry_admin`+DB role can query it |
| **D** | Audit-write failure blocks the request | [accepted RR-04] | By design — a request that cannot write its audit row should fail (DPPA s.14 accountability) |

### A-3 Supply hash-chain ledger

| Cat | Threat | Status | Control / link |
| --- | ------ | ------ | -------------- |
| **T** | UPDATE a `stock_events` row | [mitigated] | Verification cron + on-demand `GET /api/v1/supply/ledger/verify`; trips [RUNBOOK.md RB-07](./RUNBOOK.md#rb-07) and [INCIDENT_RESPONSE.md IR-21](./INCIDENT_RESPONSE.md#ir-21--supply-ledger-broken) |
| **T** | Migration that rewrites historical rows | [accepted RR-05] | Mitigated by RB-12 review and the chain-verify cron; not technically prevented |
| **T** | DELETE a leaf row | [mitigated] | Chain is recomputable; deletion creates a verifiable break |
| **I** | Bulk export via analytics | [mitigated] | Analytics aggregates only |

### A-4 Consent records

| Cat | Threat | Status | Control / link |
| --- | ------ | ------ | -------------- |
| **T** | Backdated `granted_at` to legitimise a past access | [accepted RR-06] | App generates `granted_at = datetime.now(UTC)`; DB-side trigger not enforced |
| **R** | Worker grants consent the patient did not actually give | [mitigated] | `granted_by` stamped with caller; consent is itself an audit-logged event; citizen can revoke on demand |
| **I** | Read of another patient's consents | [mitigated] | Citizen-self check in `consent.py:75`; staff bound by `require_role("worker")` + audit |

### A-5 JWT signing key

| Cat | Threat | Status | Control / link |
| --- | ------ | ------ | -------------- |
| **S** | Forge token | [mitigated for HS256] | Hard-coded `algorithms=["HS256"]` in `_decode_token`; required claims allow-list defeats algorithm-confusion (CVE-2025-45768 advisory in [SECURITY.md](./SECURITY.md)) |
| **T** | Modify token in transit | [mitigated] | TLS at TB-1; JWT MAC verification |
| **I** | Leak of `SECRET_KEY` from env / git history | [mitigated] | `.env.example` carries no real secret; deployment uses Vault/KMS-backed secret store; pre-commit hook bans `SECRET_KEY=` in committed files |
| **I** | Leak via debug log | [mitigated] | `structlog` redactors mask `secret_key`, `password`, `Authorization` fields |
| **E** | Rotation without re-auth | [roadmap RR-07] | RS256 + JWKS rotation in the IdP-backed deployment; pilot HS256 rotation forces re-auth |

### A-6 User password hashes

| Cat | Threat | Status | Control / link |
| --- | ------ | ------ | -------------- |
| **I** | Offline crack of leaked hashes | [mitigated] | bcrypt default work factor; 72-byte input truncation is defensive only (not a weakening, since bcrypt always truncates) |
| **I** | Hash-collision attack | [mitigated] | bcrypt is collision-resistant for password lengths |
| **E** | Reuse across services | [accepted RR-08] | Out-of-scope — staff are advised not to reuse via training |

### A-7 NIRA last-known-good cache

| Cat | Threat | Status | Control / link |
| --- | ------ | ------ | -------------- |
| **T** | Cache poisoning via spoofed NIRA response | [mitigated] | Circuit breaker isolates upstream; cache only populated by a successful TLS-verified response; per [INCIDENT_RESPONSE.md IR-24](./INCIDENT_RESPONSE.md#ir-24--spoofed-integration) |
| **R** | NIRA disputes a cached verification | [mitigated] | Cache entries are timestamped + TTL'd; audit log records the cache hit |
| **D** | Cache flushed during incident | [mitigated] | Platform degrades to "NIRA unreachable" mode (deny new verifications, serve known-good for existing); see [RESILIENCE.md](./RESILIENCE.md) |

### A-8 Backups & evidence packs

| Cat | Threat | Status | Control / link |
| --- | ------ | ------ | -------------- |
| **I** | Theft of backup tarball | [mitigated] | At-rest encryption with KMS/CMEK; object-store ACL excludes the on-call rota by default |
| **T** | Backup corruption / tampering | [mitigated] | Checksum manifest per backup; quarterly restore drill in [BACKUP_RESTORE.md](./BACKUP_RESTORE.md) |
| **I** | Evidence-bucket leak | [mitigated] | Legal-hold on the bucket; readable only by DPO + forensics lead |

### A-9 Idempotency-key cache

| Cat | Threat | Status | Control / link |
| --- | ------ | ------ | -------------- |
| **D** | Cache flush → duplicate writes on retry | [mitigated] | 24-h TTL on idempotency keys; offline drainer holds keys on the client too |
| **I** | Key guessing | [mitigated] | ULID keys (122 bits) are unguessable for practical purposes |

---

## 5. Attack scenarios (worked examples)

These are the scenarios used in the tabletop exercises documented in [INCIDENT_RESPONSE.md §7](./INCIDENT_RESPONSE.md#7-tabletop-exercises). Each ties the model above to concrete IR procedures.

### TS-A — Stolen worker tablet

A nurse's tablet (with cached IndexedDB) is stolen from a rural HC IV at midnight. The session token is still valid (8-hour TTL).

- **Threats invoked:** A-1 [I], A-5 [S] (via stolen token).
- **What is exposed:** patients viewed in the past 7 days within the nurse's facility scope; observations recorded during the same window; consent state.
- **What is NOT exposed:** patients outside that nurse's facility (because the writes were facility-stamped, even though reads were not); patients the nurse never viewed; the JWT signing key.
- **IR procedure:** [INCIDENT_RESPONSE.md IR-22](./INCIDENT_RESPONSE.md#ir-22--lost-or-stolen-device-with-cached-phi).

### TS-B — Rogue district admin querying outside their district

A district_admin in District X uses the analytics endpoints to pull aggregates for District Y.

- **Threats invoked:** A-1 [I], A-2 [R].
- **Detection:** analytics aggregates are not by themselves PHI, but the access pattern is a strong signal in the audit log (`actor_facility_id=NULL`, `actor_role=district_admin`, scope outside their assigned district).
- **What stops it:** the analytics endpoints do not currently constrain by the district_admin's assigned district. Compensated by audit log and the detection signal in [INCIDENT_RESPONSE.md §3 Phase B](./INCIDENT_RESPONSE.md#phase-b--detection--analysis). **Tracked as [RR-09](#6-residual-risk-register)**.

### TS-C — Spoofed DHIS2 endpoint

DNS within the cluster is poisoned to point `dhis2.go.ug` at an attacker-controlled host that accepts our outbox pushes.

- **Threats invoked:** A-1 [I] (data leaving the platform), A-7 [T] (analogous for DHIS2).
- **Detection:** TLS pin failure (when implemented) or `CapabilityStatement` mismatch on the response.
- **IR procedure:** [INCIDENT_RESPONSE.md IR-24](./INCIDENT_RESPONSE.md#ir-24--spoofed-integration).

### TS-D — Supply ledger broken by a careless migration

A migration writes a `quantity_delta` correction to a historical `stock_events` row.

- **Threats invoked:** A-3 [T].
- **Detection:** the nightly chain-verify cron returns `ok=false`.
- **IR procedure:** [INCIDENT_RESPONSE.md IR-21](./INCIDENT_RESPONSE.md#ir-21--supply-ledger-broken) → [RUNBOOK.md RB-07](./RUNBOOK.md#rb-07).
- **What stops it from happening again:** [RUNBOOK.md RB-12](./RUNBOOK.md#rb-12--schema-migration-to-apply) review discipline; database-level append-only `RULE` is planned.

### TS-E — Credential-stuffing burst on `/auth/login`

An attacker brings 50,000 username:password pairs from a public dump and tries them against `/auth/login`.

- **Threats invoked:** A-6 [S].
- **Detection:** sustained 429s on `/auth/login` from a small set of IPs; alert AL-… (see [OBSERVABILITY.md](./OBSERVABILITY.md)).
- **What stops it:** rate-limit (600 req/min default, tighter on auth routes); audit log on every successful login (rare for stuffing); WAF/Cloudflare block at the next layer.
- **IR procedure:** [RUNBOOK.md RB-05](./RUNBOOK.md#rb-05--login-rate-limit-at-unusual-scale).

---

## 6. Residual-risk register

Risks the platform accepts in its current shape. Each carries an acceptance owner, a roadmap link if applicable, and a monitoring rule.

| ID    | Risk                                                                                  | Reason for acceptance                                          | Acceptance owner | Monitoring / mitigation                                                                                       | Resolution target               |
| ----- | ------------------------------------------------------------------------------------- | -------------------------------------------------------------- | ---------------- | -------------------------------------------------------------------------------------------------------------- | ------------------------------- |
| RR-01 | Direct DB UPDATE on PII can bypass audit                                              | Pilot DB has minimal operator access; full DB-RULE deferred    | Engineering lead | Audit-log anomaly query; access-tier review pre-pilot                                                          | Production (`audit_log` RULE)    |
| RR-02 | `GET /patients/{id}` not facility-scoped                                              | Compensating control: audit log + detection                    | Engineering lead | [INCIDENT_RESPONSE.md §Phase B](./INCIDENT_RESPONSE.md#phase-b--detection--analysis) cross-facility signal      | Pre-pilot (ADR + migration)      |
| RR-03 | `audit_log` is append-only by app convention, not DB rule                             | DB rule is a planned migration                                 | Engineering lead | Anomalous row-version queries; restore-drill verifies                                                          | Pre-pilot                        |
| RR-04 | Audit-write failure blocks the user request                                           | Required by DPPA s.14                                          | DPO              | n/a — desired behaviour                                                                                        | n/a                              |
| RR-05 | Migration can rewrite a `stock_events` row                                            | Mitigated by RB-12 review and the chain verifier                | Engineering lead | Nightly cron + on-demand verify                                                                                | Production (DB rule)             |
| RR-06 | `consents.granted_at` is application-controlled                                       | Audit log records the grant action with its own `created_at`    | DPO              | Anomaly query: consent rows whose `granted_at` < `created_at` - epsilon                                        | Pre-pilot (DB default)           |
| RR-07 | JWT HS256 rotation forces re-auth instead of seamless rotation                        | Pilot prototype; RS256+JWKS deferred                            | Engineering lead | Manual rotation runbook                                                                                        | Production (IdP)                 |
| RR-08 | Staff may reuse passwords across services                                              | Out-of-platform control                                         | MoH HR           | Annual training; mandatory password change every 90 days (IdP-enforced post-Keycloak)                          | Production (IdP)                 |
| RR-09 | `analytics/*` does not constrain district_admin to their district                     | Compensating control: audit log + tabletop TS-B                 | Engineering lead | Audit-log query: district_admin reads outside `actor_facility_district`                                        | Pre-pilot (scope claim)          |
| RR-10 | IndexedDB cache on the worker device is unencrypted at rest                            | Bounded by 7-day TTL and session-token binding                  | Engineering lead | Session-revoke procedure (IR-14 step 2); device-loss IR (IR-22)                                                 | Production (device-level crypto) |
| RR-11 | PyJWT CVE-2025-45768 (disputed)                                                       | Not exploitable in our usage — see [SECURITY.md](./SECURITY.md) advisories table | Engineering lead | Monthly Dependabot triage                                                                                      | When upstream fix lands           |
| RR-12 | No WAF / DDoS layer in pilot                                                          | NITA-U cloud option includes it; pilot single-host does not    | Operator         | Rate-limit at app layer; alert on sustained 429 burst                                                          | Production                       |

---

## 7. Roadmap Closure Plan

Every residual risk in §6 has an explicit closure target. This table is the **operational commitment** the team makes to the Showcase panel and to MoH / NITA-U: by the named date, the named owner produces the named evidence-of-closure artefact and the risk is either eliminated, materially reduced, or accepted with a written rationale countersigned by the DPO.

Closure phases are pegged to the project timeline:

- **Pre-showcase** = before 2026-06-25.
- **Pre-pilot** = 2026-06-25 to 2026-09-30 (Pilot kickoff window).
- **During pilot** = 2026-10-01 to 2027-06-30 (Pilot operational window).
- **Pre-national** = 2027-07-01 to 2028-12-31 (Regional → national hardening).

| RR    | Owner               | Closure target  | Evidence of closure (what an auditor would inspect)                                                                                                                                                                                       | Tracking link / artefact                                                                                       |
| ----- | ------------------- | --------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| RR-01 | Engineering lead    | Pre-pilot (2026-09-30) | Alembic migration adding a Postgres `RULE` denying `UPDATE`/`DELETE` on `audit_log` and `stock_events`; failing tests when bypass attempted; access-tier review document signed by DBA + DPO.                                              | Migration in `backend/alembic/versions/`; checklist in `docs/incidents/access-tier-review-2026-09.md`.          |
| RR-02 | Engineering lead    | Pre-pilot (2026-09-30) | ADR documenting the facility-scope policy for read endpoints; migration enforcing scope-or-consent at `GET /patients/{id}`; updated [ACCESS_CONTROL.md §3](./ACCESS_CONTROL.md#3-facility-scoping); regression tests in `backend/tests/`. | `docs/adr/0005-facility-scoped-patient-reads.md` (to be authored).                                              |
| RR-03 | Engineering lead    | Pre-pilot (2026-09-30) | Same migration as RR-01 (covers `audit_log` append-only at DB layer).                                                                                                                                                                       | See RR-01 row.                                                                                                  |
| RR-04 | DPO                 | n/a — desired   | Behavioural test (`test_audit_failure_blocks_request`) asserts a 5xx when the audit-write fails; documented as intentional behaviour.                                                                                                       | `backend/tests/test_audit.py` (to be added).                                                                    |
| RR-05 | Engineering lead    | Pre-pilot (2026-09-30) | Same DB-level append-only rule (RR-01) closes this transitively. RB-12 migration review process additionally requires a chain-verify run on the staging DB before any migration affecting `stock_events`.                                  | RB-12; CI job `migration-chain-check`.                                                                          |
| RR-06 | DPO                 | Pre-pilot (2026-09-30) | Postgres default `granted_at = now()` enforced at the DB layer; constraint check that `granted_at >= created_at`.                                                                                                                          | Migration `0006_consent_granted_at_default.sql` (to be added).                                                  |
| RR-07 | Engineering lead    | Pre-national (2027-12-31) | Production deployment uses Keycloak / Authentik with RS256 + JWKS rotation; rotation procedure documented in [SECURITY.md §"Penetration testing & vulnerability management"](./SECURITY.md).                                              | Keycloak realm export; rotation runbook in RUNBOOK; ADR `0006-idp-production.md`.                              |
| RR-08 | MoH HR              | During pilot (2027-06-30) | IdP-enforced 90-day password rotation; staff-training attendance log signed quarterly; named training curriculum referenced from TEAM.md.                                                                                                  | Keycloak password policy; training register in MoH HR system.                                                   |
| RR-09 | Engineering lead    | Pre-pilot (2026-09-30) | Scope claim in JWT (`assigned_district` for district_admin); `analytics/*` endpoints filter by claim; regression tests.                                                                                                                    | ADR `0007-district-scope-claim.md`; `backend/app/api/v1/analytics.py` updated.                                  |
| RR-10 | Engineering lead    | Pre-national (2027-12-31) | Encrypted IndexedDB cache (per [WebCrypto best practice]); evaluation of device-attestation (FIDO L3) for the worker device fleet; alternative: shift to per-request fetch with no client-side cache.                                       | ADR `0008-encrypted-client-cache.md`; security review minutes.                                                  |
| RR-11 | Engineering lead    | Monthly review   | Monthly Dependabot triage entry in [SECURITY.md "Known advisories and waivers"](./SECURITY.md); revisit when a non-disputed PyJWT CVE supersedes this one or when an upstream patch lands.                                                | SECURITY.md advisories table row; calendar reminder.                                                            |
| RR-12 | Operator (NITA-U)   | Pre-pilot (2026-09-30) | NITA-U Government Cloud WAF / DDoS protection deployed in front of the API; CDN tier with rate-limiting; alert AL-11 wired.                                                                                                                  | Deployment overlay `infra/k8s/overlays/national/`; vendor SOW with NITA-U.                                      |

**Cadence:** the closure plan is reviewed monthly at the Security & Privacy Review (per [TEAM.md §3](./TEAM.md#3-governance)). Any row that slips by more than one quarter is escalated to the Architecture Review Board with a written justification.

**Sign-off rule:** an RR row is considered *closed* only when the evidence artefact has been produced and reviewed by *two* people — the named owner and the DPO (for privacy-relevant items) or a peer engineer (for engineering-only items).

---

## 8. Cross-references

- [SECURITY.md](./SECURITY.md) — posture, controls, advisories table.
- [ACCESS_CONTROL.md](./ACCESS_CONTROL.md) — role matrix referenced by privilege-escalation threats.
- [DATA_MODEL.md](./DATA_MODEL.md) — assets named in §3 and §4.
- [INCIDENT_RESPONSE.md](./INCIDENT_RESPONSE.md) — what happens when a threat is realised.
- [RUNBOOK.md](./RUNBOOK.md) — RB-procedures invoked by the scenarios in §5.
- [OBSERVABILITY.md](./OBSERVABILITY.md) — alerts that fire on threat indicators.
- [DPIA.md](./DPIA.md) — privacy-risk register (overlaps with §6 but framed by data-subject impact rather than STRIDE).
- [RESILIENCE.md](./RESILIENCE.md) — degradation paths under denial-of-service.
- [adr/0002-resilience-circuit-breakers.md](./adr/0002-resilience-circuit-breakers.md) — why breakers are themselves a security control.
- [adr/0004-supply-hash-chain-ledger.md](./adr/0004-supply-hash-chain-ledger.md) — design choice behind A-3.
