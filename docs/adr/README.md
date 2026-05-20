# Architecture Decision Records

This directory contains the architecturally-significant decisions for
HealthSync Uganda, in the [MADR](https://adr.github.io/madr/) lightweight
format.

## Why ADRs

Anyone touching the codebase six months from now will ask "why did they choose
X over Y?" — and the answer is rarely visible in the code itself. An ADR
captures the decision **and the alternatives we rejected**, so future
maintainers can revisit the trade-off when the constraints change.

## Status lifecycle

- **Proposed** — open for review.
- **Accepted** — adopted; binding on contributors.
- **Deprecated** — superseded; kept for historical context.
- **Rejected** — considered and declined.

## When to write one

Open a new ADR when the change:

1. Affects more than one bounded context (e.g. backend ↔ frontend ↔ infra).
2. Picks a *standard* (FHIR profile, terminology, encoding).
3. Picks a *vendor* or *cloud primitive*.
4. Changes how PHI is stored, transported or retained.
5. Changes the offline/online contract.

Trivial decisions (file layout, test framework) don't need ADRs — code review
is enough.

## Numbering and naming

`NNNN-kebab-case-title.md`, four-digit zero-padded, monotonically increasing.
Do not re-use a number even if the ADR is rejected.

## Index

| #    | Title                              | Status   |
| ---- | ---------------------------------- | -------- |
| 0001 | [Use FHIR R4 as the primary clinical data model](./0001-fhir-r4-clinical-data-model.md) | Accepted |
| 0002 | [Resilience via per-dependency circuit breakers](./0002-resilience-circuit-breakers.md) | Accepted |
| 0003 | [Offline-first frontend with IndexedDB mutation queue](./0003-offline-first-frontend.md) | Accepted |
| 0004 | [Append-only hash-chained ledger for supply chain](./0004-supply-hash-chain-ledger.md)  | Accepted |
