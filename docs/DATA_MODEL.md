# Data Model

**Audience:** code reviewers, DBAs, security/privacy auditors, anyone writing a migration.
**Source of truth:** `backend/app/db/models/*.py`. This document mirrors those files; if you find a mismatch, the code wins and this document is the one to fix.
**Last reviewed:** 2026-05-25.

This is the canonical reference for **what data lives where**, **how it is classified**, and **how long it is kept**. It exists for three audiences:

- **Code reviewers** verifying that an endpoint touches the tables it claims to touch.
- **DPPA / privacy auditors** verifying that every PII column has a lawful basis (in [DPIA.md](./DPIA.md)) and a retention rule.
- **DBAs** verifying that the indexes are correct for the access patterns described in [ARCHITECTURE.md](./ARCHITECTURE.md) and the workloads in [RUNBOOK.md](./RUNBOOK.md).

---

## 1. Conventions

All ORM models inherit `Base, IdMixin, TimestampMixin` from `app.db.base`. Therefore every row carries:

| Column        | Type                       | Source              | Notes |
| ------------- | -------------------------- | ------------------- | ----- |
| `id`          | `String(26)` PRIMARY KEY   | `IdMixin`           | Width is sized for ULID; current default is `str(uuid4())`. Migration to ULID generation is a non-breaking change (column stays `String(26)`). |
| `created_at`  | `DateTime(timezone=True)` NOT NULL | `TimestampMixin` | UTC; populated by application default. |
| `updated_at`  | `DateTime(timezone=True)` NOT NULL | `TimestampMixin` | UTC; bumped on every flush via `onupdate`. |

JSON columns use the `JSONBOrJSON` type decorator: **JSONB on PostgreSQL, JSON on SQLite** (laptop/test fallback). Same Python interface either way.

Naming convention (set on `Base.metadata`): `ix_%(column_0_label)s`, `uq_%(table_name)s_%(column_0_name)s`, `fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s`, `pk_%(table_name)s`. Alembic uses this convention so migrations diff cleanly.

**Classification scheme** used in the inventory below:

- **PII** — Personal Identifiable Information under DPPA s.3 (name, NIN, contact info, location).
- **PHI** — Personal Health Information; the special-category subset of PII (clinical observations, diagnosis codes, encounter reasons).
- **Operational** — system data with no privacy classification (timestamps, IDs, status flags, foreign keys).
- **Append-only** — application contract that writes happen only via `INSERT`; never `UPDATE`, never `DELETE`.

---

## 2. Entity-relationship overview

```
                        ┌─────────────────┐
                        │   facilities    │
                        │  (HC II … NRH)  │
                        └────────┬────────┘
                                 │ 1
                ┌────────────────┼─────────────────┬─────────────────┐
                │ N              │ N               │ N               │ N
       ┌────────┴──────┐  ┌──────┴──────┐  ┌───────┴─────────┐  ┌────┴───────────┐
       │     users     │  │ encounters  │  │  stock_batches  │  │ stock_transfers│
       │   (staff)     │  │  (clinical) │  │   (inventory)   │  │  (movements)   │
       └───────────────┘  └──────┬──────┘  └────────┬────────┘  └────────────────┘
                                 │ 1                │ N
                                 │ N                │
                          ┌──────┴───────┐  ┌───────┴────────┐
                          │ observations │  │   stock_events │  ◀── append-only
                          │  (PHI)       │  │  (hash-chain)  │      hash chain
                          └──────────────┘  └────────────────┘

                                 ▲
                                 │ N
                          ┌──────┴────────┐  1     N  ┌─────────────────┐
                          │   patients    │ ◀────────▶│    consents     │
                          │  (NIN-linked) │           │  (revocable)    │
                          └───────────────┘           └─────────────────┘

                          ┌────────────────┐
                          │   audit_log    │  ◀── append-only;
                          │ (PII access)   │      no FK — references resources by (resource_type, resource_id) tuple
                          └────────────────┘

                          ┌────────────────┐
                          │  supply_items  │  ── master data, no FK from elsewhere
                          │ (drug catalog) │     except stock_batches.supply_item_id
                          └────────────────┘
```

