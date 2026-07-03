# src/rankforge/services/stats_service.py

"""Maintains GameProfile.stats (matches_played, wins, losses, draws, win_rate).

Stats are incremented as matches are recorded and rebuilt from scratch
whenever a correction cascade rewrites history. Rating engines never touch
stats — they own rating_info only.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rankforge.db import models

logger = logging.getLogger(__name__)

_RESULT_KEYS = {"win": "wins", "loss": "losses", "draw": "draws"}


def outcome_result(outcome: dict) -> str | None:
    """Classify an outcome dict as win/loss/draw.

    Binary outcomes carry an explicit result; ranked outcomes count first
    place as a win and everything else as a loss. Returns None if the
    outcome carries neither form (shouldn't happen for validated matches).
    """
    result = outcome.get("result")
    if result in _RESULT_KEYS:
        return str(result)
    rank = outcome.get("rank")
    if isinstance(rank, int):
        return "win" if rank == 1 else "loss"
    return None


def _with_win_rate(stats: dict) -> dict:
    played = stats.get("matches_played", 0)
    stats["win_rate"] = round(stats.get("wins", 0) / played, 4) if played > 0 else 0.0
    return stats


def apply_match_stats(profile: models.GameProfile, outcome: dict) -> None:
    """Increment a profile's stats counters for one recorded participation."""
    stats = dict(profile.stats or {})
    stats["matches_played"] = stats.get("matches_played", 0) + 1
    result = outcome_result(outcome)
    if result is not None:
        key = _RESULT_KEYS[result]
        stats[key] = stats.get(key, 0) + 1
    profile.stats = _with_win_rate(stats)


async def rebuild_stats(
    db: AsyncSession, game_id: int, player_ids: set[int] | list[int]
) -> None:
    """Recompute stats from scratch for the given players in a game.

    Aggregates every participation in non-deleted matches; used after a
    correction cascade, where increments would drift. Flushes but does not
    commit.
    """
    ids = list(player_ids)
    if not ids:
        return

    result = await db.execute(
        select(models.MatchParticipant)
        .join(models.Match, models.MatchParticipant.match_id == models.Match.id)
        .where(
            models.Match.game_id == game_id,
            models.Match.deleted_at.is_(None),
            models.MatchParticipant.player_id.in_(ids),
        )
    )

    counters: dict[int, dict] = {
        pid: {"matches_played": 0, "wins": 0, "losses": 0, "draws": 0} for pid in ids
    }
    for participant in result.scalars():
        stats = counters[participant.player_id]
        stats["matches_played"] += 1
        result_kind = outcome_result(participant.outcome)
        if result_kind is not None:
            stats[_RESULT_KEYS[result_kind]] += 1

    profile_result = await db.execute(
        select(models.GameProfile).where(
            models.GameProfile.game_id == game_id,
            models.GameProfile.player_id.in_(ids),
        )
    )
    profiles = {p.player_id: p for p in profile_result.scalars()}

    for player_id, stats in counters.items():
        profile = profiles.get(player_id)
        if profile is None:
            continue
        # Merge over existing stats: the schema allows game-specific custom
        # keys (e.g. imported metrics) that a rebuild must not destroy.
        merged = dict(profile.stats or {})
        merged.update(stats)
        profile.stats = _with_win_rate(merged)
        db.add(profile)

    await db.flush()
    logger.debug("Stats rebuilt", extra={"game_id": game_id, "player_count": len(ids)})
