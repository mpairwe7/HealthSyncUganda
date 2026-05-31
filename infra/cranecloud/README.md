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
| **PostgreSQL** | **Crane Cloud managed DaaS** (Project → Databases → + New Database → PostgreSQL) — *not* a Crane Cloud app | Managed by the platform | **Durable, platform-managed storage.** The backend connects via `DATABASE_URL`; it creates the `pgcrypto` / `pg_trgm` / `btree_gin` extensions itself at startup (`backend/app/main.py _ensure_postgres_extensions`), so no custom image or `init.sql` is needed on the server. |
| **Redis** | Crane Cloud app — `cranecloud apps deploy` | `redis:7-alpine` (Docker Hub) | Deployed with `--requirepass` + 256 MB cap + LRU eviction. |
| **Backend (FastAPI)** | Crane Cloud app | `docker.io/mpairwe7/healthsync-uganda-backend:<tag>` | Built and pushed by `.github/workflows/build-push.yml`. |
| **Frontend (Next.js)** | Crane Cloud app | `docker.io/mpairwe7/healthsync-uganda-frontend:<tag>` | Built and pushed by the same workflow. |
| OpenTelemetry collector | Optional external — point `OTEL_EXPORTER_OTLP_ENDPOINT` at any OTLP receiver. Leave blank to disable. | — | Not part of the Crane Cloud project. |

The `make deploy ENV=<env>` target deploys the three Crane Cloud apps in order: **redis → backend → frontend**. Postgres is the managed DaaS — provision it first (Project → Databases) and set `DATABASE_URL` in `environments/<env>.env` before `deploy-backend`. The backend/frontend depend on the DaaS + redis being reachable; the chain order matters.

### 0.1 Persistence: Postgres is durable (DaaS); Redis is ephemeral

**Postgres** is the Crane Cloud managed DaaS — durable, platform-managed storage — so the old self-hosted "pod restart = data loss" risk no longer applies to the database. (Still run scheduled `pg_dump` backups per [`docs/BACKUP_RESTORE.md`](../../docs/BACKUP_RESTORE.md) for point-in-time recovery and an off-platform copy.)

**Redis** remains a Crane Cloud app, and Crane Cloud does not document persistent volumes for app containers, so treat Redis as **ephemeral** — any pod restart resets it. This is bounded:

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
3. **Container images** published to Docker Hub (Crane Cloud's RENU/AHUMAIN ML clusters do not pull from `ghcr.io` — see §9.1 for context):
   - `docker.io/mpairwe7/healthsync-uganda-postgres:<tag>`
   - `docker.io/mpairwe7/healthsync-uganda-backend:<tag>`
   - `docker.io/mpairwe7/healthsync-uganda-frontend:<tag>`
   - Repos under your Docker Hub account must be **Public** (or paste a private-image PAT into the Crane Cloud "Private Image" deploy form per app).
4. **Redis** is deployed from the official upstream `redis:7-alpine` (Docker Hub). **Postgres** is the custom image above. Both run as Crane Cloud apps, not external managed services. See §0.1 for the durability caveat.

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
- **What it does:** builds `backend/`, `frontend/`, and `infra/postgres/` images via `docker/build-push-action` and pushes to `docker.io/<user>/healthsync-uganda-{backend,frontend,postgres}` with derived tags (`main`, `sha-<short>`, version, `latest` on non-prerelease releases).
- **Registry choice — Docker Hub, not GHCR.** Crane Cloud's RENU and AHUMAIN ML clusters (the two available on the project's account as of 2026-05-26) cannot pull from `ghcr.io`; identical-shape pulls from Docker Hub work cleanly. Until Crane Cloud enables GHCR access on the relevant clusters, Docker Hub is the registry of record.
- **Auth:** repo variable `DOCKERHUB_USER` (defaults to `mpairwe7`) + repo secret `DOCKERHUB_TOKEN` (Docker Hub PAT scoped Read & Write on Repos).
- **After successful build on `main` / `v*`:** dispatches `deploy-cranecloud.yml` automatically — `main` → `staging`, `v*` → `pilot`. Production deploys are *never* automatic; they are operator-triggered via `workflow_dispatch`.

### 9.2 `.github/workflows/deploy-cranecloud.yml` — operator-led

- **Triggers:** `workflow_dispatch` only (manual); also invoked by `build-push.yml` for staging / pilot.
- **Inputs:** `env` (staging/pilot/production), `target` (backend/frontend/both), `image_tag`.
- **Auth path:** pip-installs `cranecloud`, sets `PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring` so the CLI does not require D-Bus / SecretService, and seeds `~/.cranecloud/token` from the environment secret `CRANECLOUD_TOKEN`.
- **Environment protection:** uses GitHub Environments (`cranecloud-staging`, `cranecloud-pilot`, `cranecloud-production`) so production deploys can require manual reviewer approval per [ADR 0000](../../docs/adr/0000-governance.md).
- **Fallback:** if the CLI cannot authenticate (e.g. a future cranecloud version re-introduces a keyring dependency that the null backend cannot satisfy), the job fails loudly and posts the manual-deploy command to the run summary so the operator can run the same rollout from their interactive shell via `make update-*`.

### 9.3 Required GitHub secrets

