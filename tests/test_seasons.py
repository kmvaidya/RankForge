# tests/test_seasons.py

"""Tests for season boundaries: RD reset, stat split, replay determinism."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _post(async_client: AsyncClient, path: str, body: dict | None = None) -> dict:
    response = await async_client.post(path, json=body if body is not None else {})
    assert response.status_code in (200, 201), response.text
    return dict(response.json())


async def _setup(
    async_client: AsyncClient, prefix: str, config: dict | None = None
) -> tuple[int, int, int]:
    body: dict = {"name": f"{prefix}Game", "rating_strategy": "glicko2"}
    if config is not None:
        body["rating_config"] = config
    game = await _post(async_client, "/games/", body)
    p1 = await _post(async_client, "/players/", {"name": f"{prefix}A"})
    p2 = await _post(async_client, "/players/", {"name": f"{prefix}B"})
    return game["id"], p1["id"], p2["id"]


async def _play(
    async_client: AsyncClient, game_id: int, winner_id: int, loser_id: int
) -> None:
    await _post(
        async_client,
        "/matches/",
        {
            "game_id": game_id,
            "participants": [
                {"player_id": winner_id, "team_id": 1, "outcome": {"result": "win"}},
                {"player_id": loser_id, "team_id": 2, "outcome": {"result": "loss"}},
            ],
        },
    )


async def _board(async_client: AsyncClient, game_id: int) -> dict[int, dict]:
    response = await async_client.get(f"/games/{game_id}/leaderboard?limit=100")
    assert response.status_code == 200
    return {e["player"]["id"]: e for e in response.json()["items"]}


class TestSeasonLifecycle:
    async def test_implicit_season_one(self, async_client: AsyncClient):
        game_id, _, _ = await _setup(async_client, "S1")
        body = (await async_client.get(f"/games/{game_id}/seasons")).json()
        assert body == {"current_season": 1, "items": []}

    async def test_start_season_increments(self, async_client: AsyncClient):
        game_id, _, _ = await _setup(async_client, "S2")
        season = await _post(async_client, f"/games/{game_id}/seasons")
        assert season["number"] == 2
        season = await _post(async_client, f"/games/{game_id}/seasons")
        assert season["number"] == 3
        body = (await async_client.get(f"/games/{game_id}/seasons")).json()
        assert body["current_season"] == 3
        assert [s["number"] for s in body["items"]] == [2, 3]

    async def test_missing_game_404(self, async_client: AsyncClient):
        assert (await async_client.get("/games/999999/seasons")).status_code == 404
        assert (await async_client.post("/games/999999/seasons")).status_code == 404


class TestSeasonEffects:
    async def test_rd_resets_rating_persists(self, async_client: AsyncClient):
        game_id, p1, p2 = await _setup(async_client, "SFX")
        for _ in range(3):
            await _play(async_client, game_id, p1, p2)
        before = await _board(async_client, game_id)
        assert before[p1]["rating_info"]["rd"] < 350

        await _post(async_client, f"/games/{game_id}/seasons")

        after = await _board(async_client, game_id)
        assert after[p1]["rating_info"]["rd"] == 350.0
        assert after[p2]["rating_info"]["rd"] == 350.0
        assert after[p1]["rating_info"]["rating"] == before[p1]["rating_info"]["rating"]

    async def test_custom_rd_reset(self, async_client: AsyncClient):
        game_id, p1, p2 = await _setup(async_client, "SRD", {"season_rd_reset": 250})
        await _play(async_client, game_id, p1, p2)
        await _post(async_client, f"/games/{game_id}/seasons")
        after = await _board(async_client, game_id)
        assert after[p1]["rating_info"]["rd"] == 250.0

    async def test_season_stats_zero_then_count(self, async_client: AsyncClient):
        game_id, p1, p2 = await _setup(async_client, "SST")
        await _play(async_client, game_id, p1, p2)
        await _play(async_client, game_id, p1, p2)

        await _post(async_client, f"/games/{game_id}/seasons")
        board = await _board(async_client, game_id)
        assert board[p1]["stats"]["matches_played"] == 2  # career kept
        assert board[p1]["stats"]["season"]["matches_played"] == 0

        await _play(async_client, game_id, p2, p1)
        board = await _board(async_client, game_id)
        assert board[p1]["stats"]["matches_played"] == 3
        assert board[p1]["stats"]["season"] == {
            "matches_played": 1,
            "wins": 0,
            "losses": 1,
            "draws": 0,
            "win_rate": 0.0,
        }
        assert board[p2]["stats"]["season"]["wins"] == 1


class TestSeasonReplayDeterminism:
    async def test_recalculate_reproduces_boundary_state(
        self, async_client: AsyncClient
    ):
        """A full recalculation must land on the same ratings, RDs, and
        season stats as the original live sequence with a mid-history
        boundary."""
        game_id, p1, p2 = await _setup(async_client, "SRP")
        await _play(async_client, game_id, p1, p2)
        await _play(async_client, game_id, p1, p2)
        await _post(async_client, f"/games/{game_id}/seasons")
        await _play(async_client, game_id, p2, p1)

        before = await _board(async_client, game_id)
        recalc = await _post(async_client, f"/games/{game_id}/recalculate")
        assert recalc["matches_recalculated"] == 3
        after = await _board(async_client, game_id)

        for pid in (p1, p2):
            assert after[pid]["rating_info"] == before[pid]["rating_info"], pid
            assert after[pid]["stats"] == before[pid]["stats"], pid

    async def test_boundary_after_all_matches_survives_recalc(
        self, async_client: AsyncClient
    ):
        game_id, p1, p2 = await _setup(async_client, "SRT")
        await _play(async_client, game_id, p1, p2)
        await _post(async_client, f"/games/{game_id}/seasons")

        before = await _board(async_client, game_id)
        assert before[p1]["rating_info"]["rd"] == 350.0
        await _post(async_client, f"/games/{game_id}/recalculate")
        after = await _board(async_client, game_id)
        assert after[p1]["rating_info"] == before[p1]["rating_info"]
        assert after[p1]["stats"]["season"]["matches_played"] == 0
