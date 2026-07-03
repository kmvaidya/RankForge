# tests/test_features.py

"""Tests for deployment feature flags and the /config endpoint."""

import pytest
from httpx import AsyncClient

from rankforge.features import enabled_features


class TestEnabledFeatures:
    def test_default_is_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("RANKFORGE_FEATURES", raising=False)
        assert enabled_features() == []

    def test_known_flag_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RANKFORGE_FEATURES", "match_weights")
        assert enabled_features() == ["match_weights"]

    def test_whitespace_and_case_are_tolerated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("RANKFORGE_FEATURES", "  Match_Weights , ")
        assert enabled_features() == ["match_weights"]

    def test_unknown_flags_are_dropped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RANKFORGE_FEATURES", "match_weights,definitely_bogus")
        assert enabled_features() == ["match_weights"]

    def test_empty_tokens_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RANKFORGE_FEATURES", ",,  ,")
        assert enabled_features() == []


class TestConfigEndpoint:
    @pytest.mark.asyncio
    async def test_config_reports_enabled_features(
        self, async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("RANKFORGE_FEATURES", "match_weights")
        response = await async_client.get("/config")
        assert response.status_code == 200
        assert response.json() == {"features": ["match_weights"]}

    @pytest.mark.asyncio
    async def test_config_defaults_to_no_features(
        self, async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("RANKFORGE_FEATURES", raising=False)
        response = await async_client.get("/config")
        assert response.status_code == 200
        assert response.json() == {"features": []}
