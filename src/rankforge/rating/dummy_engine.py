# src/rankforge/rating/dummy_engine.py

"""A dummy rating engine for testing the service layer architecture."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rankforge.db import models
from rankforge.exceptions import GameProfileNotFoundError

logger = logging.getLogger(__name__)


async def update_ratings_for_match(db: AsyncSession, match: models.Match) -> None:
    """
    A placeholder rating update function.

    Serves as the fallback engine for unknown strategies and as a test double
    proving the service layer dispatches correctly. It verifies each
    participant's GameProfile exists but leaves rating_info unchanged.
    Win/loss stats are maintained by the service layer (stats_service),
    not by rating engines.

    Raises:
        GameProfileNotFoundError: If a participant's profile is missing
    """
    logger.debug(
        "Starting dummy rating update",
        extra={"match_id": match.id, "participant_count": len(match.participants)},
    )

    # Verify each participant has a profile (same contract as real engines).
    for participant in match.participants:
        query = select(models.GameProfile).where(
            models.GameProfile.player_id == participant.player_id,
            models.GameProfile.game_id == match.game_id,
        )
        result = await db.execute(query)
        profile = result.scalar_one_or_none()

        if not profile:
            raise GameProfileNotFoundError(participant.player_id, match.game_id)

    logger.debug("Dummy ratings updated", extra={"match_id": match.id})

    # Flush changes but don't commit - let the caller handle transaction boundaries
    await db.flush()
