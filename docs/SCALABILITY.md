# Scalability & Capacity

This document replaces hand-wavey "designed to scale" with **concrete numbers** the Showcase panel can verify.

The targets here are the *evidence base* for the Scalability dimension; the runnable scripts in `scripts/loadtest-*.sh` reproduce them.

---

## 1. Performance budget

| Endpoint | p50 | p95 | p99 | At rate | On |
|---|---|---|---|---|---|
| `GET /healthz` | < 2 ms | < 10 ms | < 30 ms | 500 rps | 1 vCPU, 1 GB |
| `GET /api/v1/patients?q=…` | < 30 ms | < 150 ms | < 350 ms | 200 rps | 1 vCPU, 1 GB |
| `GET /api/v1/patients/{id}` | < 15 ms | < 80 ms | < 200 ms | 200 rps | 1 vCPU, 1 GB |
| `GET /fhir/Patient/{id}` | < 25 ms | < 120 ms | < 300 ms | 200 rps | 1 vCPU, 1 GB |
| `POST /api/v1/encounters` | < 80 ms | < 250 ms | < 500 ms | 100 rps | 1 vCPU, 1 GB |
| `GET /api/v1/analytics/encounters-by-district` (cached) | < 10 ms | < 30 ms | < 80 ms | 300 rps | 1 vCPU, 1 GB |
| `GET /api/v1/analytics/encounters-by-district` (cold) | < 250 ms | < 700 ms | < 1.2 s | n/a | First request after cache miss |

These are *single-replica* targets. The cost model below assumes 2 replicas behind a load balancer per pilot district, with linear scaling thereafter.

## 2. Capacity planning

### National-scale sizing (target: full Uganda rollout, 2028+)

| Dimension | Assumption | Sized for |
|---|---|---|
| Facilities | 6,937 (MoH 2024) | 10,000 with growth |
| Citizens | 32 million NIN-bearing adults (2026) | 45 M by 2030 |
| Annual encounters | 35 M (HSDP III estimate) | 50 M |
| Concurrent users at peak | 30,000 (workers + citizens) | 50,000 |
| Peak request rate | 5,000 req/s | 10,000 req/s |
| Database growth | ~50 GB / year of FHIR resources | 500 GB after 10 years |
| Audit log growth | ~30 GB / year | 300 GB after 10 years |

### Instance sizing recommended

| Tier | API replicas | Postgres | Redis | Notes |
|---|---|---|---|---|
| **Pilot (2 districts)** | 2 × (1 vCPU, 1 GB) | 1 × (2 vCPU, 8 GB, 200 GB SSD) | 1 × (1 vCPU, 2 GB) | ~30 facilities |
| **Regional (10 districts)** | 4 × (2 vCPU, 2 GB) | Primary + 1 read-replica (each: 4 vCPU, 16 GB, 1 TB SSD) | Sentinel HA, 3 × (1 vCPU, 4 GB) | ~600 facilities |
| **National (130 districts)** | 12 × (4 vCPU, 4 GB), HPA-enabled | Patroni cluster: 3-node, each (8 vCPU, 64 GB, 4 TB SSD), PgBouncer pool | Sentinel HA, 3 × (2 vCPU, 8 GB) | 6,937+ facilities |

### Cost model — NITA-U Government Cloud

NITA-U pricing is non-public; the figures below use comparable AWS Cape Town (af-south-1) on-demand pricing as a proxy.

| Tier | Monthly compute | Monthly bandwidth | Monthly storage | **Monthly UGX** | **Monthly USD** |
|---|---|---|---|---|---|
| Pilot | $35 | $5 | $10 | ~185k | $50 |
| Regional | $280 | $40 | $80 | ~1.5 M | $400 |
| National | $2,200 | $400 | $700 | ~12 M | $3,300 |

Production-grade NITA-U hosting at the National tier is well within the typical line item for a single MoH ICT programme.

## 3. Why these numbers are reachable

| Design choice | Effect on the budget |
|---|---|
| Stateless API | Linear horizontal scale |
| Async I/O (FastAPI + asyncpg) | Single replica handles thousands of concurrent connections |
| Connection pool (10 + 20 overflow per replica) | Postgres handles burst |
| Redis-cached analytics (60 s TTL) | Dashboards do not hit Postgres on every page view |
| `pg_trgm` GIN index on family names | Fuzzy search stays sub-100 ms even at 30 M rows |
| Indexed lookups on NIN, district, started_at | All hot reads are index-only scans |
| Bulkheads (16-wide per upstream) | A slow NIRA cannot saturate the API |
| Circuit breakers | Outage tail-latency bounded, not unbounded |

## 4. How to reproduce

```bash
# Single-replica baseline using `vegeta`:
scripts/loadtest-baseline.sh

# Scale-out demonstration (2 → 3 replicas):
scripts/loadtest-scaleout.sh

# Cache effectiveness (cold vs warm analytics):
scripts/loadtest-analytics.sh
```

Each script writes a Markdown report to `loadtest-results/$(date +%F)/` with the p50/p95/p99 histogram and latency chart for inclusion in the submission packet.

## 5. Operational SLOs (post-pilot)

| SLO | Target | Error budget |
|---|---|---|
| API availability | 99.5 % monthly | ~3.6 h / month |
| API latency p95 | < 250 ms over 30 days | 5 % of requests can exceed |
| Data integrity | 0 unrecoverable patient records | None |
| Audit log durability | 0 lost rows | None — append-only with chain verification |
| Recovery Point Objective (RPO) | 15 minutes | n/a |
| Recovery Time Objective (RTO) | 60 minutes | n/a |

## 6. Known scaling limits & what we will do

| Limit | Where it bites first | Resolution |
|---|---|---|
| Single Postgres primary | Writes saturate at ~5 k tps | Patroni multi-write or Citus shard by district (Phase 4) |
| Redis token-bucket rate limit | Per-client, 600 req/min | Tunable via env; production tier raises to 6,000 |
| ULID PK on patients | Storage growth | n/a — ULIDs are 26 B; even 50 M rows is < 2 GB of keys |
| Audit log size | 300 GB after 10 years | Cold-tier archive to S3-compatible store after 13 months |
| Frontend bundle | Cold-start time on 3G | Aggressive splitting + service-worker pre-cache; ≤ 200 KB gzipped initial JS |
