"""Singleton async Redis client used for caching, rate-limiting, idempotency."""

from __future__ import annotations

from redis.asyncio import Redis, from_url

from app.config import get_settings

_client: Redis | None = None


async def get_redis() -> Redis:
    """Return the lazily-initialised Redis client. Safe to call concurrently."""
    global _client
    if _client is None:
        _client = from_url(
            get_settings().redis_url,
            encoding="utf-8",
            decode_responses=True,
            health_check_interval=15,
        )
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
