"""NIRA (National Identification & Registration Authority) client.

In production this calls the NIRA identity verification API. For the demo we
ship a local mock at `/mock/nira/...` and a graceful-degradation pathway: if
NIRA is unreachable, we serve the last-known-good response from Redis cache.

Contract surface kept small on purpose: `verify_nin(nin) -> NinVerification`.
Wider use cases (search, biometrics) are intentionally out of scope here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import httpx
import orjson
from fastapi import Depends

from app.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.redis_client import get_redis
from app.core.resilience import resilient

logger = get_logger(__name__)


@dataclass(slots=True)
class NinVerification:
    nin: str
    found: bool
    full_name: str | None = None
    gender: str | None = None
    date_of_birth: str | None = None
    district: str | None = None
    via_fallback: bool = False     # served from cache?


_CACHE_TTL = 24 * 60 * 60         # 24h fallback cache


class NiraClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.nira_base_url,
            timeout=httpx.Timeout(connect=2.0, read=4.0, write=2.0, pool=2.0),
            headers={"X-Api-Key": settings.nira_api_key.get_secret_value()},
            transport=httpx.AsyncHTTPTransport(retries=0),  # we own retry policy
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def verify_nin(self, nin: str) -> NinVerification:
        cache_key = f"nira:nin:{nin}"
        result = await self._verify_with_fallback(nin)
        # Cache only positive responses
        if result.found and not result.via_fallback:
            try:
                redis = await get_redis()
                await redis.set(cache_key, orjson.dumps(asdict(result)), ex=_CACHE_TTL)
            except Exception as exc:
                logger.warning("nira.cache_write_failed", error=str(exc))
        return result

    async def _cache_lookup(self, nin: str) -> NinVerification | None:
        try:
            redis = await get_redis()
            raw = await redis.get(f"nira:nin:{nin}")
        except Exception as exc:
            logger.warning("nira.cache_unavailable", error=str(exc))
            return None
        if not raw:
            return None
        data = orjson.loads(raw)
        data["via_fallback"] = True
        return NinVerification(**data)

    @resilient(breaker="nira", bulkhead_concurrency=8)
    async def _verify_live(self, nin: str) -> NinVerification:
        response = await self._client.get(f"/verify/{nin}")
        if response.status_code == 404:
            return NinVerification(nin=nin, found=False)
        response.raise_for_status()
        body = response.json()
        return NinVerification(
            nin=nin,
            found=True,
            full_name=body.get("full_name"),
            gender=body.get("gender"),
            date_of_birth=body.get("date_of_birth"),
            district=body.get("district"),
        )

    async def _verify_with_fallback(self, nin: str) -> NinVerification:
        try:
            return await self._verify_live(nin)
        except Exception as exc:
            logger.warning("nira.live_unavailable_using_cache", error=str(exc))
            cached = await self._cache_lookup(nin)
            if cached:
                return cached
            # Hard fail — no cache, no upstream
            raise


# ── FastAPI dependency ───────────────────────────────────────────────────────


_nira_singleton: NiraClient | None = None


def get_nira_client(settings: Settings = Depends(get_settings)) -> NiraClient:
    global _nira_singleton
    if _nira_singleton is None:
        _nira_singleton = NiraClient(settings)
    return _nira_singleton
