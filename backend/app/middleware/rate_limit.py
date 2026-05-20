"""Lightweight token-bucket rate limiter backed by Redis.

This is not a substitute for an API gateway in production — it's a fail-safe
that keeps the service healthy if it is exposed directly. Limits degrade
open: if Redis is unavailable, we let traffic through and log loudly.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.logging import get_logger
from app.core.redis_client import get_redis

logger = get_logger(__name__)

LIMIT_PER_MINUTE = 600
WINDOW_SECONDS = 60


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        client = request.client.host if request.client else "anonymous"
        bucket = f"ratelimit:{client}:{request.url.path}"

        try:
            redis = await get_redis()
            current = await redis.incr(bucket)
            if current == 1:
                await redis.expire(bucket, WINDOW_SECONDS)
        except Exception as exc:
            logger.warning("ratelimit.disabled", error=str(exc))
            return await call_next(request)

        if current > LIMIT_PER_MINUTE:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded — please retry in a moment.",
                    "limit_per_minute": LIMIT_PER_MINUTE,
                },
                headers={"Retry-After": str(WINDOW_SECONDS)},
            )

        return await call_next(request)
