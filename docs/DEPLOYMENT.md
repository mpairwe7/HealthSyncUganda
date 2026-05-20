# Deployment guide

**Audience:** NITA-U cloud engineers, pilot facility ICT focal points, devops staff packaging the platform for production.
**Status:** v1, valid for the showcase build (25 June 2026) and the 8-week pilot.

This guide covers three deployment shapes:

1. **Laptop** — the demo / development path, used in `make full`. Single host, docker compose.
2. **Pilot (single VM)** — recommended for 2-3 districts, ≤ 30 facilities. Hardened single host with managed backups.
3. **National (Kubernetes)** — for the full rollout. Stateless API + managed Postgres + managed Redis + observability stack. Documented as a destination, not implemented as code in this prototype.

Each shape uses the **same container images and the same configuration model**. The only difference is the orchestration layer and the security envelope.

---

## 1. Build artefacts

The repository builds two container images:

| Image                                          | Source              | Base                    | Size (target) |
| ---------------------------------------------- | ------------------- | ----------------------- | ------------- |
| `ghcr.io/mpairwe7/healthsync-backend:<sha>`   | `backend/Dockerfile`  | `python:3.12-slim` (multi-stage) | ~180 MB |
| `ghcr.io/mpairwe7/healthsync-frontend:<sha>`  | `frontend/Dockerfile` | `node:20-alpine` (multi-stage)   | ~120 MB |

Images are reproducible — `uv.lock` and `bun.lock` pin every byte. Production tags are `:<semver>` published on releases.

### Build locally

```bash
docker compose build --no-cache backend frontend
```

### Sign and publish (release pipeline)

The release workflow (`.github/workflows/release.yml`) does:

1. Build multi-arch (`linux/amd64`, `linux/arm64`).
2. Sign with cosign keyless against the GitHub OIDC issuer.
3. Generate SBOM in SPDX JSON via syft.
4. Publish to `ghcr.io/mpairwe7/...`.
5. Attach the SBOM and signature to the GitHub release.

---

## 2. Shape A — laptop / showcase

For the 25 June showcase and any "kick the tyres" walkthrough.

```bash
git clone https://github.com/mpairwe7/HealthSyncUganda.git
cd HealthSyncUganda
cp .env.example .env
sed -i.bak "s|change-me-to-32-bytes-of-randomness-please|$(openssl rand -hex 32)|" .env

make full          # docker compose --profile full up --build
make seed          # idempotent demo data
make preflight     # smoke test
```

Open <http://localhost:3000> for the UI and <http://localhost:8000/docs> for the API.

Reset between rehearsals:

```bash
make reset && make seed
```

Hardware floor: 4 vCPU, 8 GB RAM, 10 GB disk. The full stack draws ~3 GB resident under demo load.

---

## 3. Shape B — pilot (single VM)

The pilot deployment target. Designed for 2-3 districts, up to ~5 000 daily encounters, mounted on a NITA-U VM or an on-prem Linux host.

### 3.1 Reference topology

