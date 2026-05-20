-- Extensions required by HealthSync.
CREATE EXTENSION IF NOT EXISTS "pgcrypto";       -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "pg_trgm";        -- trigram search on names
CREATE EXTENSION IF NOT EXISTS "btree_gin";      -- composite GIN indexes
