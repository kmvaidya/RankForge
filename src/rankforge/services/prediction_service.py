# src/rankforge/services/prediction_service.py

"""Match prediction and rating calibration from the engine's own math.

Predictions use the Glicko-2 expected-score function E() — the exact
quantity the rating updates optimize — rather than a separate model, so
the calibration report below measures the engine against its own claims.
(The offline pickleball study that shaped this design found a full ML
layer on top of a tuned rating system improved Brier by only ~1.4%;
the professional move is a well-evaluated closed form, not a model.)

``walk_forward_calibration`` replays a game's history in memory with the
strict predict-before-update protocol: each match is scored using only
ratings as they stood beforehand, then applied with full config fidelity
(tau, weights, margin multiplier, min swing, season boundaries). Nothing
is written to the database.
"""

from __future__ import annotations

import itertools
import logging
import math
from statistics import fmean

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from rankforge.db import models
from rankforge.db.models import DEFAULT_RATING_INFO
from rankforge.exceptions import GameNotFoundError, PlayerNotFoundError
from rankforge.rating.glicko2_engine import (
    Glicko2Engine,
    Glicko2Rating,
    _apply_min_swing,
    _calculate_player_scores,
    _margin_multiplier,
    _match_weight,
    _min_swing,
    _tau,
)
from rankforge.schemas import prediction as prediction_schema
from rankforge.services import season_service

logger = logging.getLogger(__name__)

GLICKO_SCALE = 173.7178
LOPSIDED_THRESHOLD = 0.8
# Players need this many replayed appearances before they count toward the
# rating-vs-results Spearman check (young ratings are still converging).
SPEARMAN_MIN_APPEARANCES = 10


def _expected_one(
    engine: Glicko2Engine, mine: Glicko2Rating, other: Glicko2Rating
) -> float:
    """Glicko-2 expected score of ``mine`` against ``other``."""
    return engine._E(
        (mine.mu - 1500) / GLICKO_SCALE,
        (other.mu - 1500) / GLICKO_SCALE,
        other.phi / GLICKO_SCALE,
    )


def _team_expected_scores(
    engine: Glicko2Engine,
    ratings: dict[int, Glicko2Rating],
    teams: list[list[int]],
) -> list[float]:
    """Each team's mean member expected score against all opponents."""
    scores = []
    for index, team in enumerate(teams):
        opponents = [
            pid for other, ids in enumerate(teams) if other != index for pid in ids
        ]
        scores.append(
            fmean(
                fmean(
                    _expected_one(engine, ratings[pid], ratings[opp])
                    for opp in opponents
                )
                for pid in team
            )
        )
    return scores


async def predict_teams(
    db: AsyncSession, game_id: int, teams: list[list[int]]
) -> prediction_schema.PredictionResponse:
    """Win probabilities for a hypothetical team split.

    Players without a profile in this game are treated as fresh (default
    rating), matching matchmaking behavior.

    Raises:
        GameNotFoundError: If the game doesn't exist
        PlayerNotFoundError: If any player doesn't exist
    """
    game = await db.get(models.Game, game_id)
    if game is None or game.deleted_at is not None:
        raise GameNotFoundError(game_id)

    player_ids = [pid for team in teams for pid in team]
    result = await db.execute(
        select(models.Player).where(models.Player.id.in_(player_ids))
    )
    players = {p.id: p for p in result.scalars().all()}
    for pid in player_ids:
        player = players.get(pid)
        if player is None or player.deleted_at is not None:
            raise PlayerNotFoundError(pid)

    profile_result = await db.execute(
        select(models.GameProfile).where(
            models.GameProfile.game_id == game_id,
            models.GameProfile.player_id.in_(player_ids),
            models.GameProfile.deleted_at.is_(None),
        )
    )
    profiles = {p.player_id: p for p in profile_result.scalars().all()}

    ratings: dict[int, Glicko2Rating] = {}
    for pid in player_ids:
        profile = profiles.get(pid)
        info = profile.rating_info if profile else dict(DEFAULT_RATING_INFO)
        ratings[pid] = Glicko2Rating(
            mu=float(info["rating"]),
            phi=float(info["rd"]),
            sigma=float(info.get("vol", 0.06)),
        )

    engine = Glicko2Engine(tau=_tau(game))
    expected = _team_expected_scores(engine, ratings, teams)
    total = sum(expected)
    probabilities = [score / total for score in expected]
    favored = max(range(len(teams)), key=lambda i: probabilities[i])

    return prediction_schema.PredictionResponse(
        game_id=game_id,
        teams=[
            prediction_schema.TeamPrediction(
                player_ids=team,
                rating=round(sum(ratings[pid].mu for pid in team), 2),
                rd=round(math.sqrt(sum(ratings[pid].phi ** 2 for pid in team)), 2),
                expected_score=round(expected[index], 4),
                win_probability=round(probabilities[index], 4),
            )
            for index, team in enumerate(teams)
        ],
        favored_team_index=favored,
        lopsided=probabilities[favored] >= LOPSIDED_THRESHOLD,
    )


