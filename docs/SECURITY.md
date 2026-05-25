# Security & Privacy

HealthSync Uganda processes sensitive personal and clinical data. The security posture is designed against the **Uganda Data Protection & Privacy Act (2019)**, the **Uganda Computer Misuse Act (2011)**, and the technical guidance of the **National Information Technology Authority — Uganda (NITA-U)**.

## Threat model

Primary adversaries we defend against:

1. **External attackers** seeking PII at scale (e.g. to extort, defraud).
2. **Insider misuse** — a worker accessing records without clinical need.
3. **Spoofed integrations** — a malicious system pretending to be DHIS2.
4. **Loss / theft of devices** holding cached data.
5. **Network adversaries on the path** between client and server.

## Authentication & authorisation

- **Citizens** authenticate with NIN + OTP. Production swaps the OTP-stub for NIRA's OIDC flow; the contract surface (the `auth/citizen/login` endpoint) does not change.
- **Workers, pharmacists, admins** authenticate with username + password (bcrypt-hashed via `passlib`). Production deployments should put Keycloak / Authentik in front.
- **JWT** access tokens are HS256-signed by default for the prototype. Production should switch to RS256 with key rotation via the OIDC IdP.
- **Five roles**: `citizen`, `worker`, `pharmacist`, `district_admin`, `ministry_admin`. Each endpoint declares its minimum role; access is enforced at the dependency level (`require_role`) so it cannot be missed.
- **Tokens are short-lived** (2h for citizens, 8h for staff). No refresh tokens in the prototype — re-login is intentional for an attended workstation context.

## Network & transport

- **TLS 1.2+** enforced at the load balancer; HSTS preload-ready via the `Strict-Transport-Security` header set in `next.config.ts`.
- **CORS** is allow-listed; no wildcards in production.
- **Hardened response headers**: `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy: camera=(), microphone=(), geolocation=(self)`.
- **Body-size limits & rate limits** at the FastAPI middleware layer (token bucket per client+path, 600 req/min default).

## Data at rest

- **PostgreSQL** with `pgcrypto`. Sensitive fields (phone, email) can be encrypted with Fernet using `SECRET_KEY` — extension included in the prototype as a follow-up.
- **Backups** should be encrypted at the volume level. Use AWS KMS / GCP CMEK or Vault transit when going to the cloud.
- **Audit log** is *append-only* by application convention, with a follow-up Postgres `RULE` to enforce at the database layer (`PR welcome`).

## Audit & accountability

Every read or write to PII goes through `app.core.audit.record_access`, which writes:

- Actor (user-id or NIN)
- Actor role + facility
- Resource type + id
- Action (`read`, `create`, `update`, `revoke`, `fhir-read`, …)
- **Purpose** of access (required field — caller must declare *why* the data is being touched)
- Consent record id, if applicable
- Free-form `extra` dict (e.g. changed fields)

The same record is mirrored to structured logs so any SIEM (Wazuh, Elastic, Loki) can index it.

## Privacy & consent

- **Consent is explicit, granular and revocable.** Citizens can revoke any consent at any time from the citizen portal — the revocation is reflected immediately via cache invalidation.
- **Data minimisation** — the API returns only what the caller is entitled to see. Citizens can only read their own record; workers cannot reach across facilities without a consent record on file.
- **Right to access** — citizens can read their record and the audit log of who has touched it.
- **Right to be forgotten** — the platform supports soft-delete and tombstoning; physical erasure is a database-level operation deliberately gated by a ministry-level admin action.

## Idempotency & retry safety

Offline-first clients retry mutations. Without idempotency, a duplicate POST creates a duplicate record. Every unsafe HTTP method honours the `Idempotency-Key` header — the response is cached for 24 hours and replayed on retry. This is enforced in `app/middleware/idempotency.py`.

## Resilience as a security property

A system that crashes under load is also insecure: it cannot keep its audit promises. The resilience patterns (circuit breakers, bulkheads, graceful degradation) ensure that under failure conditions, the system never silently loses an audit entry, never exposes a partially-failed mutation, and always declares its state to the caller (response headers carry breaker hints).

## Incident response

