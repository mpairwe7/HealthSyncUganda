"""Resilience primitives — circuit breakers, retries, bulkheads, fallbacks.

These are the load-bearing patterns for an interoperability gateway:

* **Retry**: exponential backoff with jitter, capped attempts, per-exception
  filtering. Idempotent reads only by default.
* **Circuit breaker**: half-open probing after a recovery interval. Failing
  upstream services trip the breaker; subsequent calls fail fast with
  `UpstreamUnavailableError` until the breaker resets.
* **Bulkhead**: bounded concurrency per upstream so a slow dependency cannot
  exhaust the FastAPI worker.
* **Fallback**: combine with `@resilient` to return a degraded-but-safe
  response when an upstream is down.

All decorators are async-native and OpenTelemetry-aware (they emit span events
on retry/trip so dashboards can surface the truth of what happened).
"""

from __future__ import annotations

import asyncio
import functools
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, ParamSpec, TypeVar

from opentelemetry import trace

from app.config import get_settings
from app.core.logging import get_logger

P = ParamSpec("P")
T = TypeVar("T")

logger = get_logger(__name__)
tracer = trace.get_tracer(__name__)


# ── Exceptions ───────────────────────────────────────────────────────────────


class UpstreamUnavailableError(Exception):
    """Raised when a circuit breaker is open or the upstream is unreachable."""


class BulkheadFullError(Exception):
    """Raised when the concurrency bulkhead has no slots free."""


# ── Circuit breaker ──────────────────────────────────────────────────────────


class BreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """Async-safe circuit breaker keyed by `name`.

    Default thresholds come from settings but every breaker can override.
    Designed to be created once per upstream and reused.
    """

    name: str
    failure_threshold: int = field(
        default_factory=lambda: get_settings().circuit_breaker_failure_threshold
    )
    recovery_timeout: float = field(
        default_factory=lambda: float(
            get_settings().circuit_breaker_recovery_timeout_seconds
        )
    )
    expected_exceptions: tuple[type[BaseException], ...] = (Exception,)

    _state: BreakerState = field(default=BreakerState.CLOSED, init=False)
    _failures: int = field(default=0, init=False)
    _opened_at: float | None = field(default=None, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    @property
    def state(self) -> BreakerState:
        return self._state

    async def call(self, fn: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any) -> T:
        await self._before()
        try:
            result = await fn(*args, **kwargs)
        except self.expected_exceptions as exc:
            await self._on_failure(exc)
            raise
        else:
            await self._on_success()
            return result

    async def _before(self) -> None:
        async with self._lock:
            if self._state is BreakerState.OPEN:
                assert self._opened_at is not None
                if time.monotonic() - self._opened_at >= self.recovery_timeout:
                    self._state = BreakerState.HALF_OPEN
                    logger.info("circuit.half_open", breaker=self.name)
                else:
                    raise UpstreamUnavailableError(
                        f"Circuit breaker '{self.name}' is OPEN"
                    )

    async def _on_success(self) -> None:
        async with self._lock:
            if self._state is not BreakerState.CLOSED:
                logger.info("circuit.closed", breaker=self.name)
            self._state = BreakerState.CLOSED
            self._failures = 0
            self._opened_at = None

    async def _on_failure(self, exc: BaseException) -> None:
        async with self._lock:
            self._failures += 1
            span = trace.get_current_span()
            span.add_event(
                "circuit.failure",
                {"breaker": self.name, "failures": self._failures, "error": type(exc).__name__},
            )
            if (
                self._state is BreakerState.HALF_OPEN
                or self._failures >= self.failure_threshold
            ):
                self._state = BreakerState.OPEN
                self._opened_at = time.monotonic()
                logger.warning(
                    "circuit.opened",
                    breaker=self.name,
                    failures=self._failures,
                    recovery_timeout=self.recovery_timeout,
                )


# Global registry — one breaker per upstream identifier.
_breakers: dict[str, CircuitBreaker] = {}


def get_breaker(name: str, **kwargs: Any) -> CircuitBreaker:
    if name not in _breakers:
        _breakers[name] = CircuitBreaker(name=name, **kwargs)
    return _breakers[name]


# ── Retry with exponential backoff + jitter ──────────────────────────────────


def retry(
    *,
    attempts: int | None = None,
    base_delay_ms: int | None = None,
    max_delay_ms: int = 5_000,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    do_not_retry_on: tuple[type[BaseException], ...] = (UpstreamUnavailableError,),
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Decorator: retry an awaitable with exponential backoff + full jitter.

    Defaults pull from settings so deployments can dial sensitivity centrally.
    """
    settings = get_settings()
    a = attempts or settings.retry_max_attempts
    base = base_delay_ms or settings.retry_base_delay_ms

    def decorator(fn: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @functools.wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last: BaseException | None = None
            for attempt in range(1, a + 1):
                try:
                    return await fn(*args, **kwargs)
                except do_not_retry_on:
                    raise
                except retry_on as exc:
                    last = exc
                    if attempt == a:
                        break
                    delay_ms = min(max_delay_ms, base * (2 ** (attempt - 1)))
                    sleep_for = random.uniform(0, delay_ms) / 1_000.0
                    logger.info(
                        "retry",
                        fn=fn.__qualname__,
                        attempt=attempt,
                        sleep_ms=int(sleep_for * 1_000),
                        error=type(exc).__name__,
                    )
                    await asyncio.sleep(sleep_for)
            assert last is not None
            raise last

        return wrapper

    return decorator


# ── Bulkhead ─────────────────────────────────────────────────────────────────


class Bulkhead:
    """Bounded concurrency per upstream — protect FastAPI workers from slow deps."""

    def __init__(self, name: str, max_concurrent: int) -> None:
        self.name = name
        self._sem = asyncio.Semaphore(max_concurrent)
        self._max = max_concurrent

    async def __aenter__(self) -> Bulkhead:
        if not self._sem.locked() or self._sem._value > 0:  # type: ignore[attr-defined]
            await self._sem.acquire()
            return self
        raise BulkheadFullError(f"Bulkhead '{self.name}' is full ({self._max})")

    async def __aexit__(self, *_: Any) -> None:
        self._sem.release()


_bulkheads: dict[str, Bulkhead] = {}


def get_bulkhead(name: str, max_concurrent: int = 16) -> Bulkhead:
    if name not in _bulkheads:
        _bulkheads[name] = Bulkhead(name=name, max_concurrent=max_concurrent)
    return _bulkheads[name]


# ── Combined `@resilient` decorator ──────────────────────────────────────────


def resilient[T](
    *,
    breaker: str,
    bulkhead_concurrency: int = 16,
    retry_attempts: int | None = None,
    fallback: Callable[..., Awaitable[T]] | None = None,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """One-shot decorator that stacks breaker + bulkhead + retry + optional fallback.

    Use this for *every* external HTTP call. The pattern is:

        @resilient(breaker="dhis2", fallback=cached_dhis2_response)
        async def fetch_dhis2(...): ...
    """

    def decorator(fn: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        cb = get_breaker(breaker)
        bh = get_bulkhead(breaker, max_concurrent=bulkhead_concurrency)
        retried = retry(attempts=retry_attempts)(fn)

        @functools.wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            with tracer.start_as_current_span(
                f"resilient.{breaker}",
                attributes={"breaker.name": breaker},
            ):
                try:
                    async with bh:
                        return await cb.call(retried, *args, **kwargs)
                except (UpstreamUnavailableError, BulkheadFullError) as exc:
                    if fallback is None:
                        raise
                    logger.warning(
                        "resilient.fallback",
                        breaker=breaker,
                        reason=type(exc).__name__,
                    )
                    return await fallback(*args, **kwargs)

        return wrapper

    return decorator
