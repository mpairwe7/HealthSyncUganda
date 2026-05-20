"""Smoke tests — the service boots and exposes its health/FHIR metadata."""

import pytest


@pytest.mark.asyncio
async def test_healthz(client):
    r = await client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_root(client):
    r = await client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "healthsync-uganda"


@pytest.mark.asyncio
async def test_fhir_capability(client):
    r = await client.get("/fhir/metadata")
    assert r.status_code == 200
    body = r.json()
    assert body["resourceType"] == "CapabilityStatement"
    assert body["fhirVersion"] == "4.0.1"


@pytest.mark.asyncio
async def test_openapi(client):
    r = await client.get("/openapi.json")
    assert r.status_code == 200
    assert "openapi" in r.json()