def _pair_probability(
    engine: Glicko2Engine,
    ratings: dict[int, Glicko2Rating],
    members_a: list[int],
    members_b: list[int],
) -> float:
    """Normalized win probability of team a over team b in isolation."""
    e_a = fmean(
        fmean(_expected_one(engine, ratings[i], ratings[j]) for j in members_b)
        for i in members_a
    )
    e_b = fmean(
        fmean(_expected_one(engine, ratings[j], ratings[i]) for i in members_a)
        for j in members_b
    )
    return e_a / (e_a + e_b)


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    """Spearman rank correlation with average ranks for ties."""
    n = len(xs)
    if n < 3:
        return None

    def ranks(values: list[float]) -> list[float]:
        order = sorted(range(n), key=lambda i: values[i])
        ranked = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and values[order[j + 1]] == values[order[i]]:
                j += 1
            average = (i + j) / 2 + 1
            for k in range(i, j + 1):
                ranked[order[k]] = average
            i = j + 1
        return ranked

    rx, ry = ranks(xs), ranks(ys)
    mean_x, mean_y = fmean(rx), fmean(ry)
    numerator = sum((a - mean_x) * (b - mean_y) for a, b in zip(rx, ry))
    dx = math.sqrt(sum((a - mean_x) ** 2 for a in rx))
    dy = math.sqrt(sum((b - mean_y) ** 2 for b in ry))
    if dx == 0 or dy == 0:
        return None
    return numerator / (dx * dy)


