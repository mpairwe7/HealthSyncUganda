# ADR 0004 — Append-only hash-chained ledger for supply-chain events

- **Status**: Accepted
- **Date**: 2026-05-02
- **Decision-makers**: Backend lead, NMS liaison
- **Consulted**: National Medical Stores audit team

## Context

Essential-medicines supply is one of the most fraud-prone areas in any
public-sector health system. The accusation we hear most often from district
medical officers is "the central records say I received X but I received Y" —
and once both parties hold mutable databases there is no way for either side
to prove their version is the original.

The accountability question is therefore not "can we store stock movements?"
(any database can) but rather **"can we prove that a stock record has not
been silently rewritten?"**

Constraints:

- Public-sector procurement: external auditors must be able to verify the
  log without access to the live database.
- No blockchain infrastructure (we are not running consensus nodes across
  ministries).
- Must be efficient enough to support thousands of stock events per day.

## Decision

Every stock-movement event (receipt, issue, transfer, adjustment, expiry,
loss) is written to an **append-only ledger** in Postgres with the following
shape:

```
ledger_entry(
  id           BIGSERIAL PRIMARY KEY,
  prev_hash    BYTEA NOT NULL,       -- SHA-256 of the previous row
  payload      JSONB NOT NULL,       -- the event itself
  payload_hash BYTEA NOT NULL,       -- SHA-256(canonical_json(payload))
  entry_hash   BYTEA NOT NULL,       -- SHA-256(prev_hash || payload_hash)
  signed_at    TIMESTAMPTZ NOT NULL,
  signer_id    UUID NOT NULL
)
```

Properties:

- **Append-only at the application layer.** A DB role can only `INSERT`;
  `UPDATE`/`DELETE` is forbidden by row-level grants.
- **Tamper-evident.** Recomputing `entry_hash` from scratch reveals any
  silent rewrite; mismatching rows surface in the daily verification job.
- **Independently verifiable.** A nightly job exports
  `id, signed_at, entry_hash` to a public bucket. Auditors can compute the
  same chain from their copy of the data.
- **Periodic anchoring.** The top-of-chain hash is published in the Ministry's
  daily bulletin (effectively a "notarisation" without blockchain costs).

We do **not** sign each entry with an asymmetric key. Per-user signing keys
in a field setting are operationally unworkable. We instead rely on session-
authenticated server-side writes plus the recoverable audit log of *who* the
session was for.

## Consequences

**Positive**

- An auditor can answer "was this entry rewritten after the fact?" with high
  confidence using nothing but the ledger and the public anchor.
- The hash chain is also the natural input to the verification UI in
  `docs/DEMO_SCRIPT.md` step 7 — auditors love this in walkthroughs.
- We've taken a difficult social problem (trust) and reduced it to a much
  smaller technical one (verify a hash chain).

**Negative**

- Storage grows monotonically. Pruning is not safe. We accept this — the data
  volume is modest (millions of rows per year nationally) and worth keeping.
- We must guard the append-only invariant in code review and migrations. One
  carelessly-granted `UPDATE` permission destroys the property.
- "Tamper-evident" is not "tamper-proof". A determined attacker who controls
  the server can still issue arbitrary new rows. The system reveals
  modifications to *existing* rows, not the introduction of fabricated ones —
  but the audit log of authoring identity narrows the blast radius.

## Alternatives considered

- **Blockchain (Hyperledger, Ethereum)** — operationally expensive,
  politically fraught, and the consensus property is not needed (we have a
  single authoritative writer per district). Rejected.
- **Event sourcing without hashing** — gives us replay, but not tamper-
  evidence. Rejected.
- **Trust the audit log of the RDBMS** — depends on a privileged role being
  honest. We are explicitly trying not to depend on that.
- **Per-user crypto signatures** — operationally unworkable in field
  conditions; deferred.

## How we will know if this was wrong

- The nightly verification job flags > 0 chain breaks in steady state
  (signal: someone bypassed the application layer, or a migration violated
  the invariant).
- External auditors cannot reproduce a verification independently within
  one working day (signal: we have not exposed the chain well enough).
- The cost of "I want to delete a row" becomes a frequent operational pain
  point (signal: revisit retention policy, not the append-only property).

## Links

- Implementation — `backend/app/supply/ledger.py`
- Verification job — `backend/app/jobs/verify_ledger.py`
- Auditor docs — `docs/COMPLIANCE.md` § "Supply ledger"
