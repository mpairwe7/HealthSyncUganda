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

## What is *not* in this prototype (and is on the production roadmap)

- **Hardware security modules** (HSM) for JWT signing keys
- **End-to-end encryption** at the field level for the most sensitive records (HIV status, mental health)
- **Penetration test report**
- **SOC 2 / ISO 27001 alignment evidence**
- **DDoS / Web Application Firewall** in front of the API gateway
- **Tamper-evident anchor** of the supply ledger chain head to a public ledger (Stellar / Merkle anchor)

These are not blockers for the National Innovator Registry — they are line items for a production deployment.