async def walk_forward_calibration(
    db: AsyncSession, game_id: int, warmup: int = 5
) -> prediction_schema.CalibrationReport:
    """Score the rating engine's predictions over a game's real history.

    For every pair of teams in every match, records the pre-match predicted
    probability against what actually happened (1 / 0.5 / 0), skipping pairs
    involving any player with fewer than ``warmup`` prior appearances. The
    replay honors the game's full rating_config and season boundaries, so
    the evaluated ratings are exactly the ones the app would have shown.

    Raises:
        GameNotFoundError: If the game doesn't exist
    """
    game = await db.get(models.Game, game_id)
    if game is None or game.deleted_at is not None:
        raise GameNotFoundError(game_id)

    match_result = await db.execute(
        select(models.Match)
        .where(
            models.Match.game_id == game_id,
            models.Match.deleted_at.is_(None),
        )
        .order_by(models.Match.played_at, models.Match.id)
        .options(selectinload(models.Match.participants))
    )
    matches = list(match_result.scalars().all())
    boundaries = await season_service.list_seasons(db, game_id)

    engine = Glicko2Engine(tau=_tau(game))
    min_swing = _min_swing(game)
    rd_reset = season_service.season_rd_reset(game)
    default = DEFAULT_RATING_INFO

    ratings: dict[int, Glicko2Rating] = {}
    appearances: dict[int, int] = {}
    score_totals: dict[int, float] = {}
    predictions: list[tuple[float, float]] = []
    boundary_index = 0

    for match in matches:
        # Season boundaries fire before the first match at/after them,
        # mirroring the recalculation cascade.
        while (
            boundary_index < len(boundaries)
            and boundaries[boundary_index].started_at <= match.played_at
        ):
            for rating in ratings.values():
                rating.phi = rd_reset
            boundary_index += 1

        scores = _calculate_player_scores(match)
        weight = _match_weight(match) * _margin_multiplier(match, game)

        for participant in match.participants:
            ratings.setdefault(
                participant.player_id,
                Glicko2Rating(
                    float(default["rating"]),
                    float(default["rd"]),
                    float(default["vol"]),
                ),
            )

        members: dict[int, list[int]] = {}
        team_score: dict[int, float] = {}
        for participant in match.participants:
            members.setdefault(participant.team_id, []).append(participant.player_id)
            team_score[participant.team_id] = scores[participant.player_id]

        for team_a, team_b in itertools.combinations(sorted(members), 2):
            pair_players = members[team_a] + members[team_b]
            if any(appearances.get(pid, 0) < warmup for pid in pair_players):
                continue
            predicted = _pair_probability(
                engine, ratings, members[team_a], members[team_b]
            )
            if team_score[team_a] > team_score[team_b]:
                actual = 1.0
            elif team_score[team_a] < team_score[team_b]:
                actual = 0.0
            else:
                actual = 0.5
            predictions.append((predicted, actual))

        new_ratings: dict[int, Glicko2Rating] = {}
        for me in match.participants:
            mine = ratings[me.player_id]
            opponents = [
                (ratings[other.player_id], scores[me.player_id])
                for other in match.participants
                if other.team_id != me.team_id
            ]
            rated = engine.rate(mine, opponents, weight)
            new_ratings[me.player_id] = _apply_min_swing(
                mine, rated, scores[me.player_id], min_swing
            )
        ratings.update(new_ratings)
        for participant in match.participants:
            appearances[participant.player_id] = (
                appearances.get(participant.player_id, 0) + 1
            )
            score_totals[participant.player_id] = (
                score_totals.get(participant.player_id, 0.0)
                + scores[participant.player_id]
            )

    brier = accuracy = ece = None
    bins: list[prediction_schema.CalibrationBin] = []
    if predictions:
        brier = round(fmean((p - s) ** 2 for p, s in predictions), 4)
        decisive = [(p, s) for p, s in predictions if s != 0.5]
        if decisive:
            accuracy = round(
                fmean(1.0 if (p > 0.5) == (s == 1.0) else 0.0 for p, s in decisive), 4
            )

        binned: list[list[tuple[float, float]]] = [[] for _ in range(10)]
        for p, s in predictions:
            binned[min(int(p * 10), 9)].append((p, s))
        weighted_gap = 0.0
        for index, contents in enumerate(binned):
            lower, upper = index / 10, (index + 1) / 10
            if contents:
                mean_p = fmean(p for p, _ in contents)
                rate = fmean(s for _, s in contents)
                weighted_gap += len(contents) / len(predictions) * abs(mean_p - rate)
                bins.append(
                    prediction_schema.CalibrationBin(
                        lower=lower,
                        upper=upper,
                        count=len(contents),
                        mean_predicted=round(mean_p, 4),
                        actual_rate=round(rate, 4),
                    )
                )
            else:
                bins.append(
                    prediction_schema.CalibrationBin(lower=lower, upper=upper, count=0)
                )
        ece = round(weighted_gap, 4)

    established = [
        pid for pid, count in appearances.items() if count >= SPEARMAN_MIN_APPEARANCES
    ]
    spearman = _spearman(
        [ratings[pid].mu for pid in established],
        [score_totals[pid] / appearances[pid] for pid in established],
    )

    logger.info(
        "Calibration computed",
        extra={
            "game_id": game_id,
            "matches": len(matches),
            "comparisons": len(predictions),
            "brier": brier,
        },
    )

    return prediction_schema.CalibrationReport(
        game_id=game_id,
        matches_replayed=len(matches),
        comparisons_evaluated=len(predictions),
        warmup=warmup,
        brier=brier,
        accuracy=accuracy,
        ece=ece,
        bins=bins,
        rating_winrate_spearman=round(spearman, 4) if spearman is not None else None,
        spearman_players=len(established),
    )
