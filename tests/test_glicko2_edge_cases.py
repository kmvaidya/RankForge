# tests/test_glicko2_edge_cases.py

"""Tests for Glicko-2 rating engine edge cases."""

import math
from dataclasses import dataclass
from typing import Any, cast

import pytest
from httpx import AsyncClient

from rankforge.db.models import Match
from rankforge.exceptions import NonCompetitiveMatchError, RatingCalculationError
from rankforge.rating.glicko2_engine import (
    Glicko2Engine,
    Glicko2Rating,
    _calculate_player_scores,
)

# =============================================================================
# Unit Tests: Mock-based tests for _calculate_player_scores
# =============================================================================


@dataclass
class MockParticipant:
    """Mock participant for testing."""

    player_id: int
    team_id: int
    outcome: dict[str, Any]


@dataclass
class MockMatch:
    """Mock match for testing."""

    participants: list[MockParticipant]


def test_calculate_scores_win_loss_binary():
    """Test score calculation for binary win/loss matches."""
    match = MockMatch(
        participants=[
            MockParticipant(player_id=1, team_id=1, outcome={"result": "win"}),
            MockParticipant(player_id=2, team_id=2, outcome={"result": "loss"}),
        ]
    )

    scores = _calculate_player_scores(cast(Match, match))

    assert scores[1] == 1.0  # Winner
    assert scores[2] == 0.0  # Loser


def test_calculate_scores_all_draws():
    """Test that all-draw matches assign 0.5 to each player."""
    match = MockMatch(
        participants=[
            MockParticipant(player_id=1, team_id=1, outcome={"result": "draw"}),
            MockParticipant(player_id=2, team_id=2, outcome={"result": "draw"}),
        ]
    )

    scores = _calculate_player_scores(cast(Match, match))

    assert scores[1] == 0.5
    assert scores[2] == 0.5


def test_calculate_scores_ranked_ffa_three_players():
    """Test score calculation for 3-player FFA with ranks."""
    match = MockMatch(
        participants=[
            MockParticipant(player_id=1, team_id=1, outcome={"rank": 1}),  # 1st
            MockParticipant(player_id=2, team_id=2, outcome={"rank": 2}),  # 2nd
            MockParticipant(player_id=3, team_id=3, outcome={"rank": 3}),  # 3rd
        ]
    )

    scores = _calculate_player_scores(cast(Match, match))

    # num_opponents = 2
    # Rank 1: (2 - 0) / 2 = 1.0
    # Rank 2: (2 - 1) / 2 = 0.5
    # Rank 3: (2 - 2) / 2 = 0.0
    assert scores[1] == pytest.approx(1.0)
    assert scores[2] == pytest.approx(0.5)
    assert scores[3] == pytest.approx(0.0)


def test_calculate_scores_ranked_non_sequential_ranks():
    """Test that non-sequential ranks still work correctly."""
    # In a tournament, you might have ranks 1, 2, 5 (if 3, 4 DNF/DQ)
    match = MockMatch(
        participants=[
            MockParticipant(player_id=1, team_id=1, outcome={"rank": 1}),
            MockParticipant(player_id=2, team_id=2, outcome={"rank": 5}),
            MockParticipant(player_id=3, team_id=3, outcome={"rank": 10}),
        ]
    )

    scores = _calculate_player_scores(cast(Match, match))

    # num_opponents = 2
    # Rank 1: (2 - 0) / 2 = 1.0
    # Rank 5: (2 - 4) / 2 = -1.0 (can go negative for very bad placements)
    # Rank 10: (2 - 9) / 2 = -3.5
    assert scores[1] == pytest.approx(1.0)
    assert scores[2] == pytest.approx(-1.0)
    assert scores[3] == pytest.approx(-3.5)


def test_calculate_scores_single_team_raises_error():
    """Test that a match with only one team raises NonCompetitiveMatchError."""
    match = MockMatch(
        participants=[
            MockParticipant(player_id=1, team_id=1, outcome={"rank": 1}),
            MockParticipant(player_id=2, team_id=1, outcome={"rank": 1}),
        ]
    )

    with pytest.raises(NonCompetitiveMatchError) as exc_info:
        _calculate_player_scores(cast(Match, match))

    assert exc_info.value.details["team_count"] == 1