Cardinality summary:

- A **facility** has N users, N encounters, N stock_batches, and is referenced by stock_transfers (`from_facility_id`, `to_facility_id`).
- A **patient** has N encounters and N consents.
- An **encounter** has N observations.
- A **supply_item** has N stock_batches.
- A **stock_batch** is referenced by N stock_events.
- `audit_log` and `stock_events` are deliberately **not** linked by foreign key to the resources they reference — the link is a `(resource_type, resource_id)` tuple — because the audit trail must outlive `DELETE`s on the referenced table.

---

## 3. Per-table inventory

### 3.1 `patients` — clinical core, NIN-linked

Source: `backend/app/db/models/patient.py`.

| Column            | Type            | Null | Index            | Class | Notes |
| ----------------- | --------------- | ---- | ---------------- | ----- | ----- |
| `id`              | String(26)      | NO   | PK               | Op    | Primary key. |
| `nin`             | String(14)      | NO   | UNIQUE, btree    | **PII** | Uganda National Identification Number — the natural key linking citizen records across systems. |
| `given_name`      | String(80)      | NO   | (trigram GIN via family_name composite) | **PII** | |
| `family_name`     | String(80)      | NO   | `ix_patients_family_name_trgm` (GIN trgm, Postgres only) | **PII** | Trigram index supports fuzzy search in `patients.py:search_patients`. |
| `gender`          | String(10)      | NO   | —                | **PII** | DPPA s.3 special-category-adjacent. |
| `birth_date`      | Date            | NO   | —                | **PII** | |
| `phone`           | String(20)      | YES  | —                | **PII** | Optional contact channel. |
| `email`           | String(160)     | YES  | —                | **PII** | Optional contact channel. |
| `district`        | String(80)      | NO   | btree            | **PII** | Uganda administrative hierarchy; supports district-scoped queries. |
| `sub_county`      | String(80)      | YES  | —                | **PII** | |
| `parish`          | String(80)      | YES  | —                | **PII** | |
| `village`         | String(80)      | YES  | —                | **PII** | |
| `deceased`        | Boolean         | NO   | —                | Op    | Default `false`. |
| `record_version`  | Integer         | NO   | —                | Op    | Bumped on every PATCH (`patients.py:update_patient`) — supports DPPA s.11 accuracy/rectification. |
| `created_at`      | DateTime(tz)    | NO   | —                | Op    | |
| `updated_at`      | DateTime(tz)    | NO   | —                | Op    | |

