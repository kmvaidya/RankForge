# src/rankforge/services/match_service.py

"""Business logic for match-related operations."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from rankforge.db import models
from rankforge.db.models import DEFAULT_RATING_INFO
from rankforge.exceptions import (
    ConcurrentModificationError,
    DuplicatePlayerError,
    GameNotFoundError,
    InsufficientParticipantsError,
    InsufficientTeamsError,
    MatchNotFoundError,
    MatchTooOldToUpdateError,
    PlayerNotFoundError,
)
from rankforge.rating import get_rating_engine
from rankforge.schemas import match as match_schema
from rankforge.services import recalculation_service, stats_service
from rankforge.services.recalculation_service import (
    RecalculationStats,
    cascade_start_for,
    normalize_played_at,
)

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_RATING_INFO",
    "get_or_create_game_profile",
    "process_new_match",
    "update_match",
    "soft_delete_match",
]

# The canonical name for the shared unknown player
UNKNOWN_PLAYER_NAME = "Unknown"


async def get_or_create_game_profile(
    db: AsyncSession, player_id: int, game_id: int
) -> models.GameProfile:
    """
    Retrieves a player's game profile, creating it with default
    values if it doesn't exist.
    """
    # Attempt to fetch an existing profile.
    query = select(models.GameProfile).where(
        models.GameProfile.player_id == player_id,
        models.GameProfile.game_id == game_id,
    )
    result = await db.execute(query)
    profile = result.scalar_one_or_none()

    # If no profile exists, create a new one.
    if profile is None:
        profile = models.GameProfile(
            player_id=player_id,
            game_id=game_id,
            rating_info=dict(DEFAULT_RATING_INFO),
            stats={},  # Start with empty stats
        )
        db.add(profile)
        # NOTE: We don't commit here; the main function will handle the commit.
        # We need to flush to get the profile object ready for use.
        await db.flush()
        logger.debug(
            "Created new GameProfile",
            extra={"player_id": player_id, "game_id": game_id},
        )
    return profile


async def _get_or_create_unknown_player(db: AsyncSession) -> models.Player:
    """
    Get or create the shared 'Unknown' player.

    This player is used for all unknown/anonymous participants in matches,
    avoiding database bloat from creating many one-time players.

    Returns:
        The shared Unknown player instance.
    """
    query = select(models.Player).where(models.Player.name == UNKNOWN_PLAYER_NAME)
    result = await db.execute(query)
    unknown_player = result.scalar_one_or_none()

    if unknown_player is None:
        unknown_player = models.Player(name=UNKNOWN_PLAYER_NAME)
        unknown_player.is_anonymous = True
        db.add(unknown_player)
        await db.flush()
        logger.info(
            "Created shared Unknown player",
            extra={"player_id": unknown_player.id},
        )

    return unknown_player


async def _resolve_unknown_players(
    db: AsyncSession,
    participants: list[match_schema.MatchParticipantCreate],
) -> None:
    """
    Resolve participants with player_id=None to the shared 'Unknown' player.

    Modifies the participant objects in place to set their player_id
    to the shared Unknown player.
    """
    # Check if any participants need the Unknown player
    needs_unknown = any(p.player_id is None for p in participants)
    if not needs_unknown:
        return

    # Get or create the shared Unknown player once
    unknown_player = await _get_or_create_unknown_player(db)

    for participant in participants:
        if participant.player_id is None:
            # Update the participant with the Unknown player's ID
            # Pydantic models are immutable, so we use object.__setattr__
            object.__setattr__(participant, "player_id", unknown_player.id)
            logger.debug(
                "Assigned Unknown player to participant",
                extra={"player_id": unknown_player.id, "team_id": participant.team_id},
            )


async def _validate_participants(
    db: AsyncSession,
    participants: list[match_schema.MatchParticipantCreate],
    unknown_player_id: int | None = None,
) -> None:
    """
    Validates participant data before match processing.

    This validation runs AFTER unknown players are resolved, so all
    participants should have valid player_ids at this point.

    Args:
        db: Database session
        participants: List of participant data
        unknown_player_id: ID of the shared Unknown player (exempt from duplicate check)

    Raises:
        InsufficientParticipantsError: If fewer than 2 participants
        DuplicatePlayerError: If any non-Unknown player_id appears multiple times
        InsufficientTeamsError: If fewer than 2 distinct teams
        PlayerNotFoundError: If any player_id does not exist
    """
    # Check minimum participants
    if len(participants) < 2:
        raise InsufficientParticipantsError(len(participants))

    # Get all player IDs (should all be set after unknown player resolution)
    player_ids = [p.player_id for p in participants]

    # Check for duplicate players (Unknown player is exempt - can appear multiple times)
    seen: set[int] = set()
    duplicates: list[int] = []
    for pid in player_ids:
        if pid is not None and pid != unknown_player_id:
            if pid in seen:
                duplicates.append(pid)
            seen.add(pid)

    if duplicates:
        raise DuplicatePlayerError(list(set(duplicates)))

    # Check team structure (at least 2 teams)
    team_ids = {p.team_id for p in participants}
    if len(team_ids) < 2:
        raise InsufficientTeamsError(len(team_ids))

    # Validate all players exist (single query for efficiency)
    non_null_ids = [pid for pid in player_ids if pid is not None]
    if non_null_ids:
        query = select(models.Player.id).where(models.Player.id.in_(non_null_ids))
        result = await db.execute(query)
        existing_ids = set(result.scalars().all())

        missing_ids = set(non_null_ids) - existing_ids
        if missing_ids:
            # Raise for the first missing player (consistent behavior)
            raise PlayerNotFoundError(min(missing_ids))

    logger.debug("Participant validation passed")


async def process_new_match(
    db: AsyncSession, match_in: match_schema.MatchCreate
) -> models.Match:
    """
    Processes the creation of a new match.

    This service is responsible for:
    1. Creating anonymous players for participants with player_id=None
    2. Validating participant data (min 2, no duplicates, 2+ teams)
    3. Creating the Match and MatchParticipant records in the database
    4. Triggering the rating calculation process
    5. Updating player profiles with new ratings and stats

    All operations are performed within a single transaction. If any step
    fails, the entire transaction is rolled back to maintain data consistency.

    Raises:
        GameNotFoundError: If the game_id doesn't exist
        InsufficientParticipantsError: If fewer than 2 participants
        DuplicatePlayerError: If same player appears multiple times
        InsufficientTeamsError: If fewer than 2 teams
        PlayerNotFoundError: If a player_id doesn't exist
    """
    logger.info(
        "Processing new match",
        extra={
            "game_id": match_in.game_id,
            "participant_count": len(match_in.participants),
        },
    )

    try:
        # 1. Fetch the game and determine the rating strategy
        game = await db.get(models.Game, match_in.game_id)
        if not game:
            raise GameNotFoundError(match_in.game_id)

        logger.debug(
            "Game found",
            extra={"game_id": game.id, "rating_strategy": game.rating_strategy},
        )

        # 2. Resolve participants with player_id=None to the shared Unknown player
        await _resolve_unknown_players(db, match_in.participants)

        # 3. Get the Unknown player ID for validation (if it exists)
        #    The Unknown player is exempt from duplicate checking
        query = select(models.Player.id).where(
            models.Player.name == UNKNOWN_PLAYER_NAME
        )
        result = await db.execute(query)
        unknown_player_id = result.scalar_one_or_none()

        # 4. Validate participants AFTER unknown player resolution
        await _validate_participants(db, match_in.participants, unknown_player_id)

        # 5. Create the database models from the input schema.
        #    Exclude 'participants' as it's a list of schemas, not a direct field.
        #    Exclude 'played_at' if None to let the model use its default (now).
        match_data = match_in.model_dump(exclude={"participants"}, exclude_none=True)
        new_match = models.Match(**match_data)

        # 5. Ensure profiles exist and create participant records.
        profiles_by_participant: list[
            tuple[models.GameProfile, models.MatchParticipant]
        ] = []
        for participant_data in match_in.participants:
            # At this point, player_id is guaranteed to be set (either from input
            # or from anonymous player creation)
            assert participant_data.player_id is not None

            profile = await get_or_create_game_profile(
                db, player_id=participant_data.player_id, game_id=match_in.game_id
            )

            # Store the "before" rating for historical tracking
            participant_with_history = participant_data.model_dump()
            participant_with_history["rating_info_before"] = profile.rating_info

            new_participant = models.MatchParticipant(**participant_with_history)
            new_match.participants.append(new_participant)
            profiles_by_participant.append((profile, new_participant))

        # 6. Add the new match and flush to get IDs (NO COMMIT YET)
        db.add(new_match)
        await db.flush()
        await db.refresh(new_match, attribute_names=["participants"])

        # 7. DISPATCHER: Trigger the correct rating update process.
        #    Rating engines use flush(), not commit(), to allow atomic transactions.
        logger.info(
            "Dispatching to rating engine",
            extra={"match_id": new_match.id, "strategy": game.rating_strategy},
        )

        engine_fn = get_rating_engine(game.rating_strategy)
        await engine_fn(db, new_match)

        # 7b. Update win/loss/draw stats (service-owned; engines only touch
        #     rating_info)
        for profile, participant in profiles_by_participant:
            stats_service.apply_match_stats(profile, participant.outcome)
            db.add(profile)

        # 8. COMMIT the entire transaction atomically (match + ratings together)
        await db.commit()
        logger.info("Match processed successfully", extra={"match_id": new_match.id})

        # 9. Re-query the match to eager load all relationships for the response.
        match_result = await db.execute(
            select(models.Match)
            .where(models.Match.id == new_match.id)
            .options(
                selectinload(models.Match.participants).selectinload(
                    models.MatchParticipant.player
                )
            )
        )
        created_match = match_result.scalar_one()

        return created_match

    except Exception as e:
        logger.error(
            "Failed to process match",
            extra={"game_id": match_in.game_id, "error": str(e)},
            exc_info=True,
        )
        await db.rollback()
        raise


# =============================================================================
# Match Correction (Update / Delete with Rating Cascade)
# =============================================================================


def _get_max_update_age_days() -> int:
    """Read the update-age threshold from the environment. 0 disables it.

    Defaults to 0 (unlimited) because RankForge's primary data source is
    historical imports; set MATCH_UPDATE_MAX_AGE_DAYS to enforce immutability
    of older matches.
    """
    try:
        return int(os.getenv("MATCH_UPDATE_MAX_AGE_DAYS", "0"))
    except ValueError:
        return 0


def _check_update_age(match: models.Match) -> None:
    """Raise MatchTooOldToUpdateError if the match exceeds the age threshold."""
    max_age_days = _get_max_update_age_days()
    if max_age_days <= 0:
        return

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    age_days = (now - normalize_played_at(match.played_at)).days
    if age_days > max_age_days:
        raise MatchTooOldToUpdateError(match.id, age_days, max_age_days)


async def _load_match_for_correction(db: AsyncSession, match_id: int) -> models.Match:
    """Load a live (non-deleted) match with participants, or raise 404."""
    result = await db.execute(
        select(models.Match)
        .where(models.Match.id == match_id)
        .options(selectinload(models.Match.participants))
    )
    match = result.scalar_one_or_none()
    if match is None or match.deleted_at is not None:
        raise MatchNotFoundError(match_id)
    return match


async def update_match(
    db: AsyncSession,
    match_id: int,
    update: match_schema.MatchUpdate,
) -> tuple[models.Match, RecalculationStats | None]:
    """
    Correct a historical match and recalculate all affected ratings.

    Uses optimistic locking (update.expected_version must match the match's
    current version). Changing played_at or participants triggers a forward
    recalculation of every subsequent match in the game; metadata-only
    updates skip recalculation.

    The whole operation (mutation plus recalculation) is one transaction:
    any failure rolls back everything.

    Returns:
        (updated match with relationships loaded, recalculation stats or
        None if ratings were unaffected)

    Raises:
        MatchNotFoundError: If the match doesn't exist or is deleted
        ConcurrentModificationError: If expected_version doesn't match
        MatchTooOldToUpdateError: If beyond MATCH_UPDATE_MAX_AGE_DAYS
        ParticipantValidationError subclasses: If new participants invalid
    """
    try:
        match = await _load_match_for_correction(db, match_id)

        # Optimistic locking check
        if update.expected_version != match.version:
            raise ConcurrentModificationError(update.expected_version, match.version)

        _check_update_age(match)

        old_played_at = match.played_at
        new_played_at = (
            update.played_at if update.played_at is not None else old_played_at
        )
        played_at_changed = normalize_played_at(new_played_at) != normalize_played_at(
            old_played_at
        )
        participants_changed = update.participants is not None
        needs_recalc = participants_changed or played_at_changed

        logger.info(
            "Updating match",
            extra={
                "match_id": match_id,
                "participants_changed": participants_changed,
                "played_at_changed": played_at_changed,
            },
        )

        # Capture reset targets BEFORE mutating, while the window still
        # reflects the original participants of this match.
        reset_targets: dict[int, dict] = {}
        cascade_start = None
        if needs_recalc:
            cascade_start = cascade_start_for(old_played_at, new_played_at)
            reset_targets = await recalculation_service.capture_reset_targets(
                db, match.game_id, cascade_start
            )

        # Validate replacement participants (after resolving unknowns)
        if update.participants is not None:
            await _resolve_unknown_players(db, update.participants)
            unknown_result = await db.execute(
                select(models.Player.id).where(
                    models.Player.name == UNKNOWN_PLAYER_NAME
                )
            )
            unknown_player_id = unknown_result.scalar_one_or_none()
            await _validate_participants(db, update.participants, unknown_player_id)

        # Apply the mutation
        if update.played_at is not None:
            match.played_at = update.played_at
        if update.match_metadata is not None:
            match.match_metadata = update.match_metadata
        if update.participants is not None:
            # Full replacement: delete-orphan cascade removes the old rows.
            match.participants.clear()
            await db.flush()
            for participant_data in update.participants:
                assert participant_data.player_id is not None
                # Ensure a profile exists so replay can rate this player.
                await get_or_create_game_profile(
                    db,
                    player_id=participant_data.player_id,
                    game_id=match.game_id,
                )
                match.participants.append(
                    models.MatchParticipant(**participant_data.model_dump())
                )

        match.version += 1
        db.add(match)
        await db.flush()

        # Recalculate ratings forward from the cascade point
        recalc_stats: RecalculationStats | None = None
        if needs_recalc:
            assert cascade_start is not None
            recalc_stats = await recalculation_service.replay_matches(
                db, match.game_id, cascade_start, reset_targets
            )

        await db.commit()
        logger.info(
            "Match updated",
            extra={
                "match_id": match_id,
                "recalculated": (
                    recalc_stats.matches_recalculated if recalc_stats else 0
                ),
            },
        )

        # Re-query with relationships eagerly loaded for the response
        result = await db.execute(
            select(models.Match)
            .where(models.Match.id == match_id)
            .options(
                selectinload(models.Match.participants).selectinload(
                    models.MatchParticipant.player
                )
            )
        )
        return result.scalar_one(), recalc_stats

    except Exception as e:
        logger.error(
            "Failed to update match",
            extra={"match_id": match_id, "error": str(e)},
            exc_info=True,
        )
        await db.rollback()
        raise


async def soft_delete_match(db: AsyncSession, match_id: int) -> RecalculationStats:
    """
    Soft-delete a match and recalculate all affected ratings.

    The match is marked deleted (preserving history) and every subsequent
    match in the game is replayed as if the deleted match never happened.
    Atomic: mutation and recalculation share one transaction.

    Raises:
        MatchNotFoundError: If the match doesn't exist or is already deleted
    """
    try:
        match = await _load_match_for_correction(db, match_id)

        cascade_start = cascade_start_for(match.played_at)

        # Capture BEFORE deleting so the deleted match's own participants
        # are reset to their pre-match ratings.
        reset_targets = await recalculation_service.capture_reset_targets(
            db, match.game_id, cascade_start
        )

        match.deleted_at = datetime.now(timezone.utc)
        match.version += 1
        db.add(match)
        await db.flush()

        recalc_stats = await recalculation_service.replay_matches(
            db, match.game_id, cascade_start, reset_targets
        )

        await db.commit()
        logger.info(
            "Match soft-deleted",
            extra={
                "match_id": match_id,
                "matches_recalculated": recalc_stats.matches_recalculated,
            },
        )
        return recalc_stats

    except Exception as e:
        logger.error(
            "Failed to delete match",
            extra={"match_id": match_id, "error": str(e)},
            exc_info=True,
        )
        await db.rollback()
        raise