def test_calculate_scores_mixed_result_and_rank_uses_result():
    """Test that if any participant has a result, all must use result."""
    # This tests the priority: if ANY has win/loss/draw result, use that logic
    match = MockMatch(
        participants=[
            MockParticipant(player_id=1, team_id=1, outcome={"result": "win"}),
            MockParticipant(
                player_id=2, team_id=2, outcome={"result": "loss", "rank": 2}
            ),
        ]
    )

    scores = _calculate_player_scores(cast(Match, match))

    assert scores[1] == 1.0
    assert scores[2] == 0.0


def test_calculate_scores_invalid_result_raises_error():
    """Test that an invalid result string raises RatingCalculationError."""
    match = MockMatch(
        participants=[
            MockParticipant(player_id=1, team_id=1, outcome={"result": "win"}),
            MockParticipant(player_id=2, team_id=2, outcome={"result": "invalid"}),
        ]
    )

    with pytest.raises(RatingCalculationError) as exc_info:
        _calculate_player_scores(cast(Match, match))

    assert exc_info.value.details["player_id"] == 2


def test_calculate_scores_missing_rank_raises_error():
    """Test that missing rank in ranked match raises RatingCalculationError."""
    match = MockMatch(
        participants=[
            MockParticipant(player_id=1, team_id=1, outcome={"rank": 1}),
            MockParticipant(player_id=2, team_id=2, outcome={}),  # Missing rank
        ]
    )

    with pytest.raises(RatingCalculationError) as exc_info:
        _calculate_player_scores(cast(Match, match))

    assert exc_info.value.details["player_id"] == 2


# =============================================================================
# Unit Tests: Glicko2Engine rating calculations
# =============================================================================


def test_glicko2_engine_basic_win():
    """Test that winning increases rating and losing decreases it."""
    engine = Glicko2Engine()

    # Two equal players
    player1 = Glicko2Rating(mu=1500.0, phi=350.0, sigma=0.06)
    player2 = Glicko2Rating(mu=1500.0, phi=350.0, sigma=0.06)

    # Player 1 wins against player 2
    new_rating = engine.rate(player1, [(player2, 1.0)])

    # Winner's rating should increase
    assert new_rating.mu > 1500.0


def test_glicko2_engine_basic_loss():
    """Test that losing decreases rating."""
    engine = Glicko2Engine()

    player1 = Glicko2Rating(mu=1500.0, phi=350.0, sigma=0.06)
    player2 = Glicko2Rating(mu=1500.0, phi=350.0, sigma=0.06)

    # Player 1 loses against player 2
    new_rating = engine.rate(player1, [(player2, 0.0)])

    # Loser's rating should decrease
    assert new_rating.mu < 1500.0


def test_glicko2_engine_draw_between_equals():
    """Test that a draw between equal players keeps ratings similar."""
    engine = Glicko2Engine()

    player1 = Glicko2Rating(mu=1500.0, phi=350.0, sigma=0.06)
    player2 = Glicko2Rating(mu=1500.0, phi=350.0, sigma=0.06)

    # Draw
    new_rating = engine.rate(player1, [(player2, 0.5)])

    # Rating should stay close to original (small change due to RD adjustment)
    assert abs(new_rating.mu - 1500.0) < 10


def test_glicko2_engine_high_rd_larger_changes():
    """Test that players with high RD have larger rating changes."""
    engine = Glicko2Engine()

    high_rd_player = Glicko2Rating(mu=1500.0, phi=350.0, sigma=0.06)  # High RD
    low_rd_player = Glicko2Rating(mu=1500.0, phi=50.0, sigma=0.06)  # Low RD
    opponent = Glicko2Rating(mu=1500.0, phi=200.0, sigma=0.06)

    # Both win
    high_rd_result = engine.rate(high_rd_player, [(opponent, 1.0)])
    low_rd_result = engine.rate(low_rd_player, [(opponent, 1.0)])

    # High RD player should have larger rating change
    high_rd_change = abs(high_rd_result.mu - high_rd_player.mu)
    low_rd_change = abs(low_rd_result.mu - low_rd_player.mu)

    assert high_rd_change > low_rd_change


def test_glicko2_engine_rd_decreases_after_play():
    """Test that RD (rating deviation) decreases after playing."""
    engine = Glicko2Engine()

    player = Glicko2Rating(mu=1500.0, phi=350.0, sigma=0.06)
    opponent = Glicko2Rating(mu=1500.0, phi=350.0, sigma=0.06)

    new_rating = engine.rate(player, [(opponent, 1.0)])

    # RD should decrease after playing (more certain about rating)
    assert new_rating.phi < player.phi


