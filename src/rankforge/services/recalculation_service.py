# src/rankforge/services/recalculation_service.py

"""Forward rating recalculation for historical match corrections.

When a historical match is updated or deleted, every subsequent rating in
that game becomes invalid. This implements full forward recalculation
(Approach 1 in MASTER_PLAN):

1. Capture, for each affected player, the rating they held *before* their
   first match in the affected window (``capture_reset_targets``).
2. Apply the correction (caller's responsibility — update fields, replace
   participants, or soft-delete the match).
3. Reset affected profiles and replay every non-deleted match in the window
   in chronological order (``replay_matches``).

Replay order is (played_at, id): chronological, with insertion order breaking
ties. This assumes matches were originally applied in chronological order;
after any recalculation the window's rating history is rewritten in that
order, healing prior inconsistencies.

Complexity is O(n) in matches after the correction point — acceptable at MVP
scale (<1000 matches per game). All work happens in the caller's transaction:
this module flushes but never commits, so a failure rolls back atomically.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from rankforge.db import models
from rankforge.db.models import DEFAULT_RATING_INFO
from rankforge.exceptions import GameNotFoundError
from rankforge.rating import get_rating_engine

logger = logging.getLogger(__name__)


@dataclass
class RecalculationStats:
    """Summary of a forward recalculation run."""

    matches_recalculated: int
    players_affected: int


def normalize_played_at(dt: datetime) -> datetime:
    """Normalize a datetime to naive UTC for safe comparison.

    played_at values can arrive timezone-aware (API clients sending "Z") or
    naive (defaults, historical imports). Mixed-form comparisons either raise
    (Python ordering) or misbehave (SQLite string comparison), so all cascade
    arithmetic uses naive UTC.
    """
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def cascade_start_for(*played_at_values: datetime) -> datetime:
    """Compute the cascade window start for a set of played_at values.

    Returns the earliest value minus a microsecond of slack. The slack keeps
    the boundary match inside the window regardless of whether its stored
    form is naive or timezone-aware (SQLite compares these as strings).
    """
    earliest = min(normalize_played_at(dt) for dt in played_at_values)
    return earliest - timedelta(microseconds=1)


async def _load_window_matches(
    db: AsyncSession, game_id: int, from_played_at: datetime
) -> list[models.Match]:
    """Load non-deleted matches in the window, in replay order, with participants."""
    result = await db.execute(
        select(models.Match)
        .where(
            models.Match.game_id == game_id,
            models.Match.deleted_at.is_(None),
            models.Match.played_at >= from_played_at,
        )
        .order_by(models.Match.played_at, models.Match.id)
        .options(selectinload(models.Match.participants))
    )
    return list(result.scalars().all())


async def capture_reset_targets(
    db: AsyncSession, game_id: int, from_played_at: datetime
) -> dict[int, dict]:
    """Map each player in the window to the rating they must be reset to.

    Must be called BEFORE the correction is applied, so the window still
    reflects the original participants. For each player, the reset value is
    the ``rating_info_before`` of their earliest window participation (in
    replay order), falling back to the default rating if it was never stored.
    """
    reset_targets: dict[int, dict] = {}
    for match in await _load_window_matches(db, game_id, from_played_at):
        for participant in match.participants:
            if participant.player_id not in reset_targets:
                reset_targets[participant.player_id] = dict(
                    participant.rating_info_before or DEFAULT_RATING_INFO
                )
    return reset_targets


async def _get_or_create_profile(
    db: AsyncSession, player_id: int, game_id: int
) -> models.GameProfile:
    """Fetch a profile, creating it with default rating if missing."""
    profile = await models.GameProfile.find_by_player_and_game(db, player_id, game_id)
    if profile is None:
        profile = models.GameProfile(
            player_id=player_id,
            game_id=game_id,
            rating_info=dict(DEFAULT_RATING_INFO),
            stats={},
        )
        db.add(profile)
        await db.flush()
    return profile


async def replay_matches(
    db: AsyncSession,
    game_id: int,
    from_played_at: datetime,
    reset_targets: dict[int, dict],
) -> RecalculationStats:
    """Reset affected profiles, then replay the window in chronological order.

    Rewrites each participant's ``rating_info_before`` / ``rating_info_change``
    and each affected profile's ``rating_info``. Flushes but does not commit —
    the caller owns the transaction boundary.
    """
    game = await db.get(models.Game, game_id)
    if game is None:
        raise GameNotFoundError(game_id)
    engine_fn = get_rating_engine(game.rating_strategy)

    # 1. Reset every affected profile to its pre-window rating.
    for player_id, rating_info in reset_targets.items():
        profile = await _get_or_create_profile(db, player_id, game_id)
        profile.rating_info = dict(rating_info)
        db.add(profile)
    await db.flush()

    # 2. Replay the (possibly mutated) window in order.
    window = await _load_window_matches(db, game_id, from_played_at)
    for match in window:
        for participant in match.participants:
            profile = await _get_or_create_profile(db, participant.player_id, game_id)
            participant.rating_info_before = dict(profile.rating_info)
            db.add(participant)
        await engine_fn(db, match)

    await db.flush()

    stats = RecalculationStats(
        matches_recalculated=len(window),
        players_affected=len(reset_targets),
    )
    logger.info(
        "Forward recalculation complete",
        extra={
            "game_id": game_id,
            "matches_recalculated": stats.matches_recalculated,
            "players_affected": stats.players_affected,
        },
    )
    return stats
