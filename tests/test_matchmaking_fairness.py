# tests/test_matchmaking_fairness.py

"""Tests for lopsided flagging and the repeat-partner variety penalty."""

import pytest
from httpx import AsyncClient

from rankforge.services.matchmaking_service import (
    PlayerSkill,
    _repeat_pairs,
    _variety_penalty,
    search_configurations,
)


class TestVarietyPenalty:
    def test_repeat_pairs_expand_groups(self):
        pairs = _repeat_pairs([[1, 2, 3], [4, 5]])
        assert pairs == {
            frozenset((1, 2)),
            frozenset((1, 3)),
            frozenset((2, 3)),
            frozenset((4, 5)),
        }

    def test_penalty_counts_reformed_partnerships(self):
        pairs = _repeat_pairs([[1, 2], [3, 4]])
        assert _variety_penalty(((1, 2), (3, 4)), pairs) == pytest.approx(0.2)
        assert _variety_penalty(((1, 3), (2, 4)), pairs) == 0.0

    def test_search_ranks_fresh_partnerships_first(self):
        # Four equal players: every 2v2 split is perfectly fair, so the
        # variety penalty must decide the order.
        skills = {
            pid: PlayerSkill(player_id=pid, mu=1500.0, sigma=100.0)
            for pid in (1, 2, 3, 4)
        }
        ranked, _, _ = search_configurations(
            skills,
            [1, 2, 3, 4],
            [2, 2],
            num_results=3,
            together=[],
            apart=[],
            repeat_pairs=_repeat_pairs([[1, 2]]),
        )
        top_fairness, top_config = ranked[0]
        top_teams = [set(team) for team in top_config]
        assert {1, 2} not in top_teams
        # Fairness reported is the pure balance number, unpenalized.
        assert top_fairness == pytest.approx(1.0)
        # The penalized 1&2 pairing still appears, just ranked last.
        last_teams = [set(team) for team in ranked[-1][1]]
        assert {1, 2} in last_teams


async def _post(async_client: AsyncClient, path: str, body: dict) -> dict:
    response = await async_client.post(path, json=body)
    assert response.status_code == 201, response.text
    return dict(response.json())


@pytest.mark.asyncio
class TestLopsidedFlag:
    async def _setup(self, async_client: AsyncClient) -> tuple[int, int, int]:
        game = await _post(
            async_client, "/games/", {"name": "FairGame", "rating_strategy": "glicko2"}
        )
        a = await _post(async_client, "/players/", {"name": "Shark"})
        b = await _post(async_client, "/players/", {"name": "Minnow"})
        return game["id"], a["id"], b["id"]

    async def test_fresh_players_are_not_lopsided(self, async_client: AsyncClient):
        game_id, a, b = await self._setup(async_client)
        response = await async_client.post(
            "/matchmaking/generate",
            json={"game_id": game_id, "player_ids": [a, b], "num_results": 1},
        )
        assert response.status_code == 200
        assert response.json()["configurations"][0]["lopsided"] is False

    async def test_runaway_rating_gap_is_flagged(self, async_client: AsyncClient):
        game_id, a, b = await self._setup(async_client)
        for _ in range(12):
            await _post(
                async_client,
                "/matches/",
                {
                    "game_id": game_id,
                    "participants": [
                        {"player_id": a, "team_id": 1, "outcome": {"result": "win"}},
                        {"player_id": b, "team_id": 2, "outcome": {"result": "loss"}},
                    ],
                },
            )
        response = await async_client.post(
            "/matchmaking/generate",
            json={"game_id": game_id, "player_ids": [a, b], "num_results": 1},
        )
        config = response.json()["configurations"][0]
        assert config["lopsided"] is True
        assert config["fairness"] < 0.4

    async def test_recent_pairings_accepted_by_api(self, async_client: AsyncClient):
        game_id, a, b = await self._setup(async_client)
        c = await _post(async_client, "/players/", {"name": "Crab"})
        d = await _post(async_client, "/players/", {"name": "Dab"})
        response = await async_client.post(
            "/matchmaking/generate",
            json={
                "game_id": game_id,
                "player_ids": [a, b, c["id"], d["id"]],
                "num_results": 1,
                "recent_pairings": [[a, b]],
            },
        )
        assert response.status_code == 200
        top_teams = [
            {member["player"]["id"] for member in team}
            for team in response.json()["configurations"][0]["teams"]
        ]
        assert {a, b} not in top_teams
