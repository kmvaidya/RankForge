# tests/test_security.py

"""Tests for CORS configuration and security headers."""

import pytest
from httpx import AsyncClient

from rankforge.main import cors_origins


@pytest.mark.asyncio
async def test_security_headers_present(async_client: AsyncClient):
    response = await async_client.get("/health")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"


@pytest.mark.asyncio
async def test_cors_allows_configured_origin(async_client: AsyncClient):
    response = await async_client.get(
        "/health", headers={"Origin": "http://localhost:5173"}
    )
    assert response.status_code == 200
    assert (
        response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    )


@pytest.mark.asyncio
async def test_cors_preflight(async_client: AsyncClient):
    response = await async_client.options(
        "/matches/",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200
    assert "access-control-allow-methods" in response.headers


@pytest.mark.asyncio
async def test_cors_rejects_unknown_origin(async_client: AsyncClient):
    response = await async_client.get(
        "/health", headers={"Origin": "https://evil.example.com"}
    )
    # Request succeeds but no CORS grant is issued for unknown origins
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_cors_origins_parsing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example.com , https://b.example.com,")
    assert cors_origins() == ["https://a.example.com", "https://b.example.com"]
