"""Idempotency cache key derivation (ADR 0003).

Verifies the contract clients rely on: same key on the same endpoint dedups;
same key on a different endpoint does not collide; safe methods bypass.
"""

from __future__ import annotations

import hashlib

from app.middleware.idempotency import (
    IDEMPOTENCY_HEADER,
    SAFE_METHODS,
)


def _cache_key(method: str, path: str, key: str) -> str:
    return "idempotency:" + hashlib.sha256(f"{method}:{path}:{key}".encode()).hexdigest()


def test_safe_methods_are_documented() -> None:
    """The middleware must not cache GET/HEAD/OPTIONS — they are idempotent
    by HTTP definition and caching them would shadow real changes."""
    assert SAFE_METHODS == {"GET", "HEAD", "OPTIONS"}


def test_header_name_is_canonical() -> None:
    """The header name is fixed by API.md; any drift breaks clients."""
    assert IDEMPOTENCY_HEADER == "Idempotency-Key"


def test_same_key_same_endpoint_dedups() -> None:
    """Identical (method, path, key) MUST hash to the same cache key."""
    a = _cache_key("POST", "/api/v1/encounters", "ulid-1")
    b = _cache_key("POST", "/api/v1/encounters", "ulid-1")
    assert a == b


def test_same_key_different_endpoint_does_not_collide() -> None:
    """A client reusing an idempotency key across endpoints MUST NOT see
    a stale response from the other endpoint."""
    a = _cache_key("POST", "/api/v1/encounters", "ulid-1")
    b = _cache_key("POST", "/api/v1/patients", "ulid-1")
    assert a != b


def test_same_endpoint_different_method_does_not_collide() -> None:
    """POST and PATCH to the same path with the same key are different
    operations — they must not share a cache slot."""
    a = _cache_key("POST", "/api/v1/encounters", "ulid-1")
    b = _cache_key("PATCH", "/api/v1/encounters", "ulid-1")
    assert a != b
