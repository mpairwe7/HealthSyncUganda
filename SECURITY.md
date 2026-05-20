# Security policy

HealthSync Uganda handles **Personal Health Information (PHI)** for citizens of
Uganda. We take vulnerability reports seriously and run a coordinated
disclosure programme.

## Supported versions

| Version       | Supported with security fixes? |
| ------------- | ------------------------------ |
| `main`        | ✅ yes                          |
| Latest tagged | ✅ yes (12 months)              |
| Older         | ❌ no                           |

## Reporting a vulnerability

**Do not open a public GitHub issue.** Public issues let attackers weaponise
the bug before we can patch.

Please report security issues by one of:

1. **Encrypted email** to `security@healthsync.ug` using the PGP key fingerprint
   `4F12 0E9A 8B3C  D7F1 6A4D  9F11 8C20 71B5 6C8A 0EE3`. The key is on
   `keys.openpgp.org` under the same address.
2. **GitHub Security Advisories** — use the *"Report a vulnerability"* button
   on the repository's *Security* tab. This is the preferred channel.

Please include:

- A description of the vulnerability and its potential impact.
- Steps to reproduce, including affected endpoints, payloads, and the API
  version returned by `GET /healthz`.
- The `X-Trace-Id` from any reproducing request (if available).
- Whether the vulnerability appears to affect **PHI confidentiality**,
  **PHI integrity**, **availability**, or **auditability** — flag this clearly
  because it changes our SLA.

## What you can expect

| Step                | Target time        |
| ------------------- | ------------------ |
| Acknowledge receipt | within 48 hours    |
| Triage assessment   | within 5 days      |
| Status updates      | at least weekly    |
| Fix in `main`       | 30 days (critical) / 90 days (high) / 180 days (medium-low) |
| Public disclosure   | by mutual agreement, default 90 days after fix |

We will credit you in the advisory unless you request otherwise.

## Scope

In scope:

- The HealthSync Uganda monorepo (`backend/`, `frontend/`, `infra/`).
- Officially published container images and Helm charts.
- The reference FHIR validator and conformance test suite.

Out of scope:

- Test instances at `*.demo.healthsync.ug` (these are reset nightly and contain
  only synthetic data).
- Third-party services we integrate with (NIRA, DHIS2, RxNav). Please report
  to those upstreams directly.
- Denial-of-service via volumetric attack alone.
- Reports from automated scanners without a working proof-of-concept.

## Safe harbour

We will not pursue legal action against researchers who:

- Make a good-faith effort to avoid privacy violations, data destruction, and
  service interruption.
- Comply with this policy.
- Give us reasonable time to remediate before public disclosure.

This safe harbour does **not** extend to actions that:

- Access, modify, or exfiltrate **real** patient data. Use only synthetic
  fixtures from `backend/scripts/seed_*.py`.
- Disrupt service for live ministry users.

## Personal data and the DPPA

If you discover PHI exposure, **stop immediately** and report via the channels
above. Do not retain, share, or screenshot the data. Reproduce with synthetic
data only. We are required under Uganda's Data Protection and Privacy Act 2019
to notify the Personal Data Protection Office (PDPO) within 72 hours of
confirmed PHI exposure; your prompt report helps us meet that obligation.

## Hall of fame

Researchers who have responsibly disclosed issues will be listed at
`docs/SECURITY_HALL_OF_FAME.md` (with consent).
