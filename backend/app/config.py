"""Application configuration — loaded once from env, immutable thereafter."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strict, immutable settings loaded from environment variables.

    All access goes through `get_settings()` so the import-graph stays clean
    and tests can override via environment without monkey-patching.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )

    # ── Application ──────────────────────────────────────────────────────
    app_env: Literal["development", "staging", "production", "test"] = "development"
    app_name: str = "healthsync-uganda"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    secret_key: SecretStr = Field(
        default=SecretStr("dev-secret-change-me-please-32-bytes"),
        description="Used for JWT signing and Fernet encryption of PII fields.",
    )

    # ── Database ─────────────────────────────────────────────────────────
    database_url: str = Field(
        default="sqlite+aiosqlite:///./healthsync.db",
        description="Async SQLAlchemy URL. Default falls back to SQLite for laptop demos.",
    )
    database_echo: bool = False
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # Schema bootstrap for dev/staging only. When true, the lifespan hook
    # runs `Base.metadata.create_all` on startup — idempotent (only creates
    # missing tables; never ALTERs existing ones). Defaults to False so
    # production deploys must apply Alembic migrations explicitly
    # (`uv run alembic upgrade head`). The dev `scripts/dev-stack.sh` and
    # staging compose files set `AUTO_CREATE_SCHEMA=true` to keep first-
    # deploy ergonomics. Setting this true in production is a config bug
    # — main.py logs a WARNING at startup if it observes that combination.
    auto_create_schema: bool = False

    # Run `alembic upgrade head` on startup. Necessary on platforms (e.g.
    # Crane Cloud) where there's no separate migration step in the deploy
    # pipeline. The lifespan hook detects a DB bootstrapped via create_all
    # (no `alembic_version` table) and stamps it at the last pre-Alembic
    # revision before upgrading, so this is safe to enable on existing
    # staging databases. Defaults False; staging / pilot turn it on
    # through cranecloud env vars.
    auto_migrate: bool = False

    # ── Redis ────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Observability ────────────────────────────────────────────────────
    otel_exporter_otlp_endpoint: str | None = None
    otel_service_name: str = "healthsync-api"
    otel_traces_sampler: str = "parentbased_always_on"

    # ── External integrations ────────────────────────────────────────────
    # Default points to in-process mocks under /api/v1/interop/mock/*; override
    # to real NIRA / DHIS2 hosts in production deployments.
    nira_base_url: str = "http://localhost:8000/api/v1/interop/mock/nira"
    nira_api_key: SecretStr = SecretStr("mock-nira-key")
    dhis2_base_url: str = "http://localhost:8000/api/v1/interop/mock/dhis2"
    dhis2_username: str = "mock"
    dhis2_password: SecretStr = SecretStr("mock")

    # ── Resilience ───────────────────────────────────────────────────────
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout_seconds: int = 30
    retry_max_attempts: int = 4
    retry_base_delay_ms: int = 200

    # ── CORS ─────────────────────────────────────────────────────────────
    cors_allow_origins: list[str] = ["http://localhost:3000"]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Memoised settings instance. Call from anywhere in the app."""
    return Settings()
