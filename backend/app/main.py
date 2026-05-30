"""FastAPI application entrypoint.

Lifespan boots: logging → telemetry → DB schema (dev) → Redis ping → seed (dev).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_v1_router
from app.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.core.redis_client import close_redis, get_redis
from app.core.telemetry import setup_telemetry
from app.db.base import Base
from app.db.models import *  # noqa: F403  — register models
from app.db.session import dispose_engine, get_engine
from app.fhir.endpoints import fhir_router
from app.middleware.audit_context import AuditContextMiddleware
from app.middleware.idempotency import IdempotencyMiddleware
from app.middleware.rate_limit import RateLimitMiddleware

# Resolve at import time — keeps the async lifespan body off of any
# pathlib calls (ASYNC240). `/app` in the Docker image; `backend/` locally.
_BACKEND_ROOT = str(Path(__file__).resolve().parents[1])

logger = get_logger(__name__)


# Revisions used by the stamp-detection logic below.
#   - _PRE_SWEEP_HEAD: state after the last revision *before* the compliance
#     sweep. Any DB bootstrapped via create_all with the pre-sweep ORM
#     matches this state.
#   - _A01_HEAD: state after schema additions (enrolling_facility_id,
#     enrolling_district, composite indexes). A DB bootstrapped via the
#     post-sweep ORM via create_all matches this — the new columns exist
#     but A02 backfill + A03 constraints/triggers haven't run.
_PRE_SWEEP_HEAD = "c07e02b0024b"
_A01_HEAD = "a01_patient_facility"


async def _run_alembic_upgrade() -> None:
    """Run `alembic upgrade head` from inside the application process.

    Detects three bootstrap states and stamps appropriately:
      1. Fresh DB → no tables → run all migrations from base.
      2. Bootstrapped via create_all with PRE-sweep ORM → stamp pre-sweep
         head, then A01+A02+A03 add the new columns and constraints.
      3. Bootstrapped via create_all with POST-sweep ORM → new columns
         already present → stamp A01, then A02 backfill + A03 constraints.

    Idempotent: running against a DB already at head is a no-op.
    """
    from alembic.config import Config
    from sqlalchemy import inspect

    from alembic import command

    engine = get_engine()

    # Detect bootstrap state. Three signals:
    #   has_alembic_version  — has alembic ever been run?
    #   has_patients         — was the DB bootstrapped at all?
    #   has_new_columns      — did the create_all use post-sweep ORM?
    async with engine.connect() as conn:

        def _inspect(sync_conn) -> dict:
            insp = inspect(sync_conn)
            has_av = insp.has_table("alembic_version")
            has_pt = insp.has_table("patients")
            has_new = False
            if has_pt:
                cols = {c["name"] for c in insp.get_columns("patients")}
                has_new = "enrolling_facility_id" in cols
            return {
                "has_alembic_version": has_av,
                "has_patients": has_pt,
                "has_new_columns": has_new,
            }

        state = await conn.run_sync(_inspect)

    # Alembic's command API is sync; the engine creation inside env.py reads
    # DATABASE_URL from settings directly, so we just point Alembic at the
    # backend's alembic.ini and let it do its thing.
    alembic_cfg = Config(f"{_BACKEND_ROOT}/alembic.ini")
    alembic_cfg.set_main_option("script_location", f"{_BACKEND_ROOT}/alembic")

    def _do_migrate() -> None:
        if not state["has_alembic_version"] and state["has_patients"]:
            stamp_at = _A01_HEAD if state["has_new_columns"] else _PRE_SWEEP_HEAD
            logger.info(
                "schema.stamping_existing_db",
                revision=stamp_at,
                has_new_columns=state["has_new_columns"],
            )
            command.stamp(alembic_cfg, stamp_at)
        command.upgrade(alembic_cfg, "head")

    # alembic.command.upgrade is sync — run it in a thread so we don't
    # block the event loop. The migration itself uses its own sync engine
    # (see alembic/env.py) so this doesn't conflict with the app's engine.
    import asyncio

    await asyncio.to_thread(_do_migrate)


_PLACEHOLDER_MARKER = "change-me"


def _check_production_secrets(settings: Settings) -> None:
    """Refuse to boot a non-local deployment that still uses placeholder secrets.

    A staging/production instance running with the default SECRET_KEY signs JWTs
    with a value committed to the source tree — anyone could forge a
    ministry_admin token. Fail fast rather than serve forgeable credentials.
    Development/test envs are exempt so the demo stays friction-free.
    """
    if settings.app_env not in ("staging", "production"):
        return
    secret = settings.secret_key.get_secret_value()
    if _PLACEHOLDER_MARKER in secret.lower() or len(secret) < 32:
        raise RuntimeError(
            "SECRET_KEY is unset, a placeholder, or shorter than 32 bytes while "
            f"APP_ENV={settings.app_env}. Generate one with `openssl rand -hex 32` "
            "and set it before starting."
        )
    if (
        settings.nira_api_key.get_secret_value() == "mock-nira-key"
        or settings.dhis2_password.get_secret_value() == "mock"
    ):
        logger.warning(
            "integration.mock_credentials",
            impact=(
                f"NIRA/DHIS2 still use mock credentials with APP_ENV="
                f"{settings.app_env}. Real integrations will not work until these "
                "are overridden."
            ),
        )


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level, json_output=settings.is_production)
    logger.info("startup", env=settings.app_env, version="0.1.0")

    # Fail fast if a non-local deployment is still on placeholder secrets —
    # forgeable JWTs are worse than a failed boot.
    _check_production_secrets(settings)

    # Auto-create schema bootstrap. Default-off in production: prod deploys
    # must run `alembic upgrade head` explicitly so column-level changes
    # (which create_all silently skips) reach Postgres. Dev/staging keep
    # this on for first-deploy ergonomics. See app/config.py for context.
    if settings.auto_create_schema:
        if settings.is_production:
            logger.warning(
                "schema.auto_create_in_production",
                impact=(
                    "AUTO_CREATE_SCHEMA=true in production hides migration "
                    "drift — create_all skips ALTERs. Run `alembic upgrade "
                    "head` and unset AUTO_CREATE_SCHEMA."
                ),
            )
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("schema.create_all_complete", env=settings.app_env)

    # Auto-migrate hook — for managed platforms (Crane Cloud, Fly, Render)
    # where there's no separate migration step in the deploy pipeline.
    # Idempotent: if the DB is at head, alembic exits cleanly. If the DB
    # was bootstrapped via create_all (no `alembic_version` table), we
    # stamp it at the last pre-sweep revision before upgrading so the
    # already-applied DDL isn't re-run.
    if settings.auto_migrate:
        try:
            await _run_alembic_upgrade()
            logger.info("schema.alembic_upgrade_complete", env=settings.app_env)
        except Exception as exc:
            logger.error(
                "schema.alembic_upgrade_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            # Re-raise so the pod doesn't serve traffic on a broken schema.
            # Crane Cloud will surface the failure via the health check.
            raise

    # Warm Redis. Service boots even if Redis is down (middlewares degrade
    # open), but several features lose fidelity — log loudly so the
    # operator notices before users do.
    try:
        redis = await get_redis()
        await redis.ping()
        logger.info("redis_ready", url=settings.redis_url)
    except Exception as exc:
        if settings.is_production:
            logger.error(
                "redis_unavailable",
                url=settings.redis_url,
                error=str(exc),
                impact=(
                    "Idempotency replay, rate-limit, analytics cache and DHIS2 outbox "
                    "are degraded. Bring Redis up before serving real traffic."
                ),
            )
        else:
            logger.warning(
                "redis_unavailable",
                url=settings.redis_url,
                error=str(exc),
                hint="Run `scripts/dev-stack.sh` to start Postgres + Redis.",
            )

    yield

    logger.info("shutdown")
    await close_redis()
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="HealthSync Uganda",
        version="0.1.0",
        description=(
            "Interoperable National Digital Health Platform — patient records, "
            "supply-chain visibility, FHIR R4 exchange."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
    )
    app.add_middleware(AuditContextMiddleware)
    app.add_middleware(IdempotencyMiddleware)
    app.add_middleware(RateLimitMiddleware)

    setup_telemetry(app)

    app.include_router(api_v1_router, prefix="/api/v1")
    app.include_router(fhir_router, prefix="/fhir")

    @app.get("/healthz", include_in_schema=False, tags=["health"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False, tags=["health"])
    async def readyz() -> JSONResponse:
        """Readiness — Redis + DB are reachable.

        Returns 200 when both are healthy, 503 with a structured body when
        anything is degraded so Kubernetes / load balancers can route around
        the instance during a Redis blip.
        """
        checks: dict[str, str] = {}
        ok = True

        try:
            redis = await get_redis()
            await redis.ping()
            checks["redis"] = "ok"
        except Exception as exc:
            checks["redis"] = f"down: {exc}"
            ok = False

        try:
            from sqlalchemy import text

            async with get_engine().connect() as conn:
                await conn.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as exc:
            checks["database"] = f"down: {exc}"
            ok = False

        status_code = 200 if ok else 503
        return JSONResponse(
            content={"status": "ready" if ok else "degraded", "checks": checks},
            status_code=status_code,
        )

    @app.get("/", include_in_schema=False)
    async def root(s: Annotated[Settings, Depends(get_settings)]) -> dict[str, str]:
        return {
            "service": s.app_name,
            "version": "0.1.0",
            "docs": "/docs",
            "fhir": "/fhir/metadata",
        }

    return app


app = create_app()
