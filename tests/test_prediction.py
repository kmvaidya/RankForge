# tests/test_prediction.py

"""Tests for the prediction endpoint and walk-forward calibration report."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _post(async_client: AsyncClient, path: str, body: dict) -> dict:
    response = await async_client.post(path, json=body)
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _setup(
    async_client: AsyncClient, names: list[str]
) -> tuple[int, dict[str, int]]:
    game = await _post(
        async_client, "/games/", {"name": "PredictGame", "rating_strategy": "glicko2"}
    )
    ids = {}
    for name in names:
        player = await _post(async_client, "/players/", {"name": name})
        ids[name] = player["id"]
    return game["id"], ids


async def _play_1v1(
    async_client: AsyncClient, game_id: int, winner: int, loser: int
) -> None:
    await _post(
        async_client,
        "/matches/",
        {
            "game_id": game_id,
            "participants": [
                {"player_id": winner, "team_id": 1, "outcome": {"result": "win"}},
                {"player_id": loser, "team_id": 2, "outcome": {"result": "loss"}},
            ],
        },
    )


class TestPredictEndpoint:
    async def test_fresh_players_are_even_odds(self, async_client: AsyncClient):
        game_id, ids = await _setup(async_client, ["Ana", "Ben"])
        response = await async_client.post(
            f"/games/{game_id}/predict",
            json={"teams": [[ids["Ana"]], [ids["Ben"]]]},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        probs = [team["win_probability"] for team in body["teams"]]
        assert probs == [0.5, 0.5]
        assert body["lopsided"] is False
        assert body["method"] == "glicko2_expected_score"

    async def test_winner_is_favored_and_probs_sum_to_one(
        self, async_client: AsyncClient
    ):
        game_id, ids = await _setup(async_client, ["Ana", "Ben"])
        for _ in range(5):
            await _play_1v1(async_client, game_id, ids["Ana"], ids["Ben"])

        response = await async_client.post(
            f"/games/{game_id}/predict",
            json={"teams": [[ids["Ana"]], [ids["Ben"]]]},
        )
        assert response.status_code == 200
        body = response.json()
        ana, ben = body["teams"]
        assert ana["win_probability"] > 0.6
        assert abs(ana["win_probability"] + ben["win_probability"] - 1.0) < 0.001
        assert body["favored_team_index"] == 0
        assert ana["rating"] > ben["rating"]

    async def test_unknown_player_is_fresh_default(self, async_client: AsyncClient):
        """A player with no profile in this game predicts at the default rating."""
        game_id, ids = await _setup(async_client, ["Ana", "Ben", "New"])
        for _ in range(3):
            await _play_1v1(async_client, game_id, ids["Ana"], ids["Ben"])
        response = await async_client.post(
            f"/games/{game_id}/predict",
            json={"teams": [[ids["Ana"]], [ids["New"]]]},
        )
        assert response.status_code == 200
        assert response.json()["teams"][0]["win_probability"] > 0.5

    async def test_validation_rejects_bad_splits(self, async_client: AsyncClient):
        game_id, ids = await _setup(async_client, ["Ana", "Ben"])
        single = await async_client.post(
            f"/games/{game_id}/predict", json={"teams": [[ids["Ana"]]]}
        )
        assert single.status_code == 422
        empty = await async_client.post(
            f"/games/{game_id}/predict", json={"teams": [[ids["Ana"]], []]}
        )
        assert empty.status_code == 422
        duplicate = await async_client.post(
            f"/games/{game_id}/predict",
            json={"teams": [[ids["Ana"]], [ids["Ana"]]]},
        )
        assert duplicate.status_code == 422

    async def test_missing_game_and_player_404(self, async_client: AsyncClient):
        game_id, ids = await _setup(async_client, ["Ana", "Ben"])
        missing_game = await async_client.post(
            "/games/999999/predict",
            json={"teams": [[ids["Ana"]], [ids["Ben"]]]},
        )
        assert missing_game.status_code == 404
        missing_player = await async_client.post(
            f"/games/{game_id}/predict",
            json={"teams": [[ids["Ana"]], [999999]]},
        )
        assert missing_player.status_code == 404


class TestCalibrationReport:
    async def test_report_shape_and_determinism(self, async_client: AsyncClient):
        game_id, ids = await _setup(async_client, ["Ana", "Ben"])
        for _ in range(6):
            await _play_1v1(async_client, game_id, ids["Ana"], ids["Ben"])

        response = await async_client.get(
            f"/games/{game_id}/calibration", params={"warmup": 0}
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["matches_replayed"] == 6
        assert body["comparisons_evaluated"] == 6
        assert 0.0 <= body["brier"] <= 1.0
        assert 0.0 <= body["accuracy"] <= 1.0
        assert body["ece"] >= 0.0
        assert len(body["bins"]) == 10
        assert sum(b["count"] for b in body["bins"]) == 6
        # 6 appearances each is below the Spearman establishment threshold.
        assert body["spearman_players"] == 0
        assert body["rating_winrate_spearman"] is None

        again = await async_client.get(
            f"/games/{game_id}/calibration", params={"warmup": 0}
        )
        assert again.json() == body

    async def test_warmup_skips_young_players(self, async_client: AsyncClient):
        game_id, ids = await _setup(async_client, ["Ana", "Ben"])
        for _ in range(6):
            await _play_1v1(async_client, game_id, ids["Ana"], ids["Ben"])

        response = await async_client.get(
            f"/games/{game_id}/calibration", params={"warmup": 5}
        )
        body = response.json()
        # Only the sixth match has both players past 5 prior appearances.
        assert body["comparisons_evaluated"] == 1
        # By then Ana has won five straight; the engine must favor her.
        evaluated_bins = [b for b in body["bins"] if b["count"]]
        assert evaluated_bins[0]["mean_predicted"] > 0.5

    async def test_predictions_beat_coin_flips_on_consistent_history(
        self, async_client: AsyncClient
    ):
        """A one-sided rivalry must score better than Brier 0.25."""
        game_id, ids = await _setup(async_client, ["Ana", "Ben"])
        for _ in range(10):
            await _play_1v1(async_client, game_id, ids["Ana"], ids["Ben"])
        response = await async_client.get(
            f"/games/{game_id}/calibration", params={"warmup": 2}
        )
        assert response.json()["brier"] < 0.25

    async def test_empty_game_reports_nothing(self, async_client: AsyncClient):
        game_id, _ = await _setup(async_client, ["Ana"])
        response = await async_client.get(f"/games/{game_id}/calibration")
        body = response.json()
        assert body["matches_replayed"] == 0
        assert body["comparisons_evaluated"] == 0
        assert body["brier"] is None
        assert body["bins"] == []

    async def test_missing_game_404(self, async_client: AsyncClient):
        response = await async_client.get("/games/999999/calibration")
        assert response.status_code == 404
