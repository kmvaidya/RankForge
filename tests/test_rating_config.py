# tests/test_rating_config.py

"""Tests for per-game rating_config: validation, min_swing, and game health."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _create_game(
    async_client: AsyncClient, name: str, rating_config: dict | None = None
) -> dict:
    body: dict = {"name": name, "rating_strategy": "glicko2"}
    if rating_config is not None:
        body["rating_config"] = rating_config
    response = await async_client.post("/games/", json=body)
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _create_player(async_client: AsyncClient, name: str) -> dict:
    response = await async_client.post("/players/", json={"name": name})
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _play_match(
    async_client: AsyncClient,
    game_id: int,
    winner_id: int,
    loser_id: int,
    metadata: dict | None = None,
    draw: bool = False,
) -> dict:
    outcome_1 = {"result": "draw" if draw else "win"}
    outcome_2 = {"result": "draw" if draw else "loss"}
    response = await async_client.post(
        "/matches/",
        json={
            "game_id": game_id,
            "match_metadata": metadata or {},
            "participants": [
                {"player_id": winner_id, "team_id": 1, "outcome": outcome_1},
                {"player_id": loser_id, "team_id": 2, "outcome": outcome_2},
            ],
        },
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _rating_of(async_client: AsyncClient, game_id: int, player_id: int) -> float:
    response = await async_client.get(f"/games/{game_id}/leaderboard?limit=100")
    assert response.status_code == 200
    for entry in response.json()["items"]:
        if entry["player"]["id"] == player_id:
            return float(entry["rating_info"]["rating"])
    raise AssertionError(f"player {player_id} not on leaderboard")


class TestRatingConfigValidation:
    async def test_create_with_config_roundtrips(self, async_client: AsyncClient):
        game = await _create_game(
            async_client, "CfgGame", {"min_swing": 25, "score_preset": 11}
        )
        assert game["rating_config"] == {"min_swing": 25, "score_preset": 11}

    async def test_default_config_is_empty(self, async_client: AsyncClient):
        game = await _create_game(async_client, "PlainGame")
        assert game["rating_config"] == {}

    @pytest.mark.parametrize(
        "config",
        [
            {"min_swing": -1},
            {"min_swing": "big"},
            {"min_swing": True},
            {"margin_weight_factor": -0.5},
            {"score_preset": 0},
            {"score_preset": 2.5},
            {"leaderboard_mode": "bogus"},
        ],
    )
    async def test_invalid_config_rejected(
        self, async_client: AsyncClient, config: dict
    ):
        response = await async_client.post(
            "/games/",
            json={
                "name": "BadCfg",
                "rating_strategy": "glicko2",
                "rating_config": config,
            },
        )
        assert response.status_code == 422

    async def test_update_config(self, async_client: AsyncClient):
        game = await _create_game(async_client, "UpdCfg")
        response = await async_client.put(
            f"/games/{game['id']}", json={"rating_config": {"min_swing": 10}}
        )
        assert response.status_code == 200
        assert response.json()["rating_config"] == {"min_swing": 10}

    async def test_unknown_keys_pass_through(self, async_client: AsyncClient):
        game = await _create_game(async_client, "ExtraCfg", {"house_rule": "yes"})
        assert game["rating_config"] == {"house_rule": "yes"}


class TestMinSwing:
    async def test_win_floor_applies(self, async_client: AsyncClient):
        """A near-zero-weight match moves ratings ~0; min_swing forces Â±50."""
        game = await _create_game(async_client, "SwingGame", {"min_swing": 50})
        p1 = await _create_player(async_client, "SwingWinner")
        p2 = await _create_player(async_client, "SwingLoser")
        await _play_match(
            async_client, game["id"], p1["id"], p2["id"], {"weight": 1e-6}
        )
        assert await _rating_of(async_client, game["id"], p1["id"]) == 1550.0
        assert await _rating_of(async_client, game["id"], p2["id"]) == 1450.0

    async def test_no_config_means_pure_glicko(self, async_client: AsyncClient):
        game = await _create_game(async_client, "PureGame")
        p1 = await _create_player(async_client, "PureWinner")
        p2 = await _create_player(async_client, "PureLoser")
        await _play_match(
            async_client, game["id"], p1["id"], p2["id"], {"weight": 1e-6}
        )
        assert abs(await _rating_of(async_client, game["id"], p1["id"]) - 1500) < 1

    async def test_draws_not_forced(self, async_client: AsyncClient):
        game = await _create_game(async_client, "DrawGame", {"min_swing": 50})
        p1 = await _create_player(async_client, "DrawA")
        p2 = await _create_player(async_client, "DrawB")
        await _play_match(
            async_client, game["id"], p1["id"], p2["id"], {"weight": 1e-6}, draw=True
        )
        assert abs(await _rating_of(async_client, game["id"], p1["id"]) - 1500) < 1

    async def test_large_natural_swing_untouched(self, async_client: AsyncClient):
        """When Glicko already moves more than the floor, the floor is a no-op."""
        game = await _create_game(async_client, "BigSwing", {"min_swing": 5})
        p1 = await _create_player(async_client, "BigWinner")
        p2 = await _create_player(async_client, "BigLoser")
        await _play_match(async_client, game["id"], p1["id"], p2["id"])
        gain = await _rating_of(async_client, game["id"], p1["id"]) - 1500
        assert gain > 5  # fresh 1500/350 players swing far beyond the floor


class TestGameHealth:
    async def test_fresh_game(self, async_client: AsyncClient):
        game = await _create_game(async_client, "HealthFresh")
        response = await async_client.get(f"/games/{game['id']}/health")
        assert response.status_code == 200
        body = response.json()
        assert body == {
            "game_id": game["id"],
            "players": 0,
            "matches": 0,
            "mean_rating": 1500.0,
            "rating_drift": 0.0,
        }

    async def test_after_matches(self, async_client: AsyncClient):
        game = await _create_game(async_client, "HealthPlayed")
        p1 = await _create_player(async_client, "HealthA")
        p2 = await _create_player(async_client, "HealthB")
        await _play_match(async_client, game["id"], p1["id"], p2["id"])
        body = (await async_client.get(f"/games/{game['id']}/health")).json()
        assert body["players"] == 2
        assert body["matches"] == 1
        r1 = await _rating_of(async_client, game["id"], p1["id"])
        r2 = await _rating_of(async_client, game["id"], p2["id"])
        assert body["mean_rating"] == pytest.approx((r1 + r2) / 2, abs=0.01)
        assert body["rating_drift"] == pytest.approx(
            abs(1500 - (r1 + r2) / 2), abs=0.01
        )

    async def test_missing_game_404(self, async_client: AsyncClient):
        response = await async_client.get("/games/999999/health")
        assert response.status_code == 404
