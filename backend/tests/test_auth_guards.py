"""Production-safety guards: the startup secret check (C1) and the citizen OTP
production gate (C2)."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.main import _check_production_secrets


def _settings(**overrides) -> Settings:
    base: dict = {"app_env": "production", "secret_key": "a" * 64}
    base.update(overrides)
    return Settings(**base)


def test_secret_guard_rejects_placeholder_in_production():
    s = _settings(secret_key="change-me-to-32-bytes-of-randomness-please")
    with pytest.raises(RuntimeError):
        _check_production_secrets(s)


def test_secret_guard_rejects_short_secret_in_staging():
    s = _settings(app_env="staging", secret_key="too-short")
    with pytest.raises(RuntimeError):
        _check_production_secrets(s)


def test_secret_guard_allows_strong_secret_in_production():
    # 64-char non-placeholder secret — must not raise.
    _check_production_secrets(_settings())


def test_secret_guard_noop_in_development():
    # Development uses the default placeholder secret, but the guard is a no-op
    # outside staging/production.
    _check_production_secrets(_settings(app_env="development"))


@pytest.mark.anyio
async def test_citizen_otp_login_refused_in_production(monkeypatch):
    """C2: the fixed-OTP citizen stub must not authenticate in production."""
    from httpx import ASGITransport, AsyncClient

    from app.config import get_settings

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "x" * 64)  # strong, so the C1 guard passes
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("AUTO_CREATE_SCHEMA", "false")
    monkeypatch.setenv("AUTO_MIGRATE", "false")
    get_settings.cache_clear()

    import app.core.redis_client as redis_module

    redis_module._client = None

    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            async with app.router.lifespan_context(app):
                res = await c.post(
                    "/api/v1/auth/citizen/login",
                    json={"nin": "CM85051712345X", "otp": "000000"},
                )
        assert res.status_code == 503, res.text
    finally:
        try:
            await redis_module.close_redis()
        except RuntimeError:
            pass
        redis_module._client = None
        get_settings.cache_clear()