def test_glicko2_engine_upset_win_larger_gain():
    """Test that beating a higher-rated player gives larger rating increase."""
    engine = Glicko2Engine()

    underdog = Glicko2Rating(mu=1000.0, phi=200.0, sigma=0.06)
    favorite = Glicko2Rating(mu=2000.0, phi=200.0, sigma=0.06)
    equal = Glicko2Rating(mu=1000.0, phi=200.0, sigma=0.06)

    # Underdog beats favorite
    upset_result = engine.rate(underdog, [(favorite, 1.0)])

    # Underdog beats equal
    normal_result = engine.rate(underdog, [(equal, 1.0)])

    # Upset should give larger rating boost
    assert (upset_result.mu - 1000.0) > (normal_result.mu - 1000.0)


def test_glicko2_engine_no_opponents_increases_rd():
    """Test that not playing increases RD (more uncertainty)."""
    engine = Glicko2Engine()

    player = Glicko2Rating(mu=1500.0, phi=100.0, sigma=0.06)

    # No opponents (rating period with no games)
    new_rating = engine.rate(player, [])

    # RD should increase
    assert new_rating.phi > player.phi
    # Rating should stay the same
    assert new_rating.mu == player.mu


def test_glicko2_engine_high_volatility():
    """Test rating calculation with high volatility player."""
    engine = Glicko2Engine()

    # High volatility indicates inconsistent performance
    volatile_player = Glicko2Rating(mu=1500.0, phi=350.0, sigma=0.10)
    stable_player = Glicko2Rating(mu=1500.0, phi=350.0, sigma=0.03)
    opponent = Glicko2Rating(mu=1500.0, phi=350.0, sigma=0.06)

    volatile_result = engine.rate(volatile_player, [(opponent, 1.0)])
    stable_result = engine.rate(stable_player, [(opponent, 1.0)])

    # Both should increase rating
    assert volatile_result.mu > 1500.0
    assert stable_result.mu > 1500.0


def test_glicko2_engine_multiple_opponents():
    """Test rating against multiple opponents in one period."""
    engine = Glicko2Engine()

    player = Glicko2Rating(mu=1500.0, phi=350.0, sigma=0.06)
    opp1 = Glicko2Rating(mu=1400.0, phi=350.0, sigma=0.06)
    opp2 = Glicko2Rating(mu=1600.0, phi=350.0, sigma=0.06)

    # Beat weaker, lose to stronger
    new_rating = engine.rate(player, [(opp1, 1.0), (opp2, 0.0)])

    # Should be close to original since beat weaker, lost to stronger
    assert abs(new_rating.mu - 1500.0) < 100


# =============================================================================
# Unit Tests: Extreme Rating Value Edge Cases
# =============================================================================


def test_glicko2_engine_very_low_rating():
    """Test rating calculation with near-zero rating (rating = 100)."""
    engine = Glicko2Engine()
    low_rated = Glicko2Rating(mu=100.0, phi=200.0, sigma=0.06)
    opponent = Glicko2Rating(mu=1500.0, phi=200.0, sigma=0.06)

    # Low rated player wins (major upset)
    new_rating = engine.rate(low_rated, [(opponent, 1.0)])

    # Should have substantial rating increase, no math errors
    assert new_rating.mu > 100.0
    assert new_rating.mu > low_rated.mu + 100  # Substantial gain
    assert not math.isnan(new_rating.mu)
    assert not math.isinf(new_rating.mu)


def test_glicko2_engine_very_high_rating():
    """Test rating calculation with very high rating (rating = 3500)."""
    engine = Glicko2Engine()
    high_rated = Glicko2Rating(mu=3500.0, phi=200.0, sigma=0.06)
    opponent = Glicko2Rating(mu=1500.0, phi=200.0, sigma=0.06)

    # High rated player loses (upset)
    new_rating = engine.rate(high_rated, [(opponent, 0.0)])

    # Should decrease but remain valid
    assert new_rating.mu < 3500.0
    assert new_rating.mu > 0  # Should not go negative
    assert not math.isnan(new_rating.mu)
    assert not math.isinf(new_rating.mu)


