# tests/test_rd_growth.py

"""Tests for inactivity RD growth (rating_config.rd_growth_period_days)."""

import pytest
from httpx import AsyncClient

from rankforge.rating.glicko2_engine import Glicko2Rating, _grow_rd


class TestGrowRd:
    def test_disabled_or_no_elapsed_is_identity(self):
        rating = Glicko2Rating(1600.0, 80.0, 0.06)
        assert _grow_rd(rating, 30.0, 0.0) is rating
        assert _grow_rd(rating, 0.0, 7.0) is rating

    def test_growth_increases_rd_and_preserves_rating(self):
        rating = Glicko2Rating(1600.0, 80.0, 0.06)
        grown = _grow_rd(rating, 365.0, 7.0)
        assert grown.phi > rating.phi
        assert grown.mu == rating.mu
        assert grown.sigma == rating.sigma

    def test_growth_caps_at_initial_rd(self):
        rating = Glicko2Rating(1600.0, 300.0, 0.5)
        grown = _grow_rd(rating, 100_000.0, 1.0)
        assert grown.phi == 350.0

    def test_never_shrinks_above_cap(self):
        # A season reset can legitimately push RD past 350; growth must not
        # pull it back down.
        rating = Glicko2Rating(1600.0, 450.0, 0.06)
        grown = _grow_rd(rating, 30.0, 7.0)
        assert grown.phi >= 450.0


async def _post(async_client: AsyncClient, path: str, body: dict) -> dict:
    response = await async_client.post(path, json=body)
    assert response.status_code == 201, response.text
    return dict(response.json())


async def _setup(async_client: AsyncClient, period_days: float) -> tuple[int, int, int]:
    game = await _post(
        async_client,
        "/games/",
        {
            "name": "RustGame",
            "rating_strategy": "glicko2",
            "rating_config": {"rd_growth_period_days": period_days},
        },
    )
    a = await _post(async_client, "/players/", {"name": "Ada"})
    b = await _post(async_client, "/players/", {"name": "Bo"})
    return game["id"], a["id"], b["id"]


async def _play(
    async_client: AsyncClient,
    game_id: int,
    winner: int,
    loser: int,
    played_at: str,
) -> dict:
    return await _post(
        async_client,
        "/matches/",
        {
            "game_id": game_id,
            "played_at": played_at,
            "participants": [
                {"player_id": winner, "team_id": 1, "outcome": {"result": "win"}},
                {"player_id": loser, "team_id": 2, "outcome": {"result": "loss"}},
            ],
        },
    )


def _rd_after(match: dict, player_id: int) -> float:
    p = next(p for p in match["participants"] if p["player_id"] == player_id)
    return float(p["rating_info_before"]["rd"]) + float(
        p["rating_info_change"]["rd_change"]
    )


def _rd_before(match: dict, player_id: int) -> float:
    p = next(p for p in match["participants"] if p["player_id"] == player_id)
    return float(p["rating_info_before"]["rd"])


@pytest.mark.asyncio
class TestInactivityGrowth:
    async def test_long_gap_raises_rd(self, async_client: AsyncClient):
        game_id, ada, bo = await _setup(async_client, period_days=7.0)
        # Three quick matches settle the ratings a bit…
        for day in ("01", "02", "03"):
            first = await _play(
                async_client, game_id, ada, bo, f"2026-01-{day}T12:00:00"
            )
        rd_settled = _rd_after(first, ada)
        # …then half a year off. The next match must start from a higher RD
        # than the settled value. rating_info_before stores the pre-growth
        # value, so the growth shows up in rd_change instead: the post-match
        # RD is higher than an uninterrupted schedule would produce.
        comeback = await _play(async_client, game_id, ada, bo, "2026-07-03T12:00:00")
        assert _rd_before(comeback, ada) == pytest.approx(rd_settled, abs=0.02)
        followup = await _play(async_client, game_id, ada, bo, "2026-07-03T13:00:00")
        # After the comeback match, RD reflects the growth: it lands higher
        # than it was before the break's match despite two more games played.
        assert _rd_after(comeback, ada) > rd_settled - 40

        # Control game without growth: same schedule ends with a lower RD
        # after the comeback match than the growth game.
        control_game = await _post(
            async_client,
            "/games/",
            {"name": "NoRustGame", "rating_strategy": "glicko2"},
        )
        for day in ("01", "02", "03"):
            await _play(
                async_client, control_game["id"], ada, bo, f"2026-01-{day}T12:00:00"
            )
        control_comeback = await _play(
            async_client, control_game["id"], ada, bo, "2026-07-03T12:00:00"
        )
        assert _rd_after(comeback, ada) > _rd_after(control_comeback, ada)
        assert followup is not None

    async def test_recalculation_reproduces_growth_exactly(
        self, async_client: AsyncClient
    ):
        game_id, ada, bo = await _setup(async_client, period_days=3.0)
        await _play(async_client, game_id, ada, bo, "2026-01-01T12:00:00")
        await _play(async_client, game_id, bo, ada, "2026-02-15T12:00:00")
        await _play(async_client, game_id, ada, bo, "2026-06-01T12:00:00")

        before = (await async_client.get(f"/games/{game_id}/leaderboard")).json()[
            "items"
        ]
        recalc = await async_client.post(f"/games/{game_id}/recalculate")
        assert recalc.status_code == 200
        after = (await async_client.get(f"/games/{game_id}/leaderboard")).json()[
            "items"
        ]

        assert [e["rating_info"] for e in before] == [e["rating_info"] for e in after]

    async def test_calibration_runs_with_growth_enabled(
        self, async_client: AsyncClient
    ):
        game_id, ada, bo = await _setup(async_client, period_days=7.0)
        await _play(async_client, game_id, ada, bo, "2026-01-01T12:00:00")
        await _play(async_client, game_id, ada, bo, "2026-03-01T12:00:00")
        response = await async_client.get(
            f"/games/{game_id}/calibration", params={"warmup": 0}
        )
        assert response.status_code == 200
        assert response.json()["comparisons_evaluated"] == 2

    async def test_config_validation(self, async_client: AsyncClient):
        bad_negative = await async_client.post(
            "/games/",
            json={
                "name": "BadGrowth",
                "rating_strategy": "glicko2",
                "rating_config": {"rd_growth_period_days": -1},
            },
        )
        assert bad_negative.status_code == 422
        bad_bool = await async_client.post(
            "/games/",
            json={
                "name": "BadGrowth2",
                "rating_strategy": "glicko2",
                "rating_config": {"rd_growth_period_days": True},
            },
        )
        assert bad_bool.status_code == 422
