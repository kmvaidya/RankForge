# tests/test_chemistry.py

"""Tests for the partner/rival chemistry endpoint."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _post(async_client: AsyncClient, path: str, body: dict) -> dict:
    response = await async_client.post(path, json=body)
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _setup_game_and_players(
    async_client: AsyncClient, names: list[str]
) -> tuple[int, dict[str, int]]:
    game = await _post(
        async_client, "/games/", {"name": "ChemGame", "rating_strategy": "glicko2"}
    )
    ids = {}
    for name in names:
        player = await _post(async_client, "/players/", {"name": name})
        ids[name] = player["id"]
    return game["id"], ids


async def _play_2v2(
    async_client: AsyncClient,
    game_id: int,
    team1: list[int],
    team2: list[int],
    winner: int,
) -> None:
    def outcome(team: int) -> dict:
        return {"result": "win" if winner == team else "loss"}

    participants = [
        {"player_id": pid, "team_id": 1, "outcome": outcome(1)} for pid in team1
    ] + [{"player_id": pid, "team_id": 2, "outcome": outcome(2)} for pid in team2]
    await _post(
        async_client,
        "/matches/",
        {"game_id": game_id, "participants": participants},
    )


class TestChemistry:
    async def test_partners_and_rivals_aggregate(self, async_client: AsyncClient):
        game_id, ids = await _setup_game_and_players(
            async_client, ["Ana", "Ben", "Cid", "Dee"]
        )
        # Ana+Ben beat Cid+Dee twice, then Ana+Cid lose to Ben+Dee once.
        await _play_2v2(
            async_client, game_id, [ids["Ana"], ids["Ben"]], [ids["Cid"], ids["Dee"]], 1
        )
        await _play_2v2(
            async_client, game_id, [ids["Ana"], ids["Ben"]], [ids["Cid"], ids["Dee"]], 1
        )
        await _play_2v2(
            async_client, game_id, [ids["Ana"], ids["Cid"]], [ids["Ben"], ids["Dee"]], 2
        )

        response = await async_client.get(
            f"/players/{ids['Ana']}/chemistry", params={"game_id": game_id}
        )
        assert response.status_code == 200
        body = response.json()

        partners = {e["player_name"]: e for e in body["partners"]}
        rivals = {e["player_name"]: e for e in body["rivals"]}

        # Ben partnered Ana twice (both wins); Cid partnered once (a loss).
        assert partners["Ben"]["matches"] == 2
        assert partners["Ben"]["wins"] == 2
        assert partners["Ben"]["win_rate"] == 1.0
        assert partners["Cid"]["matches"] == 1
        assert partners["Cid"]["losses"] == 1

        # Dee opposed Ana in all three (Ana 2-1); Cid opposed twice (2-0);
        # Ben opposed once (0-1).
        assert rivals["Dee"]["matches"] == 3
        assert rivals["Dee"]["wins"] == 2
        assert rivals["Dee"]["losses"] == 1
        assert rivals["Cid"]["matches"] == 2
        assert rivals["Cid"]["wins"] == 2
        assert rivals["Ben"]["matches"] == 1
        assert rivals["Ben"]["losses"] == 1

        # Sorted by shared matches descending.
        assert body["rivals"][0]["player_name"] == "Dee"
        assert body["partners"][0]["player_name"] == "Ben"

    async def test_no_matches_is_empty(self, async_client: AsyncClient):
        game_id, ids = await _setup_game_and_players(async_client, ["Solo"])
        response = await async_client.get(
            f"/players/{ids['Solo']}/chemistry", params={"game_id": game_id}
        )
        assert response.status_code == 200
        assert response.json() == {
            "player_id": ids["Solo"],
            "game_id": game_id,
            "partners": [],
            "rivals": [],
        }

    async def test_missing_player_or_game_404(self, async_client: AsyncClient):
        game_id, ids = await _setup_game_and_players(async_client, ["Lone"])
        r1 = await async_client.get(
            "/players/999999/chemistry", params={"game_id": game_id}
        )
        assert r1.status_code == 404
        r2 = await async_client.get(
            f"/players/{ids['Lone']}/chemistry", params={"game_id": 999999}
        )
        assert r2.status_code == 404
