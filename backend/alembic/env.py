"""Alembic env.py — HealthSync Uganda.

Designed to work with the application's async SQLAlchemy engine:

* Reads the DATABASE_URL from the application's Settings (so a single source
  of truth — no separate alembic-specific URL).
* Imports the project's `Base` and all model modules (registers all 11 tables
  in `Base.metadata`).
* Translates async URL drivers (postgresql+asyncpg / sqlite+aiosqlite) to
  their sync equivalents (postgresql+psycopg / sqlite) for Alembic's sync
  context. Alembic itself is sync-only; using sync drivers keeps the env.py
  small and matches every other major project's convention (FastAPI Users,
  Pyramid, etc.).
* Honors `compare_type` and `compare_server_default` so future migrations
  catch type-narrowing changes (String(80) → String(40)) and DDL-default
  changes the developer might intend to commit.

To generate a migration after a model change:
    cd backend
    uv run alembic revision --autogenerate -m "describe the change"

To apply migrations against the configured DATABASE_URL:
    uv run alembic upgrade head
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# ── Make the `app` package importable ────────────────────────────────────
# Alembic runs from backend/, which is the project root for the backend.
# Ensure ./app is on sys.path so we can import Base + models.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402
import app.db.models  # noqa: F401, E402 — registers all ORM models with Base.metadata

# ── Alembic config ───────────────────────────────────────────────────────
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _sync_url() -> str:
    """Translate the app's async DATABASE_URL into a sync URL for Alembic.

    Alembic is sync-only. The app's engine uses `+asyncpg` or `+aiosqlite`;
    map those to drivers Alembic understands.
    """
    url = os.environ.get("DATABASE_URL") or get_settings().database_url
    return (
        url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
           .replace("sqlite+aiosqlite://", "sqlite://")
    )


# Provide the URL to Alembic at runtime (overrides the placeholder in alembic.ini)
config.set_main_option("sqlalchemy.url", _sync_url())

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Render the SQL to stdout without connecting to a DB."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect to the DB and apply migrations."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