```
┌──────────────────────────── pilot-vm (Ubuntu 22.04 LTS, 8 vCPU, 16 GB RAM) ───────────────────────────┐
│                                                                                                       │
│  ┌─ Caddy (TLS, reverse proxy) ──────────────┐                                                        │
│  │   :443 → frontend  :443 → backend          │                                                        │
│  └────────────────────────────────────────────┘                                                        │
│                                                                                                       │
│  ┌─ frontend (Next.js production build) ─────┐    ┌─ backend (uvicorn, 4 workers) ─┐                  │
│  │   :3000, served behind Caddy               │    │   :8000, behind Caddy           │                 │
│  └────────────────────────────────────────────┘    └────────────────────────────────┘                 │
│                                                                                                       │
│  ┌─ Postgres 16 (pgdata on encrypted disk) ──┐    ┌─ Redis 7 (AOF on encrypted disk) ┐                │
│  │   :5432, only listens on the docker net    │    │   :6379, same                    │                │
│  └────────────────────────────────────────────┘    └────────────────────────────────┘                 │
│                                                                                                       │
│  ┌─ Loki + Tempo + Prometheus + Grafana ─────┐                                                        │
│  │   Bundled observability — exposed at :3001 over an internal-only IP                                 │
│  └────────────────────────────────────────────┘                                                        │
│                                                                                                       │
│  ┌─ Backup agent (cron) ─────────────────────┐                                                        │
│  │   pg_dump + redis BGSAVE → object store    │                                                        │
│  └────────────────────────────────────────────┘                                                        │
└───────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Prerequisites

- Ubuntu 22.04 LTS (other modern distros work, but this is what we test on).
- Docker 24+ and Docker Compose v2.
- A registered DNS name pointing at the VM (e.g. `pilot.healthsync.go.ug`).
- An object store for backups (NITA-U S3-compatible or AWS S3).

### 3.3 Install

```bash
git clone https://github.com/mpairwe7/HealthSyncUganda.git /opt/healthsync
cd /opt/healthsync
sudo cp deploy/pilot/.env.pilot.template /etc/healthsync/.env
sudo vim /etc/healthsync/.env            # rotate SECRET_KEY, set DB password, set DOMAIN, …
sudo cp deploy/pilot/healthsync.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now healthsync
```

(`deploy/pilot/` is added in the pilot prep PR; the contents are the production-tuned `docker-compose.pilot.yml`, a `Caddyfile`, and the systemd unit.)

### 3.4 First-boot checklist

- [ ] `make preflight` returns green on the VM itself.
- [ ] `make seed` ran exactly once (production environments override the seed-admin password).
- [ ] TLS certificate is valid (`curl -I https://<your-domain>`).
- [ ] Backups directory in the object store contains a `pg_dump-<date>.sql.gz`.
- [ ] Grafana shows traffic on the overview dashboard.
- [ ] The ministry contact list in `docs/TEAM.md` is wired into the on-call rota.

### 3.5 Operating notes

- Disk encryption: the `pgdata` and `redis` volumes are mounted on LUKS-encrypted disks. Key escrow with NITA-U per their SOP.
- Network: only :443 is exposed. The observability stack (:3001) listens on an internal-only IP and is reachable via a NITA-U VPN.
- Resource ceilings are set in `docker-compose.pilot.yml`. Tune with the values from [SCALABILITY.md](./SCALABILITY.md).

---

## 4. Shape C — national (Kubernetes)

The target for the full national rollout (post-pilot). Documented here as the destination so the pilot deployment does not paint us into a corner.

### 4.1 Cluster topology

| Concern              | Choice                                                       | Reason                                                                       |
| -------------------- | ------------------------------------------------------------ | ---------------------------------------------------------------------------- |
| Orchestrator         | Kubernetes 1.30+                                              | Standard, NITA-U-supported, no vendor lock-in.                              |
| Compute              | At least three worker nodes per region, anti-affinity rules. | Tolerate single-node failure.                                                |
| Database             | Patroni-managed Postgres 16 cluster (3 nodes) or managed RDS-equivalent | Failover automation, point-in-time recovery.                  |
| Cache                | Redis 7 Sentinel or managed Redis                            | Cluster mode is not required at this scale.                                  |
| Object store         | NITA-U S3-compatible                                         | For backups, SBOMs, audit exports.                                           |
| Ingress              | Envoy / NGINX Ingress + cert-manager                         | ACME-based TLS, header injection for trace propagation.                      |
| Observability        | Prometheus + Tempo + Loki + Grafana                          | Same stack as pilot; the dashboards travel unchanged.                        |
| Secrets              | external-secrets backed by Vault                              | One source of truth, audited access.                                         |
| Policy               | OPA Gatekeeper                                                | Enforce required labels, container image signing.                            |
| Multi-region         | Active / passive per the data-residency clause in DPIA       | Data stays in Uganda.                                                        |