#### Repository-wide (used by `build-push.yml`)

| Setting | Type | Source | Notes |
| --- | --- | --- | --- |
| `DOCKERHUB_USER` | **variable** (not secret) | Your Docker Hub username; defaults to `mpairwe7` if unset | Plain identifier; visible in workflow logs by design |
| `DOCKERHUB_TOKEN` | **secret** | <https://hub.docker.com/settings/security/personal-access-tokens> → New PAT → **Read & Write** on `Repos` | Treat as bearer credential; rotate annually or on incident |

#### Per environment (used by `deploy-cranecloud.yml`)

Configured per environment (Settings → Environments → cranecloud-<env> → Environment secrets). They are *not* repository-wide secrets because each environment has distinct values.

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

## 10A. Crane Cloud operational quirks (learned 2026-05-25 / 2026-05-26)

These are real platform behaviours that surprised us during the live staging deployment. Document them here so the next operator doesn't burn an hour rediscovering each one.

### Image URL format
- **No `docker.io/` prefix** — `cranecloud apps deploy --image docker.io/landwind/...` fails with "does not exist or is private". Use the short form `landwind/healthsync-uganda-backend:main`. This is undocumented; the failure message is misleading.
- Public Docker Hub images work; GHCR (`ghcr.io/...`) does NOT work from the RENU and AHUMAIN ML clusters (only Docker Hub). See §9.1.

### Container ports
- **Containers must listen on port 3000 internally**, regardless of what you pass to `--port`. Crane Cloud's public ingress proxies HTTPS:443 → container:3000 by convention. Apps that listen on other ports (e.g. uvicorn defaulting to 8000, redis on 6379) are not reachable through the public URL.
- Backend therefore needs `--command 'uvicorn app.main:app --host 0.0.0.0 --port 3000 ...'` (override the Dockerfile's port-8000 CMD).
- Postgres and Redis bind to their canonical ports (5432, 6379) inside the container; the K8s **service** still seems to use port 3000 as the publicly-reported port (cranecloud's "Internal Url" always renders `:3000` for any app). Use **port 3000** in `DATABASE_URL` / `REDIS_URL` when referring to those services from another pod.

### Env-var updates
- **`cranecloud apps update -e KEY=value` does NOT actually update env vars** (or at least doesn't restart the pod to pick them up). The CLI reports "App updated successfully" but `cranecloud apps info` shows the OLD env. To change env vars, you must **delete and redeploy** the app. This changes the public URL hex segment, which breaks any links you've shared.
- Implication for the CI/CD workflow: `deploy-cranecloud.yml` only updates the **image** via `apps update --image`; env changes still require a manual delete-and-redeploy.

### CLI argument idiosyncrasies
- `cranecloud apps delete <APP_ID>` and `cranecloud projects delete <PROJECT_ID>` use **positional** arguments, not `--id`. The error message helpfully tells you so.
- `cranecloud projects create --cluster_id <UUID>` **fails with a simplejson serialisation error** on the CLI's own UUID type. Workaround: `cranecloud clusters use-cluster <UUID>` first to set the default cluster, then `cranecloud projects create` (no `--cluster_id` flag).
- `cranecloud auth user` and other commands **read env vars from a secret-storage helper**. In non-tty / CI runners the default `keyring.backends.null.Keyring` silently drops writes; the workflow must set `PYTHON_KEYRING_BACKEND=keyrings.alt.file.PlaintextKeyring` (provided by the `keyrings.alt` pip package) for the token-file path to work.

### Status reporting
- Newly-deployed TCP services (Postgres, Redis) initially show **`failed`** for ~60 seconds, then flip to `running` once the readiness probe settles. Don't delete a "failed" app immediately after deploy — wait 1–2 minutes.
- A `running` app can still 502 on the public URL for ~30s after deploy while the ingress catches up.
- An app that's been recreated gets a NEW URL hex (e.g. `…-9a1442da.renu-01.cranecloud.io` → `…-9b4ecff1.…`). The Internal Url's hex also changes. **Any URL stored elsewhere (env vars in other apps, GitHub Actions secrets, README links) must be updated.**

### Cluster availability
- Three clusters listed by `cranecloud clusters list`: `makerere-1`, `Research and Education Network for Uganda` (RENU), `AHUMAIN ML`. The `makerere-1` cluster is **platform-disabled** — `projects create` against it returns "cluster is disabled". Only RENU and AHUMAIN ML are usable on the current account.

### Persistence
- **No persistent volumes for app containers** are documented for any cluster (as of 2026-05-26). Treat Postgres and Redis as **ephemeral**; pod restart = fresh data dir. Operate `pg_dump → external object store` per [BACKUP_RESTORE.md](../../docs/BACKUP_RESTORE.md) before any environment holds real PHI.
- Crane Cloud's managed **PostgreSQL DaaS** does persist (separate from app containers). See §0.2 for the fallback path.

### Secrets exposure
- **`cranecloud apps info` displays env-var values in plaintext** — including secrets like `SECRET_KEY` and password-bearing connection strings. Anyone with `cranecloud apps info <APP_ID>` access can read these. Mitigation: rotate secrets when staff with project access leave; minimise the number of operators with the cranecloud token.

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
