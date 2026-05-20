"""Idempotency-Key support for unsafe methods.

Offline-first clients retry mutations when the network reappears. Without
idempotency, a duplicate POST creates a duplicate record. Clients send an
`Idempotency-Key` header (any opaque string, ≤ 128 chars); we cache the first
response and replay it on subsequent attempts within a 24-hour window.
"""

from __future__ import annotations

import hashlib

import orjson
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_logger
from app.core.redis_client import get_redis

logger = get_logger(__name__)

IDEMPOTENCY_HEADER = "Idempotency-Key"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
TTL_SECONDS = 24 * 60 * 60


class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        if request.method in SAFE_METHODS:
            return await call_next(request)

        key = request.headers.get(IDEMPOTENCY_HEADER)
        if not key:
            return await call_next(request)

        # Bind cache to (method, path, key) so the same key on different
        # endpoints does not collide. Hash to keep Redis keys short.
        cache_key = "idempotency:" + hashlib.sha256(
            f"{request.method}:{request.url.path}:{key}".encode()
        ).hexdigest()

        try:
            redis = await get_redis()
            cached = await redis.get(cache_key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("idempotency.cache_unavailable", error=str(exc))
            return await call_next(request)

        if cached:
            payload = orjson.loads(cached)
            logger.info("idempotency.replay", key=key, path=request.url.path)
            return Response(
                content=payload["body"].encode("utf-8"),
                status_code=payload["status"],
                headers={**payload["headers"], "X-Idempotent-Replay": "true"},
                media_type=payload.get("media_type"),
            )

        response = await call_next(request)

        # Cache only successful 2xx writes
        if 200 <= response.status_code < 300:
            body = b""
            async for chunk in response.body_iterator:  # type: ignore[attr-defined]
                body += chunk
            try:
                await redis.set(
                    cache_key,
                    orjson.dumps(
                        {
                            "status": response.status_code,
                            "headers": dict(response.headers),
                            "body": body.decode("utf-8"),
                            "media_type": response.media_type,
                        }
                    ),
                    ex=TTL_SECONDS,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("idempotency.cache_write_failed", error=str(exc))
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        return response