def test_glicko2_engine_rating_at_zero():
    """Test rating calculation when rating equals zero."""
    engine = Glicko2Engine()
    zero_rated = Glicko2Rating(mu=0.0, phi=350.0, sigma=0.06)
    opponent = Glicko2Rating(mu=1500.0, phi=200.0, sigma=0.06)

    # Zero-rated player wins
    new_rating = engine.rate(zero_rated, [(opponent, 1.0)])

    # Calculation should complete without error
    assert new_rating.mu > 0.0  # Should increase after win
    assert not math.isnan(new_rating.mu)
    assert not math.isinf(new_rating.mu)


def test_glicko2_engine_minimum_rd():
    """Test rating with near-minimum RD (phi = 10.0 - very certain)."""
    engine = Glicko2Engine()
    certain_player = Glicko2Rating(mu=1500.0, phi=10.0, sigma=0.06)
    opponent = Glicko2Rating(mu=1500.0, phi=200.0, sigma=0.06)

    new_rating = engine.rate(certain_player, [(opponent, 1.0)])

    # Rating change should be small due to low RD (high certainty)
    rating_change = abs(new_rating.mu - certain_player.mu)
    assert rating_change < 50  # Small change due to certainty
    assert new_rating.phi > 0  # RD stays positive
    assert not math.isnan(new_rating.phi)
    assert not math.isinf(new_rating.phi)


def test_glicko2_engine_maximum_rd():
    """Test rating with maximum RD (phi = 400.0 - very uncertain)."""
    engine = Glicko2Engine()
    uncertain_player = Glicko2Rating(mu=1500.0, phi=400.0, sigma=0.06)
    opponent = Glicko2Rating(mu=1500.0, phi=200.0, sigma=0.06)

    new_rating = engine.rate(uncertain_player, [(opponent, 1.0)])

    # Should handle gracefully
    assert new_rating.mu > 1500.0  # Win increases rating
    assert new_rating.phi < 400.0  # RD should decrease after playing
    assert not math.isnan(new_rating.mu)
    assert not math.isnan(new_rating.phi)


def test_glicko2_engine_near_zero_volatility():
    """Test rating with near-zero volatility (sigma = 0.001)."""
    engine = Glicko2Engine()
    stable_player = Glicko2Rating(mu=1500.0, phi=200.0, sigma=0.001)
    opponent = Glicko2Rating(mu=1500.0, phi=200.0, sigma=0.06)

    new_rating = engine.rate(stable_player, [(opponent, 1.0)])

    # Calculation should complete without error
    assert not math.isnan(new_rating.sigma)
    assert not math.isinf(new_rating.sigma)
    assert new_rating.sigma > 0
    assert new_rating.mu > 1500.0  # Win increases rating


def test_glicko2_engine_high_volatility_extreme():
    """Test rating with high volatility (sigma = 0.15)."""
    engine = Glicko2Engine()
    volatile_player = Glicko2Rating(mu=1500.0, phi=200.0, sigma=0.15)
    opponent = Glicko2Rating(mu=1500.0, phi=200.0, sigma=0.06)

    new_rating = engine.rate(volatile_player, [(opponent, 1.0)])

    # Calculation should complete without error
    assert not math.isnan(new_rating.sigma)
    assert not math.isinf(new_rating.sigma)
    assert new_rating.sigma > 0
    assert new_rating.sigma < 1.0  # Should stay bounded


def test_glicko2_engine_extreme_rating_difference():
    """Test match between players with massive rating difference (3000+ gap)."""
    engine = Glicko2Engine()
    grandmaster = Glicko2Rating(mu=3000.0, phi=50.0, sigma=0.06)
    beginner = Glicko2Rating(mu=100.0, phi=350.0, sigma=0.06)

    # Beginner beats grandmaster (massive upset)
    beginner_result = engine.rate(beginner, [(grandmaster, 1.0)])
    grandmaster_result = engine.rate(grandmaster, [(beginner, 0.0)])

    # Both calculations complete without NaN/Inf
    assert not math.isnan(beginner_result.mu)
    assert not math.isnan(grandmaster_result.mu)
    assert not math.isinf(beginner_result.mu)
    assert not math.isinf(grandmaster_result.mu)

    # Beginner gains rating, grandmaster loses
    assert beginner_result.mu > beginner.mu
    assert grandmaster_result.mu < grandmaster.mu


