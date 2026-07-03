# tests/test_match_weight.py

"""Tests for match weighting (match_metadata.weight) in the Glicko-2 engine.

A weight w scales the information a match carries: contributions to the
variance and improvement sums are multiplied by w, equivalent to playing
w copies of the game. Weight 1.0 (or absent) is exactly the unweighted
behavior; w < 1 dampens the match; w > 1 amplifies it.
"""

from dataclasses import dataclass, field
from typing import Any, cast

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rankforge.db.models import Game, GameProfile, Match, Player
from rankforge.exceptions import RatingCalculationError
from rankforge.rating.glicko2_engine import Glicko2Engine, Glicko2Rating, _match_weight
from rankforge.schemas.match import MatchCreate, MatchParticipantCreate
from rankforge.services import match_service

# ===============================================
# == Pure engine math
# ===============================================


def _rate_fresh_win(weight: float) -> Glicko2Rating:
    """Rate a fresh player beating an equally fresh opponent at a weight."""
    engine = Glicko2Engine()
    player = Glicko2Rating()
    opponent = Glicko2Rating()
    return engine.rate(player, [(opponent, 1.0)], weight)


def test_weight_one_matches_unweighted_behavior():
    engine = Glicko2Engine()
    unweighted = engine.rate(Glicko2Rating(), [(Glicko2Rating(), 1.0)])
    weighted = _rate_fresh_win(1.0)
    assert weighted.mu == pytest.approx(unweighted.mu)
    assert weighted.phi == pytest.approx(unweighted.phi)
    assert weighted.sigma == pytest.approx(unweighted.sigma)


def test_higher_weight_moves_rating_more():
    quarter = _rate_fresh_win(0.25)
    normal = _rate_fresh_win(1.0)
    heavy = _rate_fresh_win(5.0)
    # Rating gain from a win grows with weight.
    assert 1500 < quarter.mu < normal.mu < heavy.mu
    # Certainty gain (RD reduction) grows with weight too.
    assert heavy.phi < normal.phi < quarter.phi < 350


def test_near_zero_weight_barely_moves_rating():
    result = _rate_fresh_win(1e-9)
    assert result.mu == pytest.approx(1500, abs=0.01)


# ===============================================
# == Weight extraction / validation
# ===============================================


@dataclass
class FakeMatch:
    id: int = 1
    match_metadata: dict = field(default_factory=dict)


def _weight_of(metadata: Any) -> float:
    return _match_weight(cast(Match, FakeMatch(match_metadata=metadata)))


def test_weight_defaults_to_one():
    assert _weight_of({}) == 1.0
    assert _weight_of(None) == 1.0
    assert _weight_of({"other_key": 3}) == 1.0


def test_valid_weights_are_extracted():
    assert _weight_of({"weight": 0.28}) == 0.28
    assert _weight_of({"weight": 5}) == 5.0


@pytest.mark.parametrize("bad", [0, -1, "high", True, None, [2]])
def test_invalid_weight_raises(bad):
    with pytest.raises(RatingCalculationError):
        _weight_of({"weight": bad})


# ===============================================
# == End-to-end through the service layer
# ===============================================


async def _play_weighted_match(
    db: AsyncSession, game_name: str, metadata: dict
) -> tuple[dict, dict]:
    """Create a fresh 1v1 win in its own game; return (winner, loser) rating_info."""
    game = Game(name=game_name, rating_strategy="glicko2")
    winner = Player(name=f"{game_name} Winner")
    loser = Player(name=f"{game_name} Loser")
    db.add_all([game, winner, loser])
    await db.commit()

    match_in = MatchCreate(
        game_id=game.id,
        match_metadata=metadata,
        participants=[
            MatchParticipantCreate(
                player_id=winner.id, team_id=1, outcome={"result": "win"}
            ),
            MatchParticipantCreate(
                player_id=loser.id, team_id=2, outcome={"result": "loss"}
            ),
        ],
    )
    await match_service.process_new_match(db=db, match_in=match_in)

    async def profile_rating(player_id: int) -> dict:
        result = await db.execute(
            select(GameProfile).where(
                GameProfile.game_id == game.id, GameProfile.player_id == player_id
            )
        )
        return dict(result.scalar_one().rating_info)

    return await profile_rating(winner.id), await profile_rating(loser.id)


@pytest.mark.asyncio
async def test_weighted_match_amplifies_rating_change(db_session: AsyncSession):
    normal_winner, normal_loser = await _play_weighted_match(
        db_session, "Weight Normal", {}
    )
    heavy_winner, heavy_loser = await _play_weighted_match(
        db_session, "Weight Heavy", {"weight": 4.0}
    )
    assert heavy_winner["rating"] > normal_winner["rating"] > 1500
    assert heavy_loser["rating"] < normal_loser["rating"] < 1500
    assert heavy_winner["rd"] < normal_winner["rd"] < 350


@pytest.mark.asyncio
async def test_invalid_weight_rejects_match_atomically(
    async_client: AsyncClient, db_session: AsyncSession
):
    game = Game(name="Weight Invalid", rating_strategy="glicko2")
    p1 = Player(name="Invalid W1")
    p2 = Player(name="Invalid W2")
    db_session.add_all([game, p1, p2])
    await db_session.commit()
    # Capture plain ints: the failed request rolls back the shared session,
    # expiring these ORM objects — attribute access afterwards would lazy-load.
    game_id, p1_id, p2_id = game.id, p1.id, p2.id

    response = await async_client.post(
        "/matches/",
        json={
            "game_id": game_id,
            "match_metadata": {"weight": -2},
            "participants": [
                {"player_id": p1_id, "team_id": 1, "outcome": {"result": "win"}},
                {"player_id": p2_id, "team_id": 2, "outcome": {"result": "loss"}},
            ],
        },
    )
    assert response.status_code == 500

    result = await db_session.execute(select(Match).where(Match.game_id == game_id))
    assert result.scalars().first() is None
