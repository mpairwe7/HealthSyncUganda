# Crane Cloud deployment — HealthSync Uganda

**Audience:** SREs, DevOps engineers, MoH IT staff operating a Crane Cloud-hosted instance of HealthSync Uganda.
**CLI required:** [`cranecloud`](https://docs.cranecloud.io/) installed and authenticated on the operator's interactive shell.
**Last reviewed:** 2026-05-25.

This directory is the **deployment surface** for Crane Cloud (Uganda's PaaS, run by Makerere AI Lab). It wraps the `cranecloud` CLI's per-app commands behind a Make-based environment-aware workflow so the same deploy story works across **staging**, **pilot**, and **production** without bespoke scripts.

```
infra/cranecloud/
├── README.md                              ← this file
├── manifest.yaml                          ← deployment manifest (image, port, env names)
├── Makefile                               ← deploy / update / list wrappers
└── environments/
    ├── staging.env.example                ← committed template
    ├── pilot.env.example                  ← committed template
    └── production.env.example             ← committed template
    # staging.env, pilot.env, production.env are GIT-IGNORED.
```

---

## 0. Topology on Crane Cloud

A HealthSync deployment occupies **one Crane Cloud project** per environment, with all four components running as Crane Cloud apps in the same project. This mirrors the local `docker-compose.yml` topology — every component is local to the deployment unit; nothing is an external dependency.

| Component | How it lives on Crane Cloud | Image / source | Notes |
| --- | --- | --- | --- |
| **PostgreSQL** | Crane Cloud app — `cranecloud apps deploy` | `ghcr.io/mpairwe7/healthsync-uganda-postgres:<tag>` (custom image: `postgres:16-alpine` + baked-in `init.sql` for pgcrypto / pg_trgm / btree_gin) | **Self-hosted, not DaaS** — see §0.1 below for the durability trade-off and §0.2 for the DaaS fallback. |
| **Redis** | Crane Cloud app — `cranecloud apps deploy` | `redis:7-alpine` (Docker Hub) | Deployed with `--requirepass` + 256 MB cap + LRU eviction. |
| **Backend (FastAPI)** | Crane Cloud app | `ghcr.io/mpairwe7/healthsync-uganda-backend:<tag>` | Built and pushed by `.github/workflows/build-push.yml`. |
| **Frontend (Next.js)** | Crane Cloud app | `ghcr.io/mpairwe7/healthsync-uganda-frontend:<tag>` | Built and pushed by the same workflow. |
| OpenTelemetry collector | Optional external — point `OTEL_EXPORTER_OTLP_ENDPOINT` at any OTLP receiver. Leave blank to disable. | — | Not part of the Crane Cloud project. |

The `make deploy ENV=<env>` target deploys all four Crane Cloud apps in order: **postgres → redis → backend → frontend**. The backend/frontend depend on postgres + redis being reachable; the chain order matters.

### 0.1 Persistence caveat for self-hosted DB & cache (READ BEFORE DEPLOY)

Crane Cloud's public documentation (as of 2026-05-25, [docs.cranecloud.io](https://docs.cranecloud.io/)) does not document persistent volumes for app containers. We therefore treat both `postgres` and `redis` as **ephemeral** — any pod restart resets state to the image's initial state.

For **Postgres**, ephemerality is severe:

- A pod restart drops every patient record, encounter, observation, consent grant, audit-log row, and supply ledger entry created since the last `pg_dump`.
- For a health-records system this is **unacceptable in production** without persistent storage.

For **Redis**, ephemerality is bounded:

| Redis-resident state | Rebuildable after restart? |
| --- | --- |
| Idempotency-key cache (24h) | ✅ Re-populates on first retry |
| NIRA last-known-good cache | ✅ Re-populates on next NIRA call |
| Rate-limit token buckets | ✅ Re-populates within the 60s window |
| Analytics cache (60s TTL) | ✅ Re-populates on first dashboard hit |
| **DHIS2 outbox queue** | ⚠️ NOT trivially rebuildable — pending pushes are lost on Redis restart (see `docs/RUNBOOK.md` RB-03) |

Operating discipline for the self-hosted shape:

1. **Scheduled `pg_dump`** to external object storage (S3-compatible) per [`docs/BACKUP_RESTORE.md`](../../docs/BACKUP_RESTORE.md). Cadence: 15-min WAL + daily logical dump (RPO 15 min target).
2. **Postgres pod-restart alert** — any restart of the Postgres app triggers SEV-1 alert (treat as a potential data-loss event until a fresh dump confirms otherwise).
3. **Avoid `make update-postgres`** in production unless a recent dump exists; the Makefile prints a warning.

### 0.2 Fallback to Crane Cloud's managed PostgreSQL DaaS

If self-hosted Postgres turns out to be unsuitable (no persistent volumes confirmed; data loss observed on restart; pilot acceptance review fails), the documented alternative is Crane Cloud's managed PostgreSQL DaaS:

> Crane Cloud DaaS: UI: Project → **Databases** → **+ New Database** → PostgreSQL → Create. Copy credentials. ([docs.cranecloud.io/databases](https://docs.cranecloud.io/databases/))

Switching back to DaaS requires:

1. Delete the self-hosted `healthsync-postgres-*` Crane Cloud app (`cranecloud apps delete --id $POSTGRES_APP_ID`).
2. Provision the Postgres DaaS via the UI; copy the connection string.
3. Update `DATABASE_URL` in `environments/<env>.env` to the DaaS connection string (rewriting `postgresql://` to `postgresql+asyncpg://`).
4. `make update-backend ENV=<env>` to roll the backend onto the new database.
5. Restore from the most recent `pg_dump` into the DaaS instance before re-enabling writes.

For longer-term durability the right answer is NITA-U Government Cloud, where persistent storage is first-class — tracked on the roadmap.

## 1. Prerequisites

1. **`cranecloud` CLI installed** and on `$PATH`. See <https://docs.cranecloud.io/>.
2. **Authenticated** via `cranecloud auth login`. The session token lives in the OS keyring; deploys must therefore run from an **interactive shell with keyring access** (not from CI, not from a non-tty session — that's why CI does not deploy automatically).
3. **Container images** for the two apps are reachable from Crane Cloud's pull side:
   - `ghcr.io/mpairwe7/healthsync-uganda-backend:<tag>`
   - `ghcr.io/mpairwe7/healthsync-uganda-frontend:<tag>`
   - Either make the GHCR packages public, or grant Crane Cloud's registry-puller read access.
4. **Postgres + Redis** are provisioned — either as Crane Cloud add-ons (recommended for pilot) or pointing at external managed services. You'll paste the `postgresql+asyncpg://…` and `redis://…` URLs into the `.env` file.

---

## 2. One-time setup per environment

Replace `<env>` with `staging`, `pilot`, or `production`. Steps 1–3 are **prerequisites** that have to complete before the `make deploy` target succeeds.

```bash
cd infra/cranecloud
make init ENV=<env>          # prints the same checklist verbosely

# 1) Confirm authentication and find/create the Crane Cloud project
cranecloud auth user
cranecloud projects list
# If the project doesn't exist:
cranecloud projects create   # suggested name: healthsync-uganda-<env>
PROJ_ID=$(cranecloud projects list | grep "healthsync-uganda-<env>" | awk '{print $1}')

# 2) Generate secrets locally
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
POSTGRES_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
REDIS_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

# 3) Copy the env template and fill in real values
cp environments/<env>.env.example environments/<env>.env
$EDITOR environments/<env>.env
# At minimum set:
#   CRANECLOUD_PROJECT_ID = <PROJ_ID from step 1>
#   POSTGRES_PASSWORD     = <from step 2>
#   REDIS_PASSWORD        = <from step 2>
#   SECRET_KEY            = <from step 2>
#   DATABASE_URL          = postgresql+asyncpg://healthsync:<POSTGRES_PASSWORD>@<POSTGRES_HOSTNAME>:5432/healthsync
#                           (POSTGRES_HOSTNAME is set automatically by the
#                            template, e.g. healthsync-postgres-staging)
#   REDIS_URL             = redis://:<REDIS_PASSWORD>@<REDIS_HOSTNAME>:6379/0
#   NIRA_*, DHIS2_*       = real URLs for pilot / production; mocks for staging
```

The `.env` file stays on your machine (gitignored). It is **the** source of truth for values; the manifest declares which names are expected.

---

## 3. First deploy

```bash
cd infra/cranecloud
make deploy ENV=<env>
# Equivalent: make deploy-postgres ENV=<env>
#          && make deploy-redis    ENV=<env>
#          && make deploy-backend  ENV=<env>
#          && make deploy-frontend ENV=<env>
```

The CLI returns an **APP_ID (UUID)** for each of the four apps. Capture them back into your `.env`:

```bash
# environments/<env>.env
POSTGRES_APP_ID=<uuid-from-cli>
REDIS_APP_ID=<uuid-from-cli>
BACKEND_APP_ID=<uuid-from-cli>
FRONTEND_APP_ID=<uuid-from-cli>
```

### Schema bootstrap

The backend auto-creates its schema on first startup via `Base.metadata.create_all` in the FastAPI lifespan hook, gated on the `AUTO_CREATE_SCHEMA` env var (default `true`). This means: as long as `AUTO_CREATE_SCHEMA=true` is set (or left at default), `deploy-backend` itself bootstraps the schema against the freshly-deployed Postgres app — no separate migration step.

**Stop-gap notice.** `create_all` is idempotent for adding new tables but does **not** apply ALTERs or destructive changes — it cannot evolve a live schema. Before production go-live with real PHI, the project commits to wiring up proper Alembic migrations (declared in `pyproject.toml`, not yet configured). At that point set `AUTO_CREATE_SCHEMA=false` and the deploy flow becomes:

```bash
make -C infra/cranecloud deploy-postgres ENV=<env>
cd backend && uv run alembic upgrade head     # against the Crane Cloud Postgres
make -C infra/cranecloud deploy-backend ENV=<env>
```

Tracked as a pre-pilot follow-up; see `CHANGELOG.md` "Known follow-ups".

These IDs are what `make update-*` targets later — without them, you'd accidentally create duplicate apps.

The **REDIS_HOSTNAME** entry in your `.env` is the in-project DNS name Crane Cloud assigns to the Redis app (typically the app's `name`). Crane Cloud's web UI confirms this on the Redis app's detail page after deploy. If the actual hostname differs from the default (`healthsync-redis-<env>`), update `REDIS_HOSTNAME` and `REDIS_URL` accordingly, then re-deploy the backend to pick up the corrected URL.

---

## 4. Subsequent rollouts

A code change → new image tag → roll out:

```bash
# Update the image tag (and optionally the replica count) in your env file
$EDITOR environments/<env>.env       # bump BACKEND_IMAGE_TAG

make update-backend ENV=<env>
make update-frontend ENV=<env>
```

Crane Cloud performs a rolling update against the existing app — no downtime if `replicas >= 2`.

---

## 5. Listing and inspecting

```bash
make list ENV=<env>                       # list all apps in the project
make info ENV=<env> APP_ID=<uuid>         # detail one app
```

---

## 6. What lives where

| Concern | Where it lives | Tracked in git? |
| --- | --- | --- |
| Which apps exist + how they are shaped | `manifest.yaml` | ✅ committed |
| Per-environment values (URLs, tags, replica counts) | `environments/<env>.env` | ❌ gitignored (`.env.example` committed as template) |
| Secrets (SECRET_KEY, NIRA_API_KEY, DHIS2_PASSWORD, DB password embedded in DATABASE_URL) | `environments/<env>.env` *or* Crane Cloud secret manager | ❌ never committed |
| Resulting APP_IDs | `environments/<env>.env` after first deploy | ❌ gitignored |
| Operational SLOs that the deploy must meet | [`docs/OBSERVABILITY.md`](../../docs/OBSERVABILITY.md), [`docs/SCALABILITY.md`](../../docs/SCALABILITY.md) | ✅ committed |
| Runbook procedures invoked by alerts | [`docs/RUNBOOK.md`](../../docs/RUNBOOK.md) | ✅ committed |

---

## 7. Secret handling — limitations of the CLI

The `cranecloud apps deploy/update -e KEY=value` flag places secret values on the command line. They are visible to:

- Anyone with shell access to the host running the deploy (via `ps`, `/proc/<pid>/cmdline`).
- The terminal's history file unless `set +o history` (or zsh `setopt hist_ignore_space` + leading space) is used.

For **highly sensitive** secrets (production `SECRET_KEY`, `NIRA_API_KEY`, real DB passwords), prefer:

1. **Set them once via Crane Cloud's web-dashboard secret manager.** Then remove them from your local `.env` after the initial deploy.
2. **Use environment variables sourced from a password manager** (1Password CLI, Bitwarden CLI) at deploy time:
   ```bash
   export SECRET_KEY=$(op read "op://healthsync/production/SECRET_KEY")
   make deploy-backend ENV=production
   ```
3. **Do not commit** any `.env` file containing real secret values. The `.gitignore` rule (`/infra/cranecloud/environments/*.env` is implicitly covered by the root `.env` rule? — **explicit rule below**) protects against accidental commits.

---

## 8. Production-only safeguards

For `ENV=production` we observe the policies from [ADR 0000 governance](../../docs/adr/0000-governance.md) and [INCIDENT_RESPONSE.md](../../docs/INCIDENT_RESPONSE.md):

- **Two-person sign-off** on every production deploy. The deploying operator records the deploy intent in `docs/incidents/deploy-YYYY-MM-DD.md` with the version tag, the reviewer's name, and the rollback plan.
- **No `latest` tags.** Production images are tagged with the release version (e.g. `v0.1.0-pre-pilot.3`). The `production.env.example` enforces this by leaving `BACKEND_IMAGE_TAG=` blank — the deploy fails fast if you forget to set it.
- **DPO sign-off** for deploys that touch privacy-relevant invariants (audit log, consent model, role hierarchy, PII inventory). The CI flags PRs that change these and requires the DPO label on the merge.
- **Two-tier DB role** per [ADR 0010](../../docs/adr/0010-db-append-only-enforcement.md): the runtime DB user is `healthsync_app` (no UPDATE/DELETE on append-only tables); migrations run as `healthsync_admin`. Production `DATABASE_URL` uses the app credentials.

---

## 9. CI/CD pipeline

Two GitHub Actions workflows automate the parts of the rollout that are safe to automate:

### 9.1 `.github/workflows/build-push.yml` — fully automated

- **Triggers:** push to `main`, push of `v*` tags, manual `workflow_dispatch`.
- **What it does:** builds `backend/` and `frontend/` images via `docker/build-push-action` and pushes to `ghcr.io/mpairwe7/healthsync-uganda-{backend,frontend}` with derived tags (`main`, `sha-<short>`, version, `latest` on non-prerelease releases).
- **Auth:** `GITHUB_TOKEN` (no extra secret).
- **After successful build on `main` / `v*`:** dispatches `deploy-cranecloud.yml` automatically — `main` → `staging`, `v*` → `pilot`. Production deploys are *never* automatic; they are operator-triggered via `workflow_dispatch`.

### 9.2 `.github/workflows/deploy-cranecloud.yml` — operator-led

- **Triggers:** `workflow_dispatch` only (manual); also invoked by `build-push.yml` for staging / pilot.
- **Inputs:** `env` (staging/pilot/production), `target` (backend/frontend/both), `image_tag`.
- **Auth path:** pip-installs `cranecloud`, sets `PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring` so the CLI does not require D-Bus / SecretService, and seeds `~/.cranecloud/token` from the environment secret `CRANECLOUD_TOKEN`.
- **Environment protection:** uses GitHub Environments (`cranecloud-staging`, `cranecloud-pilot`, `cranecloud-production`) so production deploys can require manual reviewer approval per [ADR 0000](../../docs/adr/0000-governance.md).
- **Fallback:** if the CLI cannot authenticate (e.g. a future cranecloud version re-introduces a keyring dependency that the null backend cannot satisfy), the job fails loudly and posts the manual-deploy command to the run summary so the operator can run the same rollout from their interactive shell via `make update-*`.

### 9.3 Required GitHub secrets

These are configured per environment (Settings → Environments → cranecloud-<env> → Environment secrets). They are *not* repository-wide secrets because each environment has distinct values.

| Secret name                         | Where to get it                                                | Notes |
| ----------------------------------- | -------------------------------------------------------------- | ----- |
| `CRANECLOUD_TOKEN`                  | `cat ~/.cranecloud/token` after `cranecloud auth login`        | Treat as bearer credential. Rotate per [SECURITY.md](../../docs/SECURITY.md) cadence. |
| `CRANECLOUD_USER_ID`                | `cat ~/.cranecloud/user_id`                                    | |
| `CRANECLOUD_PROJECT_ID`             | `cranecloud projects list` (UUID column)                       | Per-environment value. |
| `CRANECLOUD_BACKEND_APP_ID`         | After first `make deploy-backend ENV=<env>` — captured from CLI output | Per-environment value. |
| `CRANECLOUD_FRONTEND_APP_ID`        | After first `make deploy-frontend ENV=<env>`                   | Per-environment value. |

> The Redis app's `APP_ID` is *not* needed as a GitHub secret because the GHA deploy workflow does not roll out Redis (Redis is a one-time deploy; its image changes very rarely). The `REDIS_APP_ID` lives only in the local `environments/<env>.env` and is used by `make update-redis` when the team rotates the password or bumps the Redis version.

Runtime env vars for the apps (DATABASE_URL, SECRET_KEY, NIRA_*, DHIS2_*) live in **Crane Cloud's web-dashboard secret manager**, not in GitHub Actions secrets. The CI deploy only updates the *image*, not the env vars. This minimises the secret surface in GitHub.

### 9.4 Typical flow

```
git tag v0.1.0-pre-pilot.3
git push origin v0.1.0-pre-pilot.3
   ↓ triggers build-push.yml
   ↓ builds + pushes backend + frontend images to GHCR
   ↓ dispatches deploy-cranecloud.yml (env=pilot, tag=v0.1.0-pre-pilot.3)
   ↓ deploy-cranecloud.yml updates the existing Crane Cloud apps
   ↓ /healthz + /readyz become green on the new image
```

Production deploys deliberately skip the dispatch — to roll out to production, an operator goes to the Actions tab → `Deploy to Crane Cloud` → `Run workflow` → `env=production` → `image_tag=v0.1.0-pre-pilot.3`. The environment's required-reviewers rule then enforces the two-person sign-off from ADR 0000.

---

## 10. Rollback

Crane Cloud retains image history per app. To roll back:

```bash
# Find the previous image tag (from your git log or release tags):
git log --oneline -10

# Update the env file with the previous tag
$EDITOR environments/<env>.env       # set BACKEND_IMAGE_TAG=<previous>
make update-backend ENV=<env>
```

If the rollback target is older than the most recent migration, restore the database first per [BACKUP_RESTORE.md §5](../../docs/BACKUP_RESTORE.md). Application-code rollback without DB rollback can leave the schema ahead of the code — read [RUNBOOK.md RB-12](../../docs/RUNBOOK.md) before doing this in production.

---

## 11. Common errors

| Symptom | Cause | Fix |
| --- | --- | --- |
| `secretstorage.exceptions.ItemNotFoundException` from `cranecloud` | Running from a non-interactive shell without D-Bus / keyring | Run the deploy from your own terminal, not from CI / SSH-without-tty |
| `Missing environments/<env>.env` | `.env` file not created | `cp environments/<env>.env.example environments/<env>.env` and fill in values |
| `BACKEND_APP_ID is not set` on `make update-backend` | First deploy never recorded the APP_ID back into `.env` | Run `make list` to find the UUID, paste into `.env` |
| App deploys but returns 503 from `/readyz` | Backend cannot reach Postgres or Redis | Confirm `DATABASE_URL` / `REDIS_URL` resolve from Crane Cloud's network; check Crane Cloud add-on bindings |
| 401 from `/api/v1/patients` | Wrong `SECRET_KEY` between deploy and consumer | The JWT signing key changed; users must re-authenticate. If unintended, redeploy with the previous `SECRET_KEY` |
| CORS errors in the browser | `CORS_ALLOW_ORIGINS` doesn't include the frontend URL | Edit the env file, redeploy backend |

---

## 12. Cross-references

- [`manifest.yaml`](./manifest.yaml) — the source of truth for what gets deployed.
- [`Makefile`](./Makefile) — `make help` from this directory lists all targets.
- [`../../.github/workflows/build-push.yml`](../../.github/workflows/build-push.yml) — GHCR build + push automation.
- [`../../.github/workflows/deploy-cranecloud.yml`](../../.github/workflows/deploy-cranecloud.yml) — CI-driven deploy to Crane Cloud.
- [`docs/DEPLOYMENT.md`](../../docs/DEPLOYMENT.md) — broader deployment topology (Compose, Kubernetes, Crane Cloud).
- [`docs/SECURITY.md`](../../docs/SECURITY.md) — key-rotation cadence, secret-management policy.
- [`docs/ROADMAP.md`](../../docs/ROADMAP.md) — deployment-shape progression: pilot → regional → national.
