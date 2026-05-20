"""FastAPI application entrypoint.

Lifespan boots: logging → telemetry → DB schema (dev) → Redis ping → seed (dev).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated, AsyncIterator

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from app.api.v1.router import api_v1_router
from app.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.core.redis_client import close_redis, get_redis
from app.core.telemetry import setup_telemetry
from app.db.base import Base
from app.db.models import *  # noqa: F401, F403  — register models
from app.db.session import dispose_engine, get_engine
from app.fhir.endpoints import fhir_router
from app.middleware.audit_context import AuditContextMiddleware
from app.middleware.idempotency import IdempotencyMiddleware
from app.middleware.rate_limit import RateLimitMiddleware

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level, json_output=settings.is_production)
    logger.info("startup", env=settings.app_env, version="0.1.0")

    # Dev convenience: auto-create schema if migrations haven't been run.
    if settings.app_env in {"development", "test"}:
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    # Warm Redis. Service boots even if Redis is down (middlewares degrade
    # open), but several features lose fidelity — log loudly so the
    # operator notices before users do.
    try:
        redis = await get_redis()
        await redis.ping()
        logger.info("redis_ready", url=settings.redis_url)
    except Exception as exc:  # noqa: BLE001
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
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
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
    async def readyz() -> ORJSONResponse:
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
        except Exception as exc:  # noqa: BLE001
            checks["redis"] = f"down: {exc}"
            ok = False

        try:
            from sqlalchemy import text

            async with get_engine().connect() as conn:
                await conn.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as exc:  # noqa: BLE001
            checks["database"] = f"down: {exc}"
            ok = False

        status_code = 200 if ok else 503
        return ORJSONResponse(
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
