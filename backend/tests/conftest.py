"""Shared pytest fixtures — in-memory SQLite, isolated per test."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.db.base import Base


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture()
async def db_session() -> AsyncIterator[AsyncSession]:
    # Reload settings to a sqlite memory DB so tests are isolated
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest.fixture()
async def client() -> AsyncIterator[AsyncClient]:
    # Set env so the app uses sqlite in-memory
    import os

    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    os.environ["APP_ENV"] = "test"
    # Force-enable auto-create for tests — the default was flipped to False
    # so production deploys must run alembic explicitly. Tests get the
    # ergonomic in-memory schema bootstrap via this override.
    os.environ["AUTO_CREATE_SCHEMA"] = "true"
    get_settings.cache_clear()

    from app.main import create_app
    from app.services.nira_client import NinVerification, NiraClient, get_nira_client
    from sqlalchemy import select
    from app.db.models.patient import Patient
    from app.db.session import get_db

    app = create_app()

    # In-process NIRA stub: the real client makes an HTTP call to the mock
    # mounted at /api/v1/interop/mock/nira/verify/{nin}, which isn't routable
    # from inside the test ASGI transport. Override the dependency to query
    # the same in-memory DB directly — preserves the demo invariant "NIRA
    # verifies any seeded patient" without standing up a second loopback.
    class _StubNira:
        async def verify_nin(self, nin: str) -> NinVerification:
            async for session in get_db():
                p = (
                    await session.scalars(select(Patient).where(Patient.nin == nin))
                ).one_or_none()
                if p is None:
                    return NinVerification(nin=nin, found=False)
                return NinVerification(
                    nin=nin,
                    found=True,
                    full_name=f"{p.given_name} {p.family_name}",
                    gender=p.gender,
                    date_of_birth=p.birth_date.isoformat(),
                    district=p.district,
                )
            return NinVerification(nin=nin, found=False)

        async def aclose(self) -> None:
            return None

    app.dependency_overrides[get_nira_client] = lambda: _StubNira()  # type: ignore[assignment]

    # The Redis singleton in app.core.redis_client is module-global. Across
    # tests pytest-asyncio creates fresh event loops, but a leftover Redis
    # client retains references to the previous loop and explodes on close.
    # Reset it before each test so the lifespan boot can rebind cleanly.
    import app.core.redis_client as redis_module

    redis_module._client = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        async with app.router.lifespan_context(app):
            try:
                yield c
            finally:
                # Suppress the noisy "Event loop is closed" raised by the
                # Redis client during teardown — it's a known pytest-anyio
                # interaction (the runner closes its loop before the
                # lifespan shutdown awaits the redis aclose). The test
                # assertions have all run by this point.
                try:
                    await redis_module.close_redis()
                except RuntimeError:
                    pass
                redis_module._client = None
