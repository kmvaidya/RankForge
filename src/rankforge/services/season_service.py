# src/rankforge/services/season_service.py

"""Season lifecycle: boundaries that re-open the ladder without erasing skill.

Starting a season resets every profile's RD to ``rating_config.
season_rd_reset`` (default 350 — full re-proving) while ratings and
volatility persist, and zeroes the per-season stats. The boundary is stored
as a timestamp so the recalculation cascade replays it deterministically
(see recalculation_service.replay_matches).
"""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from rankforge.db import models
from rankforge.exceptions import GameNotFoundError

logger = logging.getLogger(__name__)

DEFAULT_SEASON_RD_RESET = 350.0


def season_rd_reset(game: models.Game | None) -> float:
    """The RD value profiles are reset to at a season boundary."""
    raw = ((game.rating_config if game else None) or {}).get(
        "season_rd_reset", DEFAULT_SEASON_RD_RESET
    )
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or raw <= 0:
        return DEFAULT_SEASON_RD_RESET
    return float(raw)


def apply_season_reset(
    profiles: list[models.GameProfile] | list, rd_reset: float
) -> None:
    """Apply a boundary's effects to profiles: RD reset + season stats zeroed."""
    for profile in profiles:
        rating_info = dict(profile.rating_info or {})
        rating_info["rd"] = rd_reset
        profile.rating_info = rating_info
        stats = dict(profile.stats or {})
        stats["season"] = {
            "matches_played": 0,
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "win_rate": 0.0,
        }
        profile.stats = stats


async def current_season_number(db: AsyncSession, game_id: int) -> int:
    """The game's current season (1 if no boundary was ever created)."""
    result = await db.execute(
        select(func.max(models.Season.number)).where(models.Season.game_id == game_id)
    )
    return result.scalar_one() or 1


async def latest_boundary(db: AsyncSession, game_id: int) -> models.Season | None:
    """The most recent season boundary, or None inside season 1."""
    result = await db.execute(
        select(models.Season)
        .where(models.Season.game_id == game_id)
        .order_by(models.Season.number.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def list_seasons(db: AsyncSession, game_id: int) -> list[models.Season]:
    result = await db.execute(
        select(models.Season)
        .where(models.Season.game_id == game_id)
        .order_by(models.Season.number)
    )
    return list(result.scalars().all())


async def start_season(db: AsyncSession, game_id: int) -> models.Season:
    """Create the next season boundary and apply it to all live profiles.

    Commits on success, rolls back on failure.
    """
    game = await db.get(models.Game, game_id)
    if game is None or game.deleted_at is not None:
        raise GameNotFoundError(game_id)

    try:
        number = await current_season_number(db, game_id) + 1
        season = models.Season(
            game_id=game_id, number=number, started_at=models.utcnow_naive()
        )
        db.add(season)

        result = await db.execute(
            select(models.GameProfile).where(
                models.GameProfile.game_id == game_id,
                models.GameProfile.deleted_at.is_(None),
            )
        )
        profiles = list(result.scalars().all())
        apply_season_reset(profiles, season_rd_reset(game))
        for profile in profiles:
            db.add(profile)

        await db.commit()
        await db.refresh(season)
    except Exception:
        await db.rollback()
        raise

    logger.info(
        "Season started",
        extra={"game_id": game_id, "season": number, "profiles": len(profiles)},
    )
    return season
