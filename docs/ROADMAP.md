# Roadmap

A 5-year commitment, irrespective of selection outcome. We will maintain HealthSync as an active open-source project through **December 2031**.

## Phase 1 — Showcase prototype (now → 25 June 2026)

- **Engineering**: ship FHIR R4 + offline PWA + supply ledger + resilience patterns *(done — see `make preflight`)*.
- **Governance**: ship DPIA, MoH alignment matrix, control mapping *(done)*.
- **Localisation**: ship English + Luganda for citizen portal *(done — `frontend/src/lib/i18n/`)*.
- **Independent review**: 5-day external security review by a Ugandan firm *(in flight)*.
- **MoH endorsement**: secure ≥1 letter of intent from a facility / DHO *(in flight)*.

## Phase 2 — Two-district pilot (Q3 2026 – Q1 2027)

- 2 pilot districts: 1 in Northern Uganda (Gulu recommended), 1 in Central/Western (Mbarara or Wakiso).
- ~30 facilities across HC II → RRH levels.
- Real NIRA OIDC integration (replacing the demo mock).
- Real DHIS2 instance integration (replacing the demo mock).
- Field-level encryption for stigma-sensitive observations (HIV status, mental health, GBV).
- Penetration test report (post-pilot v1).
- 5-participant nurse usability study (already prepared in `docs/USABILITY_STUDY.md`).
- USSD bridge for feature-phone citizens (read-only initially).

## Phase 3 — Regional scale (Q2 2027 – Q4 2027)

- 10 districts.
- DHIS2 Tracker bi-directional sync.
- OpenMRS bridge for existing EMR deployments (Mulago, Lacor).
- AEFI (Adverse Events Following Immunisation) module on top of the immunisation observation pattern.
- Cold-chain temperature integration (IoT) for vaccine batches.
- Bulk-import pipeline for legacy paper records.

## Phase 4 — National rollout (2028)

- 30+ districts.
- Performance hardening per `docs/SCALABILITY.md` cost model.
- HA Postgres (patroni / managed); Redis Sentinel.
- Multi-region NITA-U deployment with active-passive failover.
- WHO ICD-11 transition path.

## Phase 5 — Long-term maintenance (2029 – 2031)

- LTS branch; security patches only on the LTS line.
- New features go to the next major.
- Annual independent audit.
- Annual DPIA review.

## Capability extensions (out of MVP, prioritised by demand)

| Capability | Earliest delivery | Drivers |
|---|---|---|
| Telemedicine (async store-and-forward) | Q4 2027 | Network reality in rural HC II/III |
| Genomics / research data | Q2 2028 | Separate consent scope; partner research institutions |
| Insurance / NHIS integration | Q3 2028 | Pending NHIS legislation |
| AI clinical decision support | Q4 2028 | Regulatory clarity on AI/ML in health |
| Maternal-mortality early warning | Q2 2027 | High-impact; modelled on existing Mama Doc deployments |
| TB contact tracing module | Q3 2027 | NTLP partnership |

## Decommissioning principles

If HealthSync is ever discontinued, we commit to:

1. ≥ 12-month notice to all deployed sites.
2. Open data export in FHIR R4 + Postgres dumps.
3. Migration playbook to any other open-source EMR.
4. No paywall on retained data.
