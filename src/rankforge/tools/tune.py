# src/rankforge/tools/tune.py

"""Tune Glicko-2 parameters against a game's real match history.

Replays every non-deleted match of a game entirely in memory across a grid
of (tau, initial RD) values, scoring each combination by:

* **Brier score** — mean squared error between each player's pre-match
  expected score (vs. the opponents they actually faced) and their actual
  normalized result. Lower = the ratings predicted outcomes better. The
  first few appearances of each player are skipped as warm-up.
* **Drift** — |1500 − mean final rating|, the inflation/deflation of the
  pool. Lower = healthier.

The composite objective is ``brier + drift_weight * drift / 1000``.

The database is only read (matches + participants); nothing is written.
Apply a winning tau via the API: ``PUT /games/{id}`` with
``{"rating_config": {"tau": <value>}}``, then POST /games/{id}/recalculate.
A winning initial RD is reported for reference — profile seeding currently
uses the global default (see models.DEFAULT_RATING_INFO).

Usage:
    python -m rankforge.tools.tune --game-id 6
    python -m rankforge.tools.tune --game-id 6 --warmup 10 --drift-weight 2
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Sequence, cast

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from rankforge.db import models
from rankforge.rating.glicko2_engine import (
    Glicko2Engine,
    Glicko2Rating,
    _calculate_player_scores,
    _grow_rd,
    _margin_multiplier,
    _match_weight,
    _rd_growth_period_days,
)

TAU_GRID = [0.3, 0.5, 0.75, 1.0, 1.2]
RD_GRID = [200.0, 250.0, 300.0, 350.0]


@dataclass
class ReplayParticipant:
    """Plain participant snapshot (mirrors the fields the engine reads)."""

    player_id: int
    team_id: int
    outcome: dict


@dataclass
class ReplayMatch:
    """Plain match snapshot for in-memory replay."""

    id: int
    match_metadata: dict
    played_at: datetime | None = None
    participants: list[ReplayParticipant] = field(default_factory=list)


@dataclass
class TuneResult:
    tau: float
    initial_rd: float
    brier: float
    drift: float
    composite: float


async def load_history(game_id: int) -> tuple[list[ReplayMatch], dict]:
    """Read a game's matches (chronological) and rating_config; close cleanly."""
    # Imported here so --help works without a configured DATABASE_URL.
    from rankforge.db.session import AsyncSessionLocal, engine

    async with AsyncSessionLocal() as session:
        game = await session.get(models.Game, game_id)
        if game is None or game.deleted_at is not None:
            raise SystemExit(f"Game {game_id} not found")
        config = dict(game.rating_config or {})
        result = await session.execute(
            select(models.Match)
            .where(
                models.Match.game_id == game_id,
                models.Match.deleted_at.is_(None),
            )
            .order_by(models.Match.played_at, models.Match.id)
            .options(selectinload(models.Match.participants))
        )
        matches = [
            ReplayMatch(
                id=m.id,
                match_metadata=dict(m.match_metadata or {}),
                played_at=m.played_at,
                participants=[
                    ReplayParticipant(p.player_id, p.team_id, dict(p.outcome))
                    for p in m.participants
                ],
            )
            for m in result.scalars().all()
        ]
    await engine.dispose()
    return matches, config


