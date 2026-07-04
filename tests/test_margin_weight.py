# tests/test_margin_weight.py

"""Tests for score-margin weight scaling (rating_config.margin_weight_factor)."""

from dataclasses import dataclass, field
from typing import cast

import pytest
from httpx import AsyncClient

from rankforge.db.models import Game, Match
from rankforge.exceptions import RatingCalculationError
from rankforge.rating.glicko2_engine import _margin_multiplier

pytestmark = pytest.mark.asyncio


@dataclass
class FakeMatch:
    match_metadata: dict = field(default_factory=dict)
    id: int = 1


@dataclass
class FakeGame:
    rating_config: dict = field(default_factory=dict)


def _mult(metadata: dict, config: dict) -> float:
    return _margin_multiplier(
        cast(Match, FakeMatch(match_metadata=metadata)),
        cast(Game, FakeGame(rating_config=config)),
    )


class TestMarginMultiplier:
    def test_disabled_by_default(self):
        assert _mult({"team_scores": {"1": 11, "2": 0}}, {}) == 1.0

    def test_no_scores_is_neutral(self):
        assert _mult({}, {"margin_weight_factor": 1.0}) == 1.0

    def test_blowout_scales_to_one_plus_factor(self):
        assert _mult(
            {"team_scores": {"1": 11, "2": 0}}, {"margin_weight_factor": 1.0}
        ) == pytest.approx(2.0)

    def test_close_game_stays_near_one(self):
        assert _mult(
            {"team_scores": {"1": 11, "2": 9}}, {"margin_weight_factor": 1.0}
        ) == pytest.approx(1.1)

    def test_tie_scores_neutral(self):
        assert _mult(
            {"team_scores": {"1": 7, "2": 7}}, {"margin_weight_factor": 2.0}
        ) == pytest.approx(1.0)

    def test_zero_total_neutral(self):
        assert (
            _mult({"team_scores": {"1": 0, "2": 0}}, {"margin_weight_factor": 1.0})
            == 1.0
        )

    def test_three_team_scores_ignored(self):
        assert (
            _mult(
                {"team_scores": {"1": 5, "2": 3, "3": 1}},
                {"margin_weight_factor": 1.0},
            )
            == 1.0
        )

    @pytest.mark.parametrize("bad", [{"1": -1, "2": 5}, {"1": "x", "2": 5}])
    def test_malformed_scores_raise(self, bad: dict):
        with pytest.raises(RatingCalculationError):
            _mult({"team_scores": bad}, {"margin_weight_factor": 1.0})

    def test_invalid_factor_raises(self):
        with pytest.raises(RatingCalculationError):
            _mult({"team_scores": {"1": 1, "2": 0}}, {"margin_weight_factor": -1})


async def _gain_after_match(
    async_client: AsyncClient, game_name: str, config: dict | None, metadata: dict
) -> float:
    body: dict = {"name": game_name, "rating_strategy": "glicko2"}
    if config:
        body["rating_config"] = config
    game = (await async_client.post("/games/", json=body)).json()
    p1 = (await async_client.post("/players/", json={"name": f"{game_name}W"})).json()
    p2 = (await async_client.post("/players/", json={"name": f"{game_name}L"})).json()
    response = await async_client.post(
        "/matches/",
        json={
            "game_id": game["id"],
            "match_metadata": metadata,
            "participants": [
                {"player_id": p1["id"], "team_id": 1, "outcome": {"result": "win"}},
                {"player_id": p2["id"], "team_id": 2, "outcome": {"result": "loss"}},
            ],
        },
    )
    assert response.status_code == 201, response.text
    winner = next(
        p for p in response.json()["participants"] if p["player"]["id"] == p1["id"]
    )
    return float(winner["rating_info_change"]["rating_change"])


class TestMarginEndToEnd:
    async def test_blowout_moves_more_than_close_game(self, async_client: AsyncClient):
        config = {"margin_weight_factor": 1.0}
        blowout = await _gain_after_match(
            async_client, "MarginBlowout", config, {"team_scores": {"1": 11, "2": 0}}
        )
        close = await _gain_after_match(
            async_client, "MarginClose", config, {"team_scores": {"1": 11, "2": 9}}
        )
        plain = await _gain_after_match(
            async_client, "MarginPlain", None, {"team_scores": {"1": 11, "2": 0}}
        )
        assert blowout > close
        assert blowout > plain
        assert close == pytest.approx(plain, rel=0.25)  # 1.1x vs 1.0x, same ballpark

    async def test_margin_composes_with_match_weight(self, async_client: AsyncClient):
        """weight * margin: a weighted blowout outmoves the same weight alone."""
        config = {"margin_weight_factor": 1.0}
        weighted_blowout = await _gain_after_match(
            async_client,
            "MarginWeighted",
            config,
            {"weight": 2.0, "team_scores": {"1": 11, "2": 0}},
        )
        weighted_only = await _gain_after_match(
            async_client, "WeightOnly", config, {"weight": 2.0}
        )
        assert weighted_blowout > weighted_only
