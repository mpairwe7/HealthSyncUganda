# ADR 0003 — Offline-first frontend with IndexedDB mutation queue

- **Status**: Accepted
- **Date**: 2026-04-25
- **Decision-makers**: Frontend lead, clinical lead
- **Consulted**: HC III nurse from Hoima district (field interviews, Mar 2026)

## Context

Roughly **42 % of Uganda's lower-level health facilities (HC II / HC III)**
report a daily window during which their internet connectivity is either
absent or so degraded that synchronous calls to a national backend would time
out. Yet these are the facilities that produce the most clinical events per
clinician — every nurse sees 30-60 patients per day.

Our two competing requirements are:

1. **Capture every encounter** — clinicians cannot be blocked by an offline
   moment; the patient is in the room now.
2. **One canonical record** — the same patient walking into a different
   facility tomorrow must see today's encounter.

The naive approach (POST to backend, fail loudly) violates (1). The "fully
distributed CRDT" approach (model every record as eventually consistent)
violates (1)'s simplicity and is overkill for our workloads.

## Decision

The frontend treats the network as **optional**. Concretely:

1. **Service worker** caches static assets and read-only API responses with a
   stale-while-revalidate policy.
2. **TanStack Query** persists its query cache to IndexedDB
   (`PersistQueryClientProvider` with `idbPersister`). Reads work offline up
   to the configured `maxAge` (7 days for clinical data, 24 h for analytics).
3. **Mutations** (POST/PUT/PATCH/DELETE) are queued to an IndexedDB store
   with an **idempotency key**. When the network returns, a background sync
   drains the queue in order. The backend rejects duplicates by idempotency
   key.
4. **Conflict resolution** is server-authoritative. If a queued mutation
   conflicts with newer server state, the user sees an in-app reconciliation
   prompt with both versions side-by-side.
5. **Visual sync state** — every page shows a `<SyncIndicator />` with
   online/offline status and pending mutation count. The Luganda label
   ("X bisigaddewo") matters: clinicians need to know whether their work has
   reached the central record.

We deliberately do **not** support multi-day offline operation. Beyond 7 days
of disconnection we surface a hard banner asking the user to consult IT;
attempting heroic merges across week-long divergence is the wrong default.

## Consequences

**Positive**

- A clinician can complete an entire shift offline. We measured this in
  rehearsal: 47 encounters captured offline, all reconciled cleanly when
  the network returned (see `docs/DEMO_SCRIPT.md` step 6).
- Returning citizens see their pre-existing record even when the local
  facility's link is down, because reads come from IndexedDB.
- The backend can be redeployed without freezing the field.

**Negative**

- We carry a significant client-side cache footprint. We bound it: 50 MB max,
  evicted by LRU + age.
- IndexedDB has known browser quirks (Safari private mode, older Android
  Chromium). We feature-detect and fall back to in-memory with a warning.
- Reconciliation UX is non-trivial. Each conflicting field needs a clinician
  choice. This is the right cost; surfacing the conflict is better than
  silent loss.

## Alternatives considered

- **Native app + SQLite** — better offline story, much higher distribution
  and update cost. Rejected for the pilot; revisit if PWA install rates
  prove insufficient.
- **CRDT-based fully distributed model** — overkill, and a research project
  in its own right. Rejected.
- **Just retry on the wire** — fails for the reason in Context.
- **Email/SMS fallback** — operationally fine for low volume; cannot carry
  structured clinical data.

## How we will know if this was wrong

- Reconciliation prompts appear in > 2 % of offline sessions (signal: model
  needs more granular conflict detection).
- IndexedDB quota errors in > 1 % of sessions (signal: cache bound is too
  generous).
- Field surveys show clinicians distrust the sync indicator (signal: the
  affordance is not landing).

## Links

- IDB persister setup — `frontend/src/components/layout/providers.tsx`
- Mutation queue — `frontend/src/lib/offline/queue.ts`
- Backend idempotency contract — `backend/app/core/idempotency.py`
- Service worker — `frontend/public/sw.js`
