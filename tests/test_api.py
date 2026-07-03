# tests/test_api.py

"""Tests for the main API endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_read_root(async_client: AsyncClient):
    """Test if the root endpoint returns the correct message."""
    response = await async_client.get("/")

    # Assert that the request was successful
    assert response.status_code == 200

    # Assert that the response body is what we now expect
    expected_json = {
        "message": "Welcome to the RankForge API",
    }
    assert response.json() == expected_json
