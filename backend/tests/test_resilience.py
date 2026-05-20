"""Unit tests for the resilience primitives."""

import asyncio

import pytest

from app.core.resilience import (
    BreakerState,
    CircuitBreaker,
    UpstreamUnavailable,
    retry,
)


@pytest.mark.asyncio
async def test_breaker_opens_after_threshold():
    cb = CircuitBreaker(name="test", failure_threshold=3, recovery_timeout=0.05)

    async def boom():
        raise RuntimeError("bang")

    for _ in range(3):
        with pytest.raises(RuntimeError):
            await cb.call(boom)
    assert cb.state == BreakerState.OPEN

    with pytest.raises(UpstreamUnavailable):
        await cb.call(boom)

    await asyncio.sleep(0.06)

    async def ok():
        return "ok"

    assert await cb.call(ok) == "ok"
    assert cb.state == BreakerState.CLOSED


@pytest.mark.asyncio
async def test_retry_succeeds_eventually():
    attempts = {"n": 0}

    @retry(attempts=4, base_delay_ms=1)
    async def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("flaky")
        return "done"

    assert await flaky() == "done"
    assert attempts["n"] == 3


@pytest.mark.asyncio
async def test_retry_gives_up():
    @retry(attempts=2, base_delay_ms=1)
    async def always_fails():
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError):
        await always_fails()