def evaluate(
    matches: Sequence[ReplayMatch],
    rating_config: dict,
    tau: float,
    initial_rd: float,
    warmup: int,
    drift_weight: float,
) -> TuneResult:
    """Replay all matches with the given parameters and score the outcome."""
    engine = Glicko2Engine(tau=tau)
    ratings: dict[int, Glicko2Rating] = {}
    appearances: dict[int, int] = {}
    last_played: dict[int, datetime] = {}
    squared_errors: list[float] = []

    fake_game = cast(models.Game, _ConfigCarrier(rating_config))
    growth_period = _rd_growth_period_days(fake_game)

    for match in matches:
        model_match = cast(models.Match, match)
        scores = _calculate_player_scores(model_match)
        weight = _match_weight(model_match) * _margin_multiplier(model_match, fake_game)

        for participant in match.participants:
            ratings.setdefault(
                participant.player_id, Glicko2Rating(1500.0, initial_rd, 0.06)
            )
            # Mirror the engine's inactivity growth (config-gated).
            previous = last_played.get(participant.player_id)
            if growth_period > 0 and previous is not None and match.played_at:
                elapsed = (match.played_at - previous).total_seconds() / 86400.0
                ratings[participant.player_id] = _grow_rd(
                    ratings[participant.player_id], elapsed, growth_period
                )

        new_ratings: dict[int, Glicko2Rating] = {}
        for me in match.participants:
            mine = ratings[me.player_id]
            opponents = [
                (ratings[other.player_id], scores[me.player_id])
                for other in match.participants
                if other.team_id != me.team_id
            ]
            if opponents and appearances.get(me.player_id, 0) >= warmup:
                expected = sum(
                    engine._E(
                        (mine.mu - 1500) / 173.7178,
                        (opp.mu - 1500) / 173.7178,
                        opp.phi / 173.7178,
                    )
                    for opp, _ in opponents
                ) / len(opponents)
                squared_errors.append((scores[me.player_id] - expected) ** 2)
            new_ratings[me.player_id] = engine.rate(mine, opponents, weight)

        ratings.update(new_ratings)
        for participant in match.participants:
            appearances[participant.player_id] = (
                appearances.get(participant.player_id, 0) + 1
            )
            if match.played_at:
                last_played[participant.player_id] = match.played_at

    brier = (
        sum(squared_errors) / len(squared_errors) if squared_errors else float("nan")
    )
    mean_rating = (
        sum(r.mu for r in ratings.values()) / len(ratings) if ratings else 1500.0
    )
    drift = abs(1500.0 - mean_rating)
    return TuneResult(
        tau=tau,
        initial_rd=initial_rd,
        brier=brier,
        drift=drift,
        composite=brier + drift_weight * drift / 1000.0,
    )


class _ConfigCarrier:
    """Duck-typed stand-in for Game inside _margin_multiplier."""

    def __init__(self, rating_config: dict) -> None:
        self.rating_config = rating_config


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--game-id", type=int, required=True)
    parser.add_argument(
        "--warmup",
        type=int,
        default=5,
        help="Skip each player's first N appearances when scoring (default 5)",
    )
    parser.add_argument(
        "--drift-weight",
        type=float,
        default=1.0,
        help="Weight of rating drift in the composite objective (default 1.0)",
    )
    args = parser.parse_args(argv)

    matches, rating_config = asyncio.run(load_history(args.game_id))
    if not matches:
        raise SystemExit("No matches to tune against")
    print(f"Replaying {len(matches)} matches per combination…\n")

    results = []
    for tau in TAU_GRID:
        for rd in RD_GRID:
            try:
                results.append(
                    evaluate(
                        matches, rating_config, tau, rd, args.warmup, args.drift_weight
                    )
                )
            except OverflowError:
                # Ratings diverged under these parameters — a decisive "no".
                results.append(
                    TuneResult(tau, rd, float("inf"), float("inf"), float("inf"))
                )
    results.sort(key=lambda r: r.composite)

    current_tau = rating_config.get("tau", 0.5)
    header = f"{'tau':>5} {'init RD':>8} {'brier':>8} {'drift':>8} {'objective':>10}"
    print(header)
    print("-" * len(header))
    for r in results:
        marker = ""
        if r.tau == current_tau and r.initial_rd == 350.0:
            marker = "  <- current"
        print(
            f"{r.tau:>5.2f} {r.initial_rd:>8.0f} {r.brier:>8.4f} "
            f"{r.drift:>8.1f} {r.composite:>10.4f}{marker}"
        )

    best = results[0]
    print(
        f"\nBest: tau={best.tau}, initial RD={best.initial_rd:.0f} "
        f"(brier {best.brier:.4f}, drift {best.drift:.1f})"
    )
    print(
        "Apply tau via the API: "
        f'PUT /games/{args.game_id} {{"rating_config": {{"tau": {best.tau}}}}} '
        f"then POST /games/{args.game_id}/recalculate"
    )
    if best.initial_rd != 350.0:
        print(
            "Note: initial RD is reported for reference; profile seeding "
            "currently uses the global default (350)."
        )


if __name__ == "__main__":
    main()