# =============================================================================
# API Integration Tests: Glicko-2 edge cases via API
# =============================================================================


@pytest.mark.asyncio
async def test_api_match_between_unequal_ratings(async_client: AsyncClient):
    """Test that rating changes are correct when unequal players compete."""
    # 1. ARRANGE: Create a game.
    game_res = await async_client.post(
        "/games/", json={"name": "UnequalRatingGame", "rating_strategy": "glicko2"}
    )
    assert game_res.status_code == 201
    game_id = game_res.json()["id"]

    # Create two players.
    player1_res = await async_client.post("/players/", json={"name": "HighRatedPlayer"})
    player1_id = player1_res.json()["id"]

    player2_res = await async_client.post("/players/", json={"name": "LowRatedPlayer"})
    player2_id = player2_res.json()["id"]

    # 2. ACT: Create a match where the lower-rated player wins (upset).
    match_payload = {
        "game_id": game_id,
        "participants": [
            {
                "player_id": player1_id,
                "team_id": 1,
                "outcome": {"result": "loss"},
            },  # Favorite loses
            {
                "player_id": player2_id,
                "team_id": 2,
                "outcome": {"result": "win"},
            },  # Underdog wins
        ],
    }
    match_res = await async_client.post("/matches/", json=match_payload)
    assert match_res.status_code == 201

    # 3. ASSERT: Check leaderboard to verify ratings changed.
    leaderboard_res = await async_client.get(f"/games/{game_id}/leaderboard")
    assert leaderboard_res.status_code == 200
    entries = leaderboard_res.json()["items"]

    # Winner should have higher rating now
    winner_entry = next(e for e in entries if e["player"]["id"] == player2_id)
    loser_entry = next(e for e in entries if e["player"]["id"] == player1_id)

    # Winner's rating should be higher than initial 1500
    assert winner_entry["rating_info"]["rating"] > 1500
    # Loser's rating should be lower than initial 1500
    assert loser_entry["rating_info"]["rating"] < 1500


@pytest.mark.asyncio
async def test_api_match_with_draw_outcome(async_client: AsyncClient):
    """Test that draw outcomes result in minimal rating changes."""
    # 1. ARRANGE: Create a game and two players.
    game_res = await async_client.post(
        "/games/", json={"name": "DrawTestGame", "rating_strategy": "glicko2"}
    )
    assert game_res.status_code == 201
    game_id = game_res.json()["id"]

    player1_res = await async_client.post("/players/", json={"name": "DrawPlayer1"})
    player1_id = player1_res.json()["id"]

    player2_res = await async_client.post("/players/", json={"name": "DrawPlayer2"})
    player2_id = player2_res.json()["id"]

    # 2. ACT: Create a match that ends in a draw.
    match_payload = {
        "game_id": game_id,
        "participants": [
            {"player_id": player1_id, "team_id": 1, "outcome": {"result": "draw"}},
            {"player_id": player2_id, "team_id": 2, "outcome": {"result": "draw"}},
        ],
    }
    match_res = await async_client.post("/matches/", json=match_payload)
    assert match_res.status_code == 201

    # 3. ASSERT: Both players should have ratings close to 1500.
    leaderboard_res = await async_client.get(f"/games/{game_id}/leaderboard")
    assert leaderboard_res.status_code == 200
    entries = leaderboard_res.json()["items"]

    for entry in entries:
        # Rating should be close to 1500 after a draw
        assert abs(entry["rating_info"]["rating"] - 1500) < 50


