"""DHIS2 client — pushes immunisation tallies to the Ministry's central instance.

DHIS2 is the Ministry of Health's existing standard for aggregate reporting.
We don't replace it; we feed it. This client is resilient: if DHIS2 is down,
we accumulate events in Redis and replay them when service returns.
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
class DataValue:
    data_element: str
    period: str           # ISO 8601 (e.g. "2026Q1")
    org_unit: str         # DHIS2 facility code
    value: int


class Dhis2Client:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.dhis2_base_url,
            timeout=httpx.Timeout(connect=2.0, read=5.0, write=2.0, pool=2.0),
            auth=(settings.dhis2_username, settings.dhis2_password.get_secret_value()),
            transport=httpx.AsyncHTTPTransport(retries=0),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def post_tallies(self, values: list[DataValue]) -> dict[str, int]:
        try:
            return await self._post_live(values)
        except Exception as exc:
            logger.warning("dhis2.unavailable_queued", error=str(exc), pending=len(values))
            await self._queue(values)
            return {"queued": len(values), "delivered": 0}

    @resilient(breaker="dhis2", bulkhead_concurrency=4)
    async def _post_live(self, values: list[DataValue]) -> dict[str, int]:
        payload = {"dataValues": [asdict(v) for v in values]}
        response = await self._client.post("/dataValueSets", json=payload)
        response.raise_for_status()
        return {"queued": 0, "delivered": len(values)}

    async def _queue(self, values: list[DataValue]) -> None:
        redis = await get_redis()
        await redis.rpush(
            "dhis2:pending", *[orjson.dumps(asdict(v)).decode("utf-8") for v in values]
        )

    async def drain_queue(self) -> dict[str, int]:
        """Background worker entry-point to flush queued tallies."""
        redis = await get_redis()
        delivered = 0
        while True:
            raw = await redis.lpop("dhis2:pending")
            if not raw:
                break
            value = DataValue(**orjson.loads(raw))
            try:
                await self._post_live([value])
                delivered += 1
            except Exception as exc:
                logger.warning("dhis2.replay_failed", error=str(exc))
                await redis.lpush("dhis2:pending", raw)  # put back
                break
        return {"delivered": delivered}


_dhis2_singleton: Dhis2Client | None = None


def get_dhis2_client(settings: Settings = Depends(get_settings)) -> Dhis2Client:
    global _dhis2_singleton
    if _dhis2_singleton is None:
        _dhis2_singleton = Dhis2Client(settings)
    return _dhis2_singleton