**Relationships:** `encounters` (1→N, CASCADE on patient delete), `consents` (1→N, CASCADE).
**Retention:** indefinite while the citizen is living; soft-delete on death via `deceased=true`; physical erasure only by ministry-admin action per [COMPLIANCE.md s.26](./COMPLIANCE.md#a-uganda-data-protection-and-privacy-act-2019). Detailed schedule in [DPIA.md §9](./DPIA.md).
**Lawful basis:** consent + provision of healthcare ([DPIA.md §2](./DPIA.md)).

### 3.2 `users` — staff accounts

Source: `backend/app/db/models/user.py`. Citizens are *not* in this table; they authenticate via NIN+OTP and are identified by their `patients` row.

| Column          | Type        | Null | Index           | Class | Notes |
| --------------- | ----------- | ---- | --------------- | ----- | ----- |
| `id`            | String(26)  | NO   | PK              | Op    | |
| `username`      | String(80)  | NO   | UNIQUE (`uq_users_username`), btree | **PII** | |
| `full_name`     | String(160) | NO   | —               | **PII** | Display name. |
| `role`          | String(40)  | NO   | btree           | Op    | One of `worker`, `pharmacist`, `district_admin`, `ministry_admin`. Enforced as `Role` literal in `app/core/security.py`. |
| `facility_id`   | String(26)  | YES  | FK → `facilities.id` ON DELETE SET NULL, btree | Op | Set for workers and pharmacists; NULL for admins. |
| `password_hash` | String(255) | NO   | —               | **PII** | bcrypt; 72-byte input truncation in `security.py:hash_password`. |
| `active`        | Boolean     | NO   | —               | Op    | Default `true`. Set `false` to disable account ([INCIDENT_RESPONSE.md IR-14 step 2](./INCIDENT_RESPONSE.md#ir-14)). |
| `created_at`    | DateTime(tz)| NO   | —               | Op    | |
| `updated_at`    | DateTime(tz)| NO   | —               | Op    | |

**Relationships:** `facility` (N→1, SET NULL on facility delete).
**Retention:** account lifetime; soft-disable on departure (`active=false`); historical reference preserved for audit-log integrity.
**Lawful basis:** legitimate interest (operating the platform) + employment context.

### 3.3 `facilities` — Uganda HC II … NRH hierarchy

Source: `backend/app/db/models/facility.py`.

| Column        | Type         | Null | Index          | Class | Notes |
| ------------- | ------------ | ---- | -------------- | ----- | ----- |
| `id`          | String(26)   | NO   | PK             | Op    | |
| `code`        | String(40)   | NO   | UNIQUE, btree  | Op    | Ministry-issued facility code. |
| `name`        | String(160)  | NO   | btree          | Op    | Display name. |
| `level`       | String(40)   | NO   | btree          | Op    | One of `HC II`, `HC III`, `HC IV`, `HC`, `GH`, `RRH`, `NRH`. |
| `district`    | String(80)   | NO   | btree          | Op    | |
| `sub_county`  | String(80)   | YES  | —              | Op    | |
| `latitude`    | Float        | YES  | —              | Op    | |
| `longitude`   | Float        | YES  | —              | Op    | |
| `active`      | Boolean      | NO   | —              | Op    | |
| `created_at`  | DateTime(tz) | NO   | —              | Op    | |
| `updated_at`  | DateTime(tz) | NO   | —              | Op    | |

**Relationships:** `users` (1→N), `encounters` (1→N), `stock_batches` (1→N).
**Retention:** indefinite; not personal data.
**Lawful basis:** n/a (no personal data).

### 3.4 `encounters` — clinical visit envelope

Source: `backend/app/db/models/encounter.py`.

| Column             | Type         | Null | Index         | Class | Notes |
| ------------------ | ------------ | ---- | ------------- | ----- | ----- |
| `id`               | String(26)   | NO   | PK            | Op    | |
| `patient_id`       | String(26)   | NO   | FK → `patients.id` ON DELETE CASCADE, btree | Op | |
| `facility_id`      | String(26)   | NO   | FK → `facilities.id` ON DELETE RESTRICT, btree | Op | RESTRICT prevents accidental loss of clinical history if a facility is deleted. |
| `reason`           | String(400)  | NO   | —             | **PHI** | Free-text chief complaint. |
| `status`           | String(20)   | NO   | —             | Op    | Default `in-progress`; values: `in-progress`, `finished`, `cancelled`. |
| `started_at`       | DateTime(tz) | NO   | btree         | Op    | |
| `ended_at`         | DateTime(tz) | YES  | —             | Op    | |
| `diagnosis_codes`  | JSONBOrJSON  | NO   | —             | **PHI** | List of ICD-10 codes; default `[]`. |
| `recorded_by`      | String(80)   | YES  | —             | Op    | Username of the recording clinician (not FK — preserves history if the user row is later disabled). |
| `created_at`       | DateTime(tz) | NO   | —             | Op    | |
| `updated_at`       | DateTime(tz) | NO   | —             | Op    | |

**Relationships:** `patient`, `facility`, `observations` (1→N, CASCADE).
**Retention:** lifetime of patient record; cascades on `DELETE patient` (which itself is gated).
**Lawful basis:** provision of healthcare.

### 3.5 `observations` — vitals, labs, immunisations

Source: `backend/app/db/models/encounter.py`.

| Column            | Type         | Null | Index        | Class | Notes |
| ----------------- | ------------ | ---- | ------------ | ----- | ----- |
| `id`              | String(26)   | NO   | PK           | Op    | |
| `encounter_id`    | String(26)   | NO   | FK → `encounters.id` ON DELETE CASCADE, btree | Op | |
| `patient_id`      | String(26)   | NO   | btree        | Op    | Denormalised for patient-scoped queries; no FK (already enforced via encounter cascade). |
| `code_system`     | String(160)  | NO   | —            | Op    | E.g. `http://loinc.org`, `http://snomed.info/sct`. |
| `code`            | String(80)   | NO   | btree        | Op    | Code value within the system. |
| `display`         | String(200)  | YES  | —            | Op    | Human-readable label. |
| `value_quantity`  | Float        | YES  | —            | **PHI** | Numeric measurement (BP, weight, lab value). |
| `value_unit`      | String(40)   | YES  | —            | Op    | UCUM unit. |
| `value_string`    | String(400)  | YES  | —            | **PHI** | Free-text or coded value. |
| `effective_at`    | DateTime(tz) | NO   | btree        | Op    | When the measurement was taken (not when recorded). |
| `recorded_by`     | String(80)   | YES  | —            | Op    | |
| `created_at`      | DateTime(tz) | NO   | —            | Op    | |
| `updated_at`      | DateTime(tz) | NO   | —            | Op    | |

**Relationships:** `encounter` (N→1).
**Retention:** lifetime of encounter; cascades.
**Lawful basis:** provision of healthcare.

### 3.6 `supply_items` — drug & commodity master

Source: `backend/app/db/models/supply.py`.

| Column                 | Type         | Null | Index           | Class | Notes |
| ---------------------- | ------------ | ---- | --------------- | ----- | ----- |
| `id`                   | String(26)   | NO   | PK              | Op    | |
| `code`                 | String(40)   | NO   | UNIQUE, btree   | Op    | EML/ATC code. |
| `name`                 | String(120)  | NO   | btree           | Op    | |
| `category`             | String(40)   | NO   | btree           | Op    | E.g. `antimalarial`, `vaccine`, `consumable`. |
| `unit`                 | String(40)   | NO   | —               | Op    | E.g. `tablet`, `vial`, `dose`. |
| `reorder_threshold`    | Integer      | NO   | —               | Op    | Default `0`. |
| `requires_cold_chain`  | Boolean      | NO   | —               | Op    | Default `false`. |
| `created_at`           | DateTime(tz) | NO   | —               | Op    | |
| `updated_at`           | DateTime(tz) | NO   | —               | Op    | |

**Relationships:** `batches` (1→N, CASCADE).
**Retention:** indefinite (master data).

### 3.7 `stock_batches` — facility-level inventory

Source: `backend/app/db/models/supply.py`.

| Column            | Type         | Null | Index                                              | Class | Notes |
| ----------------- | ------------ | ---- | -------------------------------------------------- | ----- | ----- |
| `id`              | String(26)   | NO   | PK                                                 | Op    | |
| `supply_item_id`  | String(26)   | NO   | FK → `supply_items.id` ON DELETE CASCADE, btree    | Op    | |
| `facility_id`     | String(26)   | NO   | FK → `facilities.id` ON DELETE RESTRICT, btree     | Op    | |
| `lot_number`      | String(80)   | NO   | btree                                              | Op    | Vendor lot — supports recall. |
| `quantity`        | Integer      | NO   | —                                                  | Op    | Quantity at receipt. |
| `remaining`       | Integer      | NO   | —                                                  | Op    | Folded from `stock_events` (cached for query convenience). |
| `expires_on`      | Date         | NO   | btree                                              | Op    | Supports expiry alerts. |
| `received_on`     | Date         | NO   | —                                                  | Op    | |
| `cost_ugx`        | Integer      | YES  | —                                                  | Op    | Unit cost. |
| `created_at`      | DateTime(tz) | NO   | —                                                  | Op    | |
| `updated_at`      | DateTime(tz) | NO   | —                                                  | Op    | |

Additional composite index: `ix_stock_batches_facility_item (facility_id, supply_item_id)` — covers "what is in stock at this facility" queries.

**Relationships:** `supply_item`, `facility`.
**Retention:** indefinite (audit-relevant for cold-chain claims and expiry recalls).

### 3.8 `stock_events` — append-only hash-chain ledger

Source: `backend/app/db/models/supply.py`. Backed by [ADR 0004 — supply hash-chain ledger](./adr/0004-supply-hash-chain-ledger.md).

| Column            | Type         | Null | Index                                          | Class | Notes |
| ----------------- | ------------ | ---- | ---------------------------------------------- | ----- | ----- |
| `id`              | String(26)   | NO   | PK                                             | **Append-only** | |
| `batch_id`        | String(26)   | YES  | FK → `stock_batches.id` ON DELETE SET NULL, btree | Op | SET NULL preserves the event when a batch is purged. |
| `supply_item_id`  | String(26)   | NO   | btree                                          | Op    | Denormalised. |
| `facility_id`     | String(26)   | NO   | btree                                          | Op    | Denormalised. |
| `event_type`      | String(40)   | NO   | btree                                          | Op    | E.g. `receive`, `dispense`, `transfer_out`, `transfer_in`, `adjust`, `expire`. |
| `quantity_delta`  | Integer      | NO   | —                                              | Op    | Signed; `dispense` is negative. |
| `actor_id`        | String(80)   | NO   | —                                              | Op    | Username; not FK. |
| `occurred_at`     | DateTime(tz) | NO   | btree                                          | Op    | |
| `reference_id`    | String(80)   | YES  | —                                              | Op    | Encounter id, transfer id, etc. |
| `prev_hash`       | String(64)   | YES  | —                                              | Op    | SHA-256 of previous event (NULL for genesis). |
| `event_hash`      | String(64)   | NO   | btree                                          | Op    | SHA-256 of this event's canonical encoding + `prev_hash`. |
| `extra`           | JSONBOrJSON  | NO   | —                                              | Op    | Free-form metadata. |
| `created_at`      | DateTime(tz) | NO   | —                                              | Op    | |
| `updated_at`      | DateTime(tz) | NO   | —                                              | Op    | Updated only at insert; subsequent `UPDATE` breaks the chain by design. |

**Append-only invariant:** the application never issues `UPDATE` or `DELETE`. Verification (`GET /api/v1/supply/ledger/verify`) recomputes `event_hash` for each row in `occurred_at` order; a mismatch trips [RUNBOOK.md RB-07](./RUNBOOK.md#rb-07) and [INCIDENT_RESPONSE.md IR-21](./INCIDENT_RESPONSE.md#ir-21--supply-ledger-broken). A database-level `RULE` to enforce append-only at the engine layer is a planned migration; see SECURITY.md "audit log is append-only by application convention".

### 3.9 `stock_transfers` — inter-facility movements

Source: `backend/app/db/models/supply.py`.

| Column              | Type         | Null | Index                                       | Class | Notes |
| ------------------- | ------------ | ---- | ------------------------------------------- | ----- | ----- |
| `id`                | String(26)   | NO   | PK                                          | Op    | |
| `from_facility_id`  | String(26)   | NO   | FK → `facilities.id` ON DELETE RESTRICT     | Op    | |
| `to_facility_id`    | String(26)   | NO   | FK → `facilities.id` ON DELETE RESTRICT     | Op    | |
| `supply_item_id`    | String(26)   | NO   | FK → `supply_items.id` ON DELETE RESTRICT   | Op    | |
| `quantity`          | Integer      | NO   | —                                           | Op    | |
| `reason`            | String(200)  | NO   | —                                           | Op    | |
| `status`            | String(20)   | NO   | —                                           | Op    | Default `in-progress`. |
| `initiated_by`      | String(80)   | NO   | —                                           | Op    | Username. |
| `initiated_at`      | DateTime(tz) | NO   | —                                           | Op    | |
| `completed_at`      | DateTime(tz) | YES  | —                                           | Op    | |
| `created_at`        | DateTime(tz) | NO   | —                                           | Op    | |
| `updated_at`        | DateTime(tz) | NO   | —                                           | Op    | |

Transfers emit paired `transfer_out` / `transfer_in` `stock_events` so the hash-chain remains the source of truth for on-hand calculation.

### 3.10 `consents` — explicit, granular, revocable

Source: `backend/app/db/models/consent.py`.

| Column         | Type         | Null | Index                                       | Class | Notes |
| -------------- | ------------ | ---- | ------------------------------------------- | ----- | ----- |
| `id`           | String(26)   | NO   | PK                                          | Op    | |
| `patient_id`   | String(26)   | NO   | FK → `patients.id` ON DELETE CASCADE, btree | Op    | |
| `scope`        | String(80)   | NO   | btree                                       | Op    | E.g. `share-with-dhis2`, `share-with-facility:HC-IV-Mbarara`. |
| `purpose`      | String(300)  | NO   | —                                           | Op    | Free text — must be specific. |
| `granted_at`   | DateTime(tz) | NO   | —                                           | Op    | |
| `expires_at`   | DateTime(tz) | YES  | —                                           | Op    | NULL = open-ended (still revocable). |
| `revoked_at`   | DateTime(tz) | YES  | —                                           | Op    | NULL = active; cache invalidation propagates within 60 s. |
| `granted_by`   | String(80)   | NO   | —                                           | Op    | Who recorded the grant (citizen self-grant or worker on their behalf). |
| `created_at`   | DateTime(tz) | NO   | —                                           | Op    | |
| `updated_at`   | DateTime(tz) | NO   | —                                           | Op    | |

**Retention:** indefinite while the patient exists; the grant→revoke history itself is regulatory evidence.

### 3.11 `audit_log` — append-only PII access trail

Source: `backend/app/db/models/audit_log.py`. Writes only via `app.core.audit.record_access`; mirrored to structured logs for SIEM.

| Column               | Type         | Null | Index                                                  | Class | Notes |
| -------------------- | ------------ | ---- | ------------------------------------------------------ | ----- | ----- |
| `id`                 | String(26)   | NO   | PK                                                     | **Append-only** | |
| `actor_id`           | String(80)   | NO   | btree                                                  | **PII** | Username or NIN. |
| `actor_role`         | String(40)   | NO   | btree                                                  | Op    | |
| `actor_facility_id`  | String(26)   | YES  | btree                                                  | Op    | |
| `resource_type`      | String(40)   | NO   | btree, `ix_audit_log_resource (resource_type, resource_id)` | Op | |
| `resource_id`        | String(80)   | NO   | btree (composite above)                                | Op    | Tuple link — no FK so the trail survives `DELETE` on the referenced resource. |
| `action`             | String(40)   | NO   | btree                                                  | Op    | E.g. `read`, `create`, `update`, `revoke`, `fhir-read`. |
| `purpose`            | String(300)  | YES  | —                                                      | Op    | The caller's declared reason; required for sensitive resources (enforced at endpoint via `Query(...)`). |
| `consent_id`         | String(26)   | YES  | —                                                      | Op    | Links to the `consents` row authorising the access, where applicable. |
| `extra`              | JSONBOrJSON  | NO   | —                                                      | Op    | Free-form (e.g. `{"fields": ["phone"]}` for updates). |
| `created_at`         | DateTime(tz) | NO   | `ix_audit_log_actor_time (actor_id, created_at)`       | Op    | |
| `updated_at`         | DateTime(tz) | NO   | —                                                      | Op    | Same value as `created_at` by construction. |

**Append-only invariant:** application contract; a Postgres `RULE` enforcing it at the DB layer is a planned migration (`PR welcome` per [SECURITY.md](./SECURITY.md)).

**Retention:** ≥ 1 year for DPPA s.13/s.14; longer for forensic value. Aged rows can be moved to cold storage but not deleted while any referenced resource still exists.

---

## 4. Index strategy

Indexes exist to serve specific access paths. The current set is conservative — every index is justified by a real query in the codebase. Avoid adding speculative indexes; each one slows writes and bloats the table.

| Table           | Index                                    | Serves                                                                |
| --------------- | ---------------------------------------- | --------------------------------------------------------------------- |
| patients        | `nin` UNIQUE                             | NIN lookup — the dominant read pattern.                               |
| patients        | `district` btree                         | District-scoped admin queries.                                        |
| patients        | `family_name` GIN trgm (Postgres)        | Fuzzy name search in `search_patients`.                               |
| users           | `username` UNIQUE                        | Login.                                                                |
| users           | `facility_id` btree                      | "Who works at this facility" admin views.                             |
| facilities      | `code` UNIQUE, `name`, `level`, `district` | Multiple facility browse views.                                     |
| encounters      | `patient_id`, `facility_id`, `started_at` | Per-patient and per-facility timelines.                              |
| observations    | `encounter_id`, `patient_id`, `code`, `effective_at` | Per-encounter and per-patient observation streams.        |
| stock_batches   | `(facility_id, supply_item_id)` composite, `expires_on` | "What's in stock here" + expiry alerts.                |
| stock_events    | `batch_id`, `event_type`, `occurred_at`, `event_hash` | Verification scan + per-batch event timeline.             |
| consents        | `patient_id`, `scope`                    | "Who has consented to what" lookup.                                   |
| audit_log       | composite `(resource_type, resource_id)`, composite `(actor_id, created_at)` | Two access patterns: "who touched X" and "what did actor Y do". |

---

## 5. Schema evolution

The migration policy is in [RUNBOOK.md RB-12](./RUNBOOK.md#rb-12--schema-migration-to-apply). Summary:

- **No single-step `DROP COLUMN` or `RENAME COLUMN`** in a single migration. Use **add → backfill → switch reads → switch writes → drop** in separate releases.
- Migrations are Alembic-managed (`backend/alembic/`).
- Naming convention is set on `Base.metadata` (see §1); Alembic uses it for diffs.
- The CI does **not** apply migrations automatically; deployment does, per [DEPLOYMENT.md](./DEPLOYMENT.md).
- An ADR is required for any change that breaks an existing FHIR mapping or changes a PII column's classification.

---

## 6. Data not in PostgreSQL

The following data lives outside the main relational store and is documented here so an auditor sees the complete picture:

| Store               | Contents                                                                            | Retention                                                  |
| ------------------- | ----------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| Redis               | Idempotency-key cache (24 h), analytics cache (60 s), NIRA last-known-good cache, DHIS2 outbox queue, rate-limit token buckets | Per-key TTL; no PHI stored beyond cache lifetime |
| Browser IndexedDB   | Offline mutation queue, TanStack Query response cache                               | 7-day TTL (browser-side); see [ADR 0003](./adr/0003-offline-first-frontend.md) |
| OTel Collector / Tempo | Distributed traces                                                               | 30 days (target) — see [OBSERVABILITY.md](./OBSERVABILITY.md) |
| Loki / SIEM         | Structured logs including audit-log mirror                                          | ≥ 1 year per DPPA s.13 |
| Object storage      | Database backups, evidence packs from incidents                                     | Backups: see [BACKUP_RESTORE.md](./BACKUP_RESTORE.md); evidence: legal-hold |

---

## 7. Cross-references

- [DPIA.md](./DPIA.md) — risk register and lawful-basis assessment per processing activity.
- [COMPLIANCE.md](./COMPLIANCE.md) — DPPA article-by-article mapping. Every PII column here ties to a row there.
- [ACCESS_CONTROL.md](./ACCESS_CONTROL.md) — RBAC matrix that constrains *who* can read what.
- [SECURITY.md](./SECURITY.md) — encryption, audit, transport posture.
- [INCIDENT_RESPONSE.md](./INCIDENT_RESPONSE.md) — what counts as a PII column for the PDPO notification.
- [API.md](./API.md) — endpoints that read/write these tables.
- [ARCHITECTURE.md](./ARCHITECTURE.md) — data flows.
- [adr/0001-fhir-r4-clinical-data-model.md](./adr/0001-fhir-r4-clinical-data-model.md) — why the clinical tables look the way they do.
- [adr/0004-supply-hash-chain-ledger.md](./adr/0004-supply-hash-chain-ledger.md) — why `stock_events` is append-only.