@pytest.mark.asyncio
async def test_api_ranked_ffa_match(async_client: AsyncClient):
    """Test a ranked free-for-all match with three players."""
    # 1. ARRANGE: Create a game and three players.
    game_res = await async_client.post(
        "/games/", json={"name": "FFATestGame", "rating_strategy": "glicko2"}
    )
    assert game_res.status_code == 201
    game_id = game_res.json()["id"]

    player1_res = await async_client.post("/players/", json={"name": "FFAPlayer1"})
    player1_id = player1_res.json()["id"]

    player2_res = await async_client.post("/players/", json={"name": "FFAPlayer2"})
    player2_id = player2_res.json()["id"]

    player3_res = await async_client.post("/players/", json={"name": "FFAPlayer3"})
    player3_id = player3_res.json()["id"]

    # 2. ACT: Create a ranked FFA match.
    match_payload = {
        "game_id": game_id,
        "participants": [
            {
                "player_id": player1_id,
                "team_id": 1,
                "outcome": {"rank": 1},
            },  # 1st place
            {
                "player_id": player2_id,
                "team_id": 2,
                "outcome": {"rank": 2},
            },  # 2nd place
            {
                "player_id": player3_id,
                "team_id": 3,
                "outcome": {"rank": 3},
            },  # 3rd place
        ],
    }
    match_res = await async_client.post("/matches/", json=match_payload)
    assert match_res.status_code == 201

    # 3. ASSERT: Verify rankings make sense.
    leaderboard_res = await async_client.get(f"/games/{game_id}/leaderboard")
    assert leaderboard_res.status_code == 200
    entries = leaderboard_res.json()["items"]

    # Get ratings by player
    ratings = {e["player"]["id"]: e["rating_info"]["rating"] for e in entries}

    # 1st place should have highest rating
    assert ratings[player1_id] > ratings[player2_id]
    # 2nd place should be in the middle
    assert ratings[player2_id] > ratings[player3_id]
    # 3rd place should have lowest rating
    assert ratings[player3_id] < 1500


@pytest.mark.asyncio
async def test_api_match_rating_info_tracking(async_client: AsyncClient):
    """Test that rating_info_before and rating_info_change are tracked."""
    # 1. ARRANGE: Create a game and two players.
    game_res = await async_client.post(
        "/games/", json={"name": "RatingTrackingGame", "rating_strategy": "glicko2"}
    )
    assert game_res.status_code == 201
    game_id = game_res.json()["id"]

    player1_res = await async_client.post("/players/", json={"name": "TrackingPlayer1"})
    player1_id = player1_res.json()["id"]

    player2_res = await async_client.post("/players/", json={"name": "TrackingPlayer2"})
    player2_id = player2_res.json()["id"]

    # 2. ACT: Create a match.
    match_payload = {
        "game_id": game_id,
        "participants": [
            {"player_id": player1_id, "team_id": 1, "outcome": {"result": "win"}},
            {"player_id": player2_id, "team_id": 2, "outcome": {"result": "loss"}},
        ],
    }
    match_res = await async_client.post("/matches/", json=match_payload)
    assert match_res.status_code == 201

    # 3. ASSERT: Check that rating info is tracked in the response.
    match_data = match_res.json()

    for p in match_data["participants"]:
        # Should have before rating (initial values)
        assert p["rating_info_before"] is not None
        assert p["rating_info_before"]["rating"] == 1500.0

        # Should have change info
        assert p["rating_info_change"] is not None
        assert "rating_change" in p["rating_info_change"]


@pytest.mark.asyncio
async def test_api_multiple_matches_cumulative_ratings(async_client: AsyncClient):
    """Test that ratings accumulate correctly across multiple matches."""
    # 1. ARRANGE: Create a game and two players.
    game_res = await async_client.post(
        "/games/", json={"name": "CumulativeGame", "rating_strategy": "glicko2"}
    )
    assert game_res.status_code == 201
    game_id = game_res.json()["id"]

    player1_res = await async_client.post(
        "/players/", json={"name": "CumulativePlayer1"}
    )
    player1_id = player1_res.json()["id"]

    player2_res = await async_client.post(
        "/players/", json={"name": "CumulativePlayer2"}
    )
    player2_id = player2_res.json()["id"]

    # 2. ACT: Create multiple matches where player1 always wins.
    for _ in range(3):
        match_payload = {
            "game_id": game_id,
            "participants": [
                {"player_id": player1_id, "team_id": 1, "outcome": {"result": "win"}},
                {"player_id": player2_id, "team_id": 2, "outcome": {"result": "loss"}},
            ],
        }
        match_res = await async_client.post("/matches/", json=match_payload)
        assert match_res.status_code == 201

    # 3. ASSERT: Player1 should have significantly higher rating.
    leaderboard_res = await async_client.get(f"/games/{game_id}/leaderboard")
    assert leaderboard_res.status_code == 200
    entries = leaderboard_res.json()["items"]

    ratings = {e["player"]["id"]: e["rating_info"]["rating"] for e in entries}

    # After 3 wins, player1 should be well above 1500
    assert ratings[player1_id] > 1600
    # After 3 losses, player2 should be well below 1500
    assert ratings[player2_id] < 1400
