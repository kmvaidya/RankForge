# src/rankforge/schemas/match.py

"""Pydantic schemas for the Match resource."""

from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from .common import RatingInfo
from .player import PlayerRead

# ===============================================
# == Outcome Schema Variants
# ===============================================


class BinaryOutcome(BaseModel):
    """Outcome for win/loss/draw matches.

    Examples:
        {"result": "win"}
        {"result": "loss", "score": 24150}
        {"result": "win", "is_tournament": true, "individual_performance": 0.8}
    """

    result: Literal["win", "loss", "draw"]

    # Allow extra fields for game-specific data (tournament flags, scores, etc.)
    model_config = ConfigDict(extra="allow")


class RankedOutcome(BaseModel):
    """Outcome for ranked/placement matches (FFA or team rankings).

    Examples:
        {"rank": 1}
        {"rank": 2, "points": 850, "was_serving": true}
    """

    rank: int = Field(..., ge=1, description="Placement (1 = first place)")

    # Allow extra fields for game-specific data
    model_config = ConfigDict(extra="allow")


# Union type that accepts either outcome format
# Pydantic will try BinaryOutcome first (has 'result'), then RankedOutcome (has 'rank')
Outcome = Annotated[Union[BinaryOutcome, RankedOutcome], Field()]


# ===============================================
# == Match Participant Schemas
# ===============================================


class MatchParticipantBase(BaseModel):
    """Shared properties for a match participant."""

    team_id: int = Field(..., ge=0, description="Team identifier (0+ for grouping)")

    # Outcome using typed variants (BinaryOutcome or RankedOutcome)
    outcome: Outcome


class MatchParticipantCreate(MatchParticipantBase):
    """Properties to receive when creating a participant within a match.

    The player_id can be:
    - An integer: Reference to an existing player
    - None: Create a new anonymous player for this match

    Anonymous players are auto-created with unique names and marked with
    is_anonymous=True, allowing them to be filtered from leaderboards.
    """

    player_id: int | None = Field(
        default=None,
        description="Player ID, or None to create an anonymous player",
    )


class MatchParticipantRead(MatchParticipantBase):
    """Properties to return to the client for a match participant."""

    id: int
    player_id: int

    # Instead of just a player_id, return the full Player object.
    player: PlayerRead

    # Rating history for auditing and analysis
    rating_info_before: RatingInfo | None = None
    # Structure: {rating_change, rd_change, vol_change}
    rating_info_change: dict | None = None

    model_config = ConfigDict(from_attributes=True)


# ===============================================
# == Match Schemas
# ===============================================


class MatchBase(BaseModel):
    """Shared properties for a match."""

    game_id: int

    # The `match_metadata` is a flexible JSON field
    match_metadata: dict = Field(default_factory=dict)


class MatchCreate(MatchBase):
    """
    Properties to receive via API on create.
    This is the main payload for submitting a new match.
    """

    # Optional: when the match was played (defaults to now if not provided)
    # Useful for importing historical match data
    played_at: datetime | None = Field(
        default=None,
        description="When the match was played (ISO format). Defaults to current time.",
    )

    participants: list[MatchParticipantCreate]


class MatchRead(MatchBase):
    """Properties to return to the client for a match."""

    id: int
    played_at: datetime

    # Optimistic-locking version; clients echo it back as expected_version
    # when updating the match.
    version: int

    # The list of participants will use the "Read" schema to show full details.
    participants: list[MatchParticipantRead]

    model_config = ConfigDict(from_attributes=True)


class MatchUpdate(BaseModel):
    """Properties to receive when correcting a historical match.

    The game cannot be changed (intentionally not a field). Updating
    played_at or participants triggers a forward rating recalculation of
    every subsequent match in the game.
    """

    # Optimistic locking: must match the match's current version.
    expected_version: int = Field(
        ..., ge=1, description="The match version this update was based on"
    )

    played_at: datetime | None = Field(
        default=None, description="Corrected time the match was played"
    )
    match_metadata: dict | None = Field(
        default=None, description="Replacement metadata (full replace, not merge)"
    )
    participants: list[MatchParticipantCreate] | None = Field(
        default=None,
        min_length=2,
        description="Replacement participant list (full replace, not merge)",
    )


class RecalculationResult(BaseModel):
    """Summary of the rating recalculation triggered by a match correction."""

    matches_recalculated: int
    players_affected: int


class MatchUpdateResponse(BaseModel):
    """Response for a match update: the new state plus recalculation summary.

    recalculation is None when the update didn't affect ratings
    (metadata-only changes).
    """

    match: MatchRead
    recalculation: RecalculationResult | None = None
