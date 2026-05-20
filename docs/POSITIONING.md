# Positioning for the Uganda National Innovator Registry

This document is for the people who will pitch HealthSync. It is *not* the product pitch — it is the meta-pitch: how to position the work so the Registry evaluation committee chooses us.

---

## 1. What the Registry actually rewards

Public information on the Uganda National Innovator Registry, the National ICT Initiatives Support Programme (NIISP), and NITA-U's prior selections suggests the committee weights, in this order:

1. **Government readiness** — Could a ministry adopt this in 6–12 months without becoming captive to a vendor?
2. **Standards alignment** — Open standards, no proprietary lock-in.
3. **Local fit** — Built for Uganda's realities (NIN, district hierarchy, language, networks).
4. **Demonstrable engineering quality** — Observability, security, audit, resilience.
5. **Scale potential** — Architecture that survives the second-year load curve.
6. **Local team capacity** — Ugandan engineers who will still be here in three years.

HealthSync was designed against this exact list. The README, the architecture doc, and the demo script reinforce each of these in turn.

---

## 2. Talking points by stakeholder

### For NITA-U (the platform host)
- Stateless containers, Helm-ready, 12-factor.
- OpenTelemetry — drops straight into NITA-U's existing observability stack.
- Postgres + Redis — they already operate both.
- No proprietary dependencies; no SaaS lock-in.
- Two-replica HA fits the existing government cloud sizing without negotiations.

### For the Ministry of Health (the data owner)
- FHIR R4 is the same standard DHIS2 Tracker uses. No translation tax.
- The platform *complements* DHIS2 and eHMIS; it does not replace either.
- Audit log is on by default — required by law.
- Citizen consent is first-class and revocable.

### For NIRA (the identity authority)
- NIN is the canonical identifier from day one — not an afterthought retrofitted on.
- The mock NIRA service in `app/api/v1/interop.py` is the same shape as the production NIRA OIDC contract. Swapping in production is a config change.

### For the Office of the President / Executive
- It works on a smartphone in a HC II with no signal.
- It saves doses, saves drugs, saves lives — concrete, demonstrable.
- It is built by Ugandans for Uganda. Sovereignty.

### For donors (USAID, GAVI, Global Fund) who often co-fund
- Open source, Apache-2.0 — funds local capacity, not foreign vendor margins.
- Telemetry & dashboards make impact measurable from day one.
- Compatible with their existing OpenHIE and DHIS2 investments.

---

## 3. Messaging matrix

| Stakeholder concern | Don't say | Say |
|---|---|---|
| "Yet another digital health platform" | "It's better than X" | "It complements DHIS2 with the patient-level layer DHIS2 doesn't have." |
| "Vendor lock-in" | "It's free" | "It's Apache-2.0. The Ministry can fork it and own it tomorrow." |
| "Will it work in Karamoja?" | "Performance is great" | "It works offline. Watch — I'll switch off Wi-Fi mid-demo." |
| "Who pays for it?" | "Donor funding" | "NITA-U cloud + a 3-year shared service model. Architecture supports both." |
| "Why your team?" | "We're experts" | "We are Ugandan engineers committed to maintaining it locally for ≥5 years." |

---

## 4. Risks & mitigation talking points

| Risk | Mitigation |
|---|---|
| Data sovereignty concerns | Default deployment is on-premise / NITA-U cloud. No data leaves Uganda. |
| Integration with legacy MoH systems | FHIR R4 is the same standard DHIS2 and OpenMRS already speak. |
| Worker training burden | Mobile-first UI, low-bandwidth, with familiar Uganda district / facility hierarchy baked in. |
| Long-term maintenance | Apache-2.0; documented; uses mainstream tech (Next.js, FastAPI, Postgres) familiar to graduates of Makerere, MUST, MUBS. |
| Security of patient data | Audit-by-default, explicit consent, NIN-bound — see `docs/SECURITY.md`. |

---

## 5. Asks at the end of the pitch

A clear ask is more memorable than a clever feature list. The asks, in priority order:

1. **Inclusion in the National Innovator Registry** — the headline.
2. **A 2-district pilot** (recommended: one in Northern Uganda, one in Central/Western) for 8 weeks.
3. **MoH sponsorship** to integrate with eHMIS / DHIS2 instances rather than the mocks.
4. **A working group seat** on the National Digital Health Strategy implementation committee — to ensure HealthSync stays aligned and useful.
5. **Co-design grant** from the Innovation Village or NIISP to staff a 4-person team for 6 months while the pilot runs.

---

## 6. What we will *not* claim

Credibility is currency. We will not claim:

- "AI-powered" or "blockchain-based" (the supply ledger is a hash chain — ready for anchoring but not currently anchored to anything public, and we say so).
- "HIPAA compliant" (HIPAA is US law). We say "designed against the Uganda Data Protection & Privacy Act."
- "Production-ready today." We say "production-quality prototype — operationally hardened with telemetry, audit and graceful degradation; not yet penetration-tested or load-tested at national scale."
- "Will replace DHIS2." We say "complements DHIS2 with the patient-level layer it deliberately doesn't have."

The committee will respect the honesty more than the bravado.
