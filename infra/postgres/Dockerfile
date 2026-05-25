# HealthSync Postgres image — `postgres:16-alpine` with the project's
# required extensions (pgcrypto, pg_trgm, btree_gin) baked in via the
# postgres docker-entrypoint initdb mechanism.
#
# Used on Crane Cloud where the platform does not support
# `volumes:` mounts for `:/docker-entrypoint-initdb.d/`. For local
# `docker compose up` this image is functionally equivalent to the
# upstream postgres:16-alpine + the bind-mounted init.sql.
#
# Build:    docker build -t ghcr.io/mpairwe7/healthsync-uganda-postgres:<tag> infra/postgres
# Push:     done automatically by .github/workflows/build-push.yml
# Deploy:   `make -C infra/cranecloud deploy-postgres ENV=<env>`

FROM postgres:16-alpine

# init.sql runs on first start (only when the data directory is empty).
# It is idempotent (`CREATE EXTENSION IF NOT EXISTS …`) so the no-op
# case on subsequent restarts is safe.
COPY init.sql /docker-entrypoint-initdb.d/00-healthsync-init.sql

# Persistent state lives at /var/lib/postgresql/data. On Crane Cloud,
# this directory's persistence depends on whether the platform provides
# per-app persistent storage (not documented as of 2026-05-25). For pilot
# we assume ephemeral and rely on scheduled pg_dump to external storage —
# see infra/cranecloud/README.md "Persistence caveat for self-hosted DB".

EXPOSE 5432
