# src/rankforge/services/stats_service.py

"""Maintains GameProfile.stats (matches_played, wins, losses, draws, win_rate).

Stats are incremented as matches are recorded and rebuilt from scratch
whenever a correction cascade rewrites history. Rating engines never touch
stats — they own rating_info only.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from rankforge.db import models
from rankforge.schemas.player_stats import ChemistryEntry, PlayerChemistry

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


def _increment(counters: dict, result: str | None) -> dict:
    counters["matches_played"] = counters.get("matches_played", 0) + 1
    # Materialize all three counters so incremental updates and full
    # rebuilds produce identical dict shapes.
    for key in _RESULT_KEYS.values():
        counters.setdefault(key, 0)
    if result is not None:
        counters[_RESULT_KEYS[result]] += 1
    return _with_win_rate(counters)


def apply_match_stats(profile: models.GameProfile, outcome: dict) -> None:
    """Increment a profile's stats counters for one recorded participation.

    Maintains career counters (top level) and the current-season counters
    (``stats["season"]``, zeroed at each season boundary; equal to career
    inside season 1).
    """
    stats = dict(profile.stats or {})
    result = outcome_result(outcome)
    stats = _increment(stats, result)
    stats["season"] = _increment(dict(stats.get("season") or {}), result)
    profile.stats = stats


async def player_chemistry(
    db: AsyncSession, player_id: int, game_id: int
) -> PlayerChemistry:
    """Partner and head-to-head aggregates for a player in one game.

    For every non-deleted match the player took part in, teammates land in
    ``partners`` and opponents in ``rivals``; both count the *player's*
    result (so a partner's win_rate reads "how we fare together" and a
    rival's reads "my record against them"). Anonymous and soft-deleted
    players are skipped. Sorted by shared matches, then win rate.
    """
    result = await db.execute(
        select(models.MatchParticipant)
        .join(models.Match, models.MatchParticipant.match_id == models.Match.id)
        .where(
            models.Match.game_id == game_id,
            models.Match.deleted_at.is_(None),
        )
        .options(selectinload(models.MatchParticipant.player))
    )
    by_match: dict[int, list[models.MatchParticipant]] = defaultdict(list)
    for participant in result.scalars():
        by_match[participant.match_id].append(participant)

    partners: dict[int, dict] = {}
    rivals: dict[int, dict] = {}
    names: dict[int, str] = {}

    for participants in by_match.values():
        me = next((p for p in participants if p.player_id == player_id), None)
        if me is None:
            continue
        result_kind = outcome_result(me.outcome)
        for other in participants:
            if other.player_id == player_id:
                continue
            if other.player.is_anonymous or other.player.deleted_at is not None:
                continue
            names[other.player_id] = other.player.name
            bucket = partners if other.team_id == me.team_id else rivals
            entry = bucket.setdefault(
                other.player_id, {"matches": 0, "wins": 0, "losses": 0, "draws": 0}
            )
            entry["matches"] += 1
            if result_kind is not None:
                entry[_RESULT_KEYS[result_kind]] += 1

    def to_entries(bucket: dict[int, dict]) -> list[ChemistryEntry]:
        entries = [
            ChemistryEntry(
                player_id=pid,
                player_name=names[pid],
                win_rate=(
                    round(counts["wins"] / counts["matches"], 4)
                    if counts["matches"]
                    else 0.0
                ),
                **counts,
            )
            for pid, counts in bucket.items()
        ]
        entries.sort(key=lambda e: (-e.matches, -e.win_rate, e.player_name))
        return entries

    return PlayerChemistry(
        player_id=player_id,
        game_id=game_id,
        partners=to_entries(partners),
        rivals=to_entries(rivals),
    )


async def rebuild_stats(
    db: AsyncSession, game_id: int, player_ids: set[int] | list[int]
) -> None:
    """Recompute stats from scratch for the given players in a game.

    Aggregates every participation in non-deleted matches; used after a
    correction cascade, where increments would drift. Flushes but does not
    commit.
    """
    # Local import: season_service imports models only, but keep the stats
    # module import-light at module scope to avoid cycles.
    from rankforge.services import season_service

    ids = list(player_ids)
    if not ids:
        return

    boundary = await season_service.latest_boundary(db, game_id)
    season_start = boundary.started_at if boundary else None

    result = await db.execute(
        select(models.MatchParticipant, models.Match.played_at)
        .join(models.Match, models.MatchParticipant.match_id == models.Match.id)
        .where(
            models.Match.game_id == game_id,
            models.Match.deleted_at.is_(None),
            models.MatchParticipant.player_id.in_(ids),
        )
    )

    def fresh() -> dict:
        return {"matches_played": 0, "wins": 0, "losses": 0, "draws": 0}

    career: dict[int, dict] = {pid: fresh() for pid in ids}
    season: dict[int, dict] = {pid: fresh() for pid in ids}
    for participant, played_at in result.all():
        result_kind = outcome_result(participant.outcome)
        buckets = [career[participant.player_id]]
        if season_start is None or played_at >= season_start:
            buckets.append(season[participant.player_id])
        for stats in buckets:
            stats["matches_played"] += 1
            if result_kind is not None:
                stats[_RESULT_KEYS[result_kind]] += 1

    profile_result = await db.execute(
        select(models.GameProfile).where(
            models.GameProfile.game_id == game_id,
            models.GameProfile.player_id.in_(ids),
        )
    )
    profiles = {p.player_id: p for p in profile_result.scalars()}

    for player_id, stats in career.items():
        profile = profiles.get(player_id)
        if profile is None:
            continue
        # Merge over existing stats: the schema allows game-specific custom
        # keys (e.g. imported metrics) that a rebuild must not destroy.
        merged = dict(profile.stats or {})
        merged.update(stats)
        merged["season"] = _with_win_rate(season[player_id])
        profile.stats = _with_win_rate(merged)
        db.add(profile)

    await db.flush()
    logger.debug("Stats rebuilt", extra={"game_id": game_id, "player_count": len(ids)})
