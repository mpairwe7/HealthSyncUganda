## Summary

<!-- One or two sentences describing the change and why. -->

## Type of change

- [ ] Feature
- [ ] Bug fix
- [ ] Refactor (no behaviour change)
- [ ] Documentation
- [ ] Build / CI / infra

## Patient & data-protection impact

- [ ] No PHI involved.
- [ ] PHI involved — DPIA updated at `docs/DPIA.md`.
- [ ] FHIR profile or terminology touched — conformance suite passes
      (`scripts/fhir-conformance.sh`).

## Offline / resilience

- [ ] Works offline (mutations queued, no network calls on the critical path).
- [ ] Network-dependent — degrades gracefully (circuit breaker, timeout, retry).

## Checklist

- [ ] Tests added or updated.
- [ ] `make typecheck` and `make lint` are clean.
- [ ] User-facing docs updated (`docs/API.md`, `docs/RUNBOOK.md`, etc.).
- [ ] ADR added under `docs/adr/` if this is an architectural decision.

## Trace ID / logs (for bug fixes)

<!-- Paste the X-Trace-Id and a sanitised log excerpt that demonstrates the
     issue, then the same after your fix. -->
