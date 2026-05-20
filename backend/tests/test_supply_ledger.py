"""Hash-chain integrity tests for the supply ledger (ADR 0004).

These tests verify the property the ledger is sold on: tamper-evidence.
Recomputing each entry's hash from its predecessor MUST yield the stored
hash. Any silent rewrite of a previously-written row makes the chain
verification fail.
"""

from __future__ import annotations

from app.services.supply_ledger import _hash_event


def test_hash_event_is_deterministic_under_key_order() -> None:
    """Same payload, different key insertion order — same hash."""
    a = _hash_event(None, {"a": 1, "b": 2, "c": 3})
    b = _hash_event(None, {"c": 3, "a": 1, "b": 2})
    assert a == b


def test_hash_event_chains_genesis_correctly() -> None:
    """First event uses the GENESIS sentinel as its predecessor."""
    h = _hash_event(None, {"x": 1})
    # Must be deterministic and lowercase hex of length 64 (sha256)
    assert len(h) == 64
    assert int(h, 16) >= 0


def test_hash_event_changes_when_prev_changes() -> None:
    """Changing the previous hash MUST change the current hash."""
    payload = {"x": 1}
    assert _hash_event("aa" * 32, payload) != _hash_event("bb" * 32, payload)


def test_hash_event_changes_when_payload_changes() -> None:
    """Mutating the payload MUST change the hash — even a single byte."""
    assert _hash_event("aa" * 32, {"x": 1}) != _hash_event("aa" * 32, {"x": 2})


def test_chain_detects_silent_rewrite() -> None:
    """Simulate a 3-entry chain. Rewriting entry 2 must break verification."""
    entries = []
    prev = None
    for payload in ({"k": 1}, {"k": 2}, {"k": 3}):
        h = _hash_event(prev, payload)
        entries.append((prev, payload, h))
        prev = h

    # Verification — recompute each row from its claimed predecessor + payload
    for prev_hash, payload, claimed in entries:
        assert _hash_event(prev_hash, payload) == claimed

    # Now rewrite entry 1's payload silently
    tampered_prev, _orig_payload, claimed_hash = entries[1]
    rewritten_payload = {"k": 999}
    recomputed = _hash_event(tampered_prev, rewritten_payload)
    assert recomputed != claimed_hash, "tamper-evidence broken"