### 4.2 Helm chart

The Helm chart lives under `infra/helm/healthsync/`. Values that change per environment:

```yaml
backend:
  replicaCount: 6
  resources:
    requests: { cpu: 500m, memory: 1Gi }
    limits:   { cpu: 2,    memory: 2Gi }
  config:
    DATABASE_URL: postgresql+asyncpg://...
    REDIS_URL:    redis://...
    NIRA_BASE_URL: https://api.nira.go.ug
    DHIS2_BASE_URL: https://dhis2.moh.go.ug

frontend:
  replicaCount: 3
  resources:
    requests: { cpu: 200m, memory: 512Mi }

ingress:
  hosts: [ api.healthsync.go.ug, app.healthsync.go.ug ]
  tlsIssuer: letsencrypt-prod
```

(The chart is on the roadmap, not in this prototype build.)

### 4.3 Capacity planning

See [SCALABILITY.md](./SCALABILITY.md) for the performance budget, national sizing model, and cost projection.

---

## 5. Configuration model

All three shapes read the same environment variables. The full list is in `.env.example`. The most security-sensitive ones, summarised:

| Variable                                    | Local default                                       | Production rule                                          |
| ------------------------------------------- | --------------------------------------------------- | -------------------------------------------------------- |
| `SECRET_KEY`                                | random — must be rotated                            | 32+ bytes from the secret store; rotate quarterly.       |
| `POSTGRES_PASSWORD`                         | `healthsync`                                        | Set in secret store; never in git.                       |
| `DATABASE_URL`                              | localhost                                           | Points at the managed/internal Postgres.                 |
| `REDIS_URL`                                 | localhost                                           | Points at the managed/internal Redis.                    |
| `NIRA_BASE_URL` / `NIRA_API_KEY`            | mock                                                | Real NIRA URL + per-environment API key.                 |
| `DHIS2_BASE_URL` / `DHIS2_USERNAME/PASSWORD`| mock                                                | Real DHIS2 credentials, scoped to the org unit allowed.  |
| `OTEL_EXPORTER_OTLP_ENDPOINT`               | unset                                               | Internal collector address.                              |
| `CIRCUIT_BREAKER_FAILURE_THRESHOLD`         | `5`                                                 | Tune per dependency profile (see RESILIENCE.md).         |

Secrets must reach the container via the orchestrator's secret mechanism (Docker secrets / Kubernetes Secrets backed by Vault), never via process arguments.

---

## 6. Backups, recovery, and DR

### 6.1 RPO / RTO targets

| Target                | Value         | Reference   |
| --------------------- | ------------- | ----------- |
| RPO                   | ≤ 15 minutes  | NFR-021     |
| RTO                   | ≤ 60 minutes  | NFR-022     |
| Retention             | 30 d daily + 12 m monthly + 7 y annual | NDHS records retention guidance |

### 6.2 What we back up

- **Postgres**: continuous WAL archival + nightly `pg_dump` to the object store. Both encrypted at rest.
- **Redis**: AOF rewrite nightly; treated as a soft-state cache, so the recovery contract is "warm cache loss is acceptable".
- **Application logs**: 30 d retention in Loki + 1 y archive in the object store.
- **Audit log**: never truncated. Retention follows DPPA 2019 and NDHS record retention guidance.

### 6.3 Restore drill

The restore is a quarterly exercise, documented in `docs/restore-drill.md` (in flight). The summary:

1. Spin up a parallel environment from the latest object-store backup.
2. Run `scripts/preflight.sh` + `scripts/fhir-conformance.sh` against it.
3. Cut over DNS only after a clinical reviewer accepts the recovered state.
4. Decommission the old environment after the verification window.

---

## 7. Observability in production

A standardised observability bundle ships with the platform.

### 7.1 Telemetry sources

