# tests/test_tune_tool.py

"""Tests for the offline rating-parameter tuning tool (in-memory replay)."""

import math

from rankforge.tools.tune import ReplayMatch, ReplayParticipant, evaluate


def _one_vs_one(match_id: int, winner: int, loser: int) -> ReplayMatch:
    return ReplayMatch(
        id=match_id,
        match_metadata={},
        participants=[
            ReplayParticipant(winner, 1, {"result": "win"}),
            ReplayParticipant(loser, 2, {"result": "loss"}),
        ],
    )


def test_dominant_player_beats_coin_flip():
    """If A always beats B, ratings should predict better than 0.25 Brier."""
    matches = [_one_vs_one(i, 1, 2) for i in range(20)]
    result = evaluate(
        matches, {}, tau=0.5, initial_rd=350.0, warmup=3, drift_weight=1.0
    )
    assert result.brier < 0.25
    assert result.drift >= 0
    assert math.isfinite(result.composite)


def test_warmup_larger_than_history_gives_nan_brier():
    matches = [_one_vs_one(i, 1, 2) for i in range(3)]
    result = evaluate(
        matches, {}, tau=0.5, initial_rd=350.0, warmup=50, drift_weight=1.0
    )
    assert math.isnan(result.brier)


def test_margin_config_respected_in_replay():
    """team_scores + margin factor changes the replayed outcome ratings."""
    matches = [
        ReplayMatch(
            id=i,
            match_metadata={"team_scores": {"1": 11, "2": 0}},
            participants=[
                ReplayParticipant(1, 1, {"result": "win"}),
                ReplayParticipant(2, 2, {"result": "loss"}),
            ],
        )
        for i in range(5)
    ]
    with_margin = evaluate(
        matches,
        {"margin_weight_factor": 1.0},
        tau=0.5,
        initial_rd=350.0,
        warmup=0,
        drift_weight=1.0,
    )
    without_margin = evaluate(
        matches, {}, tau=0.5, initial_rd=350.0, warmup=0, drift_weight=1.0
    )
    # Same matches, different information weight → different prediction error.
    assert with_margin.brier != without_margin.brier