The breach playbook is its own document: [INCIDENT_RESPONSE.md](./INCIDENT_RESPONSE.md). It covers detection signals, the NIST 800-61r2 phases (preparation → detection → containment → eradication → recovery → post-incident), forensic preservation rules, the PDPO notification template (DPPA s.19, 72-hour clock), and the communication tree. [RUNBOOK.md RB-13](./RUNBOOK.md#rb-13) is the on-call entry point that triggers it.

This SECURITY.md describes the *posture*. INCIDENT_RESPONSE.md describes the *procedure*. They are kept separate so a posture update does not silently rewrite the playbook and vice versa.

## Known advisories and waivers

We treat the OSV / GHSA / Dependabot feeds as authoritative for dependency
vulnerabilities. Findings that we have evaluated and either patched or
deliberately accepted are recorded here.

| Date       | Advisory               | Package         | Disposition                                                                                                   |
| ---------- | ---------------------- | --------------- | ------------------------------------------------------------------------------------------------------------- |
| 2026-05-20 | GHSA-267c-6grr-h53f and 12 sibling advisories | `next < 16.2.6` | **Patched.** Bumped `next` from 16.2.3 to ^16.2.6; transitive `postcss` resolved to 8.5.x via package overrides. |
| 2026-05-20 | GHSA-qx2v-qp2m-jg93    | `postcss < 8.5.10` | **Patched** via the same override.                                                                          |
| 2026-05-20 | PYSEC-2025-183 / CVE-2025-45768 | `pyjwt ≤ 2.12.1` (current latest) | **Accepted, not exploitable in our usage.** The CVE describes an alleged algorithm-confusion attack; PyJWT maintainers consider the report disputed and no patched version has been published. HealthSync signs and verifies tokens with HS256 only via `app.core.security` (the algorithm is hard-coded in `_decode_token`, `algorithms=["HS256"]`), and the `options={"require": ["sub", "role", "exp", "iat"]}` claim allow-list further constrains the parser — the confusion vector cannot be triggered. **Follow-up:** monitored monthly via Dependabot; revisit when an upstream fix lands or when a non-disputed CVE supersedes this one. |

Process: every Dependabot alert is triaged within five working days. Patched
findings ship in the next merge to `main`; accepted findings are added to this
table with the technical justification.

## Penetration testing & vulnerability management

The platform's vulnerability posture is governed by a **layered, time-bounded** programme. The Showcase panel and MoH / NITA-U reviewers can verify each layer against either the Dependabot / OSV-Scanner feed (continuous) or the artefacts under [`docs/incidents/`](./) (scheduled).

### Continuous (always-on)

| Activity                                    | Cadence              | Owner                | Evidence                                                                                                                  |
| ------------------------------------------- | -------------------- | -------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| Dependabot ingestion (uv, npm, Actions, Docker) | Weekly (Mon 06:00 EAT) | Engineering on-call  | `.github/dependabot.yml`; advisories table above; PR labels.                                                              |
| OSV-Scanner in CI                            | Every push to `main` and every PR | CI workflow          | `.github/workflows/ci.yml` (non-blocking, surfaces advisories in the job log).                                            |
| Static analysis                              | Every PR             | Engineering on-call  | `ruff` (Python), ESLint (TS), `mypy` (Python type-check). Non-blocking but tracked.                                       |
| Secrets scanning                             | Pre-commit + CI       | Engineering on-call  | Pre-commit `detect-secrets` hook; CI job (planned, pre-pilot).                                                            |
| SBOM generation                              | Per release           | Engineering on-call  | Generated by release workflow per [DEPLOYMENT.md](./DEPLOYMENT.md); attached to the GitHub release as `sbom.cdx.json`.    |

### Scheduled (point-in-time)

| Activity                                                       | Cadence                                                  | Owner                            | Evidence                                                                                                                                                                                                     |
| -------------------------------------------------------------- | -------------------------------------------------------- | -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **External penetration test** (CERT-UG accredited vendor)       | Pre-pilot (target: 2026-09); annual thereafter           | DPO + Engineering lead           | Five-day engagement covering OWASP ASVS L2 + DPPA-specific concerns. Report archived in `docs/incidents/pentest-YYYY-MM-DD.md` (sanitised version public; full report restricted).                            |
| **Internal threat-model review**                                 | Quarterly                                                | Security & Privacy Review (per TEAM.md §3) | Updates to [THREAT_MODEL.md](./THREAT_MODEL.md) §4 STRIDE rows and §6 residual-risk register, with evidence in the meeting minutes.                                                                          |
| **Restore drill** (validates RPO/RTO + backup integrity)        | Quarterly                                                | SRE                              | `docs/incidents/restore-drill-YYYY-MM-DD.md` per [BACKUP_RESTORE.md §6](./BACKUP_RESTORE.md#6-quarterly-restore-drill).                                                                                       |
| **Tabletop exercise** (incident response rehearsal)             | Twice a year (pre-pilot, mid-year)                       | DPO + IC                         | `docs/incidents/tabletop-YYYY-MM-DD-<scenario>.md` per [INCIDENT_RESPONSE.md §7](./INCIDENT_RESPONSE.md#7-tabletop-exercises).                                                                                |
| **Code review by Makerere COCIS faculty**                         | Pre-pilot (target: 2026-09)                              | Engineering lead                 | Report archived under `docs/incidents/code-review-2026-09.md` per [COMPLIANCE.md §E](./COMPLIANCE.md#e-independent-verifications-scheduled-before-pilot).                                                     |
| **DPIA external review** (Ugandan privacy counsel)               | Pre-pilot (target: 2026-09)                              | DPO                              | Report + updated [DPIA.md](./DPIA.md).                                                                                                                                                                       |
| **NITA-U technical alignment review**                            | Pre-national (target: 2027-12)                           | MoH liaison + NITA-U             | Joint review minutes; alignment letter for sovereign-hosting profile.                                                                                                                                         |

### Triage SLA

- **Critical (CVSS ≥ 9.0):** patched or mitigated within **24 hours**; advisories table row within the same business day; if not patchable, IR may activate.
- **High (CVSS 7.0–8.9):** patched or mitigated within **5 working days**; advisories table row within the same business day.
- **Medium (CVSS 4.0–6.9):** patched in the next regular release; advisories table row within five working days.
- **Low (CVSS < 4.0):** patched at the next major bump or accepted with rationale; advisories table row within ten working days.

If a CVE is *disputed* upstream (e.g. PyJWT CVE-2025-45768) the row carries an explicit acceptance rationale and a monthly re-review entry. The current accepted row is auditable above.

## Zero-trust elements

The platform implements the following zero-trust principles in code today; the remaining items are tracked under the [Roadmap Closure Plan in THREAT_MODEL.md §7](./THREAT_MODEL.md#7-roadmap-closure-plan).

| Principle                                                    | Status      | Where it's implemented                                                                                                                                                                                                                                                                                |
| ------------------------------------------------------------ | ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Verify explicitly on every request**                       | Implemented | `require_role(...)` at every endpoint ([ACCESS_CONTROL.md](./ACCESS_CONTROL.md)). No session-cookie trust; every request carries a fresh JWT verification.                                                                                                                                              |
| **Least privilege**                                           | Implemented | Five-tier RBAC; citizen-self rule; facility scoping at write time; `analytics/*` returns aggregates only.                                                                                                                                                                                              |
| **Assume breach**                                             | Implemented | Audit log on every access; supply ledger is forensic-grade (hash-chained); incident-response playbook ([INCIDENT_RESPONSE.md](./INCIDENT_RESPONSE.md)) treats compromise as a planning premise, not an edge case.                                                                                       |
| **Encrypt in transit**                                        | Implemented | TLS 1.2+ at the edge; HSTS preload-ready; CORS allow-listed; no plaintext on the wire.                                                                                                                                                                                                                |
| **Encrypt at rest**                                           | Partial     | Backups at-rest encrypted via deployment-environment KMS ([BACKUP_RESTORE.md](./BACKUP_RESTORE.md)); field-level encryption for HIV / mental-health fields is **planned** (RR-roadmap; see "What is *not* in this prototype" below).                                                                  |
| **Strong identity for services**                              | Partial     | Service-to-service via private network ACLs in pilot tier; **mTLS planned** for the national tier in the cluster-mesh layer.                                                                                                                                                                            |
| **Continuous validation & telemetry**                         | Implemented | OpenTelemetry traces, structured logs, SLO-driven alerts ([OBSERVABILITY.md](./OBSERVABILITY.md)). Detection signals AL-12…AL-14 are zero-trust behavioural anomalies (cross-facility reads, bulk reads, off-hours bursts) that classify into IR-01.                                                  |
| **Device posture**                                            | Partial     | Session-token binding; **device attestation (FIDO L3 / WebAuthn)** planned for the production worker fleet — see [THREAT_MODEL.md RR-10](./THREAT_MODEL.md#6-residual-risk-register).                                                                                                                  |
| **Network micro-segmentation**                                | Planned (national) | Pilot single-host uses VPC-internal ACLs; national-tier deployment uses NetworkPolicies + service-mesh (Istio / Linkerd) to enforce per-pod ingress/egress.                                                                                                                                          |
| **Differential privacy for analytics**                        | Planned     | See [ARCHITECTURE.md §12](./ARCHITECTURE.md) — `analytics/*` already returns only aggregates; differential-privacy noise injection is planned for cohort sizes below a configurable k-anonymity threshold.                                                                                              |

## What is *not* in this prototype (and is on the production roadmap)

- **Hardware security modules** (HSM) for JWT signing keys
- **End-to-end encryption** at the field level for the most sensitive records (HIV status, mental health)
- **Penetration test report**
- **SOC 2 / ISO 27001 alignment evidence**
- **DDoS / Web Application Firewall** in front of the API gateway
- **Tamper-evident anchor** of the supply ledger chain head to a public ledger (Stellar / Merkle anchor)

These are not blockers for the National Innovator Registry — they are line items for a production deployment.