- **Traces** — OpenTelemetry SDK in the backend; exporter to OTLP gRPC. Sampled `parentbased_always_on` in pilot, `parentbased_traceidratio:0.1` at national scale.
- **Metrics** — Prometheus scrape on `/metrics`. Request rate, latency p50/p95/p99, error rate, breaker state, queue depth, DB pool saturation.
- **Logs** — `structlog` JSON. Always carries `trace_id`, `service`, `version`, `actor_id` (when authenticated).

### 7.2 Dashboards

The Grafana dashboards are in `infra/grafana/dashboards/`:

- `healthsync-overview.json` — request rate, error rate, latency, by route.
- `resilience.json` — circuit breakers, retries, DHIS2 queue depth.
- `clinical-flows.json` — encounters/day per district, immunisation coverage, low-stock alerts.
- `audit.json` — PHI access count, by role, by purpose-of-use.

### 7.3 Alerts

Alertmanager rules in `infra/alerts/`:

| Alert                                                  | Severity  | Threshold                                              | Runbook |
| ------------------------------------------------------ | --------- | ------------------------------------------------------ | ------- |
| API error rate > 1 % for 5 min                         | SEV-2     | recording rule                                         | RB-01   |
| `/readyz` red for > 2 min                              | SEV-1     | blackbox probe                                         | RB-01   |
| Breaker open > 30 min on `dhis2` or `nira`             | SEV-2     | metric                                                  | RB-02   |
| DHIS2 outbox depth > 5 000                             | SEV-2     | metric                                                  | RB-03   |
| Audit-log write failure                                | SEV-1     | log-based                                              | RB-13   |
| Ledger verification job failure                        | SEV-1     | scheduled job                                          | RB-07   |
| Backup not completed in last 26 h                       | SEV-2     | scheduled job                                          | RB-09   |

---

## 8. Network and security envelope

- **TLS 1.2+** mandatory at the ingress.
- **mTLS** between backend ↔ database when both are on Kubernetes (managed Postgres providers vary).
- **Egress** is allow-listed: NIRA endpoints, DHIS2 endpoints, NTP, OS package mirrors. No outbound to the public internet from production pods.
- **WAF** at the NITA-U cloud layer (managed) — blocks the OWASP top 10 fingerprints by default.
- **IP allow-list** on `/admin` and `/metrics`.
- **Container security**: distroless images, non-root user, read-only root filesystem, dropped capabilities, signed images per OPA Gatekeeper policy.
- **Image provenance**: cosign + SBOM verified at admission.

The detailed control catalogue is in [COMPLIANCE.md](./COMPLIANCE.md) and [SECURITY.md](./SECURITY.md).

---

## 9. Pre-go-live checklist

Before a pilot facility goes live the following must be ticked off:

- [ ] DPIA reviewed and signed by the DPO.
- [ ] Letter of intent on file with the facility's medical superintendent.
- [ ] NIN identifier strategy confirmed with NIRA liaison.
- [ ] DHIS2 org unit mapped; staff DHIS2 credentials provisioned.
- [ ] Postgres backup tested via the quarterly restore drill.
- [ ] Pilot staff trained (5-day curriculum in `docs/clinical/training.md`, in flight).
- [ ] On-call rota staffed and tested.
- [ ] DPPA breach-notification path tested (tabletop drill).
- [ ] `make preflight` returns green from the facility's network.
- [ ] Hardware/network resilience verified (UPS, failover SIM/router).
- [ ] Citizen consent posters in English + Luganda installed at registration desks.

---

## 10. Decommissioning

When a deployment is retired (e.g. moving from pilot host to national cluster):

1. Take a final encrypted backup, write its checksum to the object store, and notify the DPO.
2. Export the audit log in the format required by PDPO (DPPA §28).
3. Run `scripts/wipe-and-verify.sh` on the disks (cryptographic erase if disks are reused, physical destruction otherwise).
4. Update the asset register and the DPIA processor inventory.

Decommissioning is not "delete the docker containers" — it is a documented, audited handover.
