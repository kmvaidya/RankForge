# src/rankforge/exceptions.py

"""Custom exception hierarchy for RankForge.

This module provides a structured exception hierarchy that enables:
1. Proper HTTP status code mapping in API endpoints
2. Detailed error context for logging and debugging
3. Clear distinction between different error categories
"""

from __future__ import annotations


class RankForgeError(Exception):
    """Base exception for all RankForge errors.

    Attributes:
        message: Human-readable error description
        details: Optional dict with additional context for logging/debugging
    """

    def __init__(self, message: str, details: dict | None = None) -> None:
        self.message = message
        self.details = details or {}
        super().__init__(message)


# =============================================================================
# Resource Not Found Errors (HTTP 404)
# =============================================================================


class ResourceNotFoundError(RankForgeError):
    """Base class for resource not found errors."""

    pass


class GameNotFoundError(ResourceNotFoundError):
    """Raised when a game ID does not exist."""

    def __init__(self, game_id: int) -> None:
        super().__init__(
            message=f"Game with ID {game_id} not found",
            details={"game_id": game_id},
        )


class PlayerNotFoundError(ResourceNotFoundError):
    """Raised when a player ID does not exist."""

    def __init__(self, player_id: int) -> None:
        super().__init__(
            message=f"Player with ID {player_id} not found",
            details={"player_id": player_id},
        )


class GameProfileNotFoundError(ResourceNotFoundError):
    """Raised when a game profile does not exist.

    This typically indicates an internal consistency error since profiles
    should be created automatically when processing matches.
    """

    def __init__(self, player_id: int, game_id: int) -> None:
        super().__init__(
            message=f"GameProfile for player {player_id} in game {game_id} not found",
            details={"player_id": player_id, "game_id": game_id},
        )


class MatchNotFoundError(ResourceNotFoundError):
    """Raised when a match ID does not exist (or has been deleted)."""

    def __init__(self, match_id: int) -> None:
        super().__init__(
            message=f"Match with ID {match_id} not found",
            details={"match_id": match_id},
        )


# =============================================================================
# Conflict Errors (HTTP 409)
# =============================================================================


class ConflictError(RankForgeError):
    """Base class for conflict errors (concurrent modification, etc.)."""

    pass


class ConcurrentModificationError(ConflictError):
    """Raised when an update's expected_version doesn't match the record.

    This implements optimistic locking: clients must send the version they
    read; if another update happened in between, the versions won't match.
    """

    def __init__(self, expected_version: int, actual_version: int) -> None:
        super().__init__(
            message=(
                f"Match was modified by another request "
                f"(expected version {expected_version}, found {actual_version}). "
                f"Re-fetch the match and retry."
            ),
            details={
                "expected_version": expected_version,
                "actual_version": actual_version,
            },
        )


# =============================================================================
# Validation Errors (HTTP 422)
# =============================================================================


class ValidationError(RankForgeError):
    """Base class for validation errors."""

    pass


class ParticipantValidationError(ValidationError):
    """Base class for participant validation errors."""

    pass


class InsufficientParticipantsError(ParticipantValidationError):
    """Raised when a match has fewer than 2 participants."""

    def __init__(self, count: int) -> None:
        super().__init__(
            message=f"Match requires at least 2 participants, got {count}",
            details={"participant_count": count},
        )


class DuplicatePlayerError(ParticipantValidationError):
    """Raised when the same player appears multiple times in a match."""

    def __init__(self, player_ids: list[int]) -> None:
        super().__init__(
            message=f"Duplicate player(s) in match: {player_ids}",
            details={"duplicate_player_ids": player_ids},
        )


class InsufficientTeamsError(ParticipantValidationError):
    """Raised when a match has fewer than 2 distinct teams."""

    def __init__(self, team_count: int) -> None:
        super().__init__(
            message=f"Match requires at least 2 teams, got {team_count}",
            details={"team_count": team_count},
        )


class InvalidOutcomeError(ParticipantValidationError):
    """Raised when participant outcome data is invalid."""

    def __init__(self, player_id: int, reason: str) -> None:
        super().__init__(
            message=f"Invalid outcome for player {player_id}: {reason}",
            details={"player_id": player_id, "reason": reason},
        )


class MatchTooOldToUpdateError(ValidationError):
    """Raised when a match is beyond the configured update-age threshold."""

    def __init__(self, match_id: int, age_days: int, max_age_days: int) -> None:
        super().__init__(
            message=(
                f"Match {match_id} is {age_days} days old and cannot be updated "
                f"(maximum age: {max_age_days} days)"
            ),
            details={
                "match_id": match_id,
                "age_days": age_days,
                "max_age_days": max_age_days,
            },
        )


# =============================================================================
# Rating Engine Errors (HTTP 500 or 422 depending on cause)
# =============================================================================


class RatingEngineError(RankForgeError):
    """Base class for rating calculation errors."""

    pass


class RatingCalculationError(RatingEngineError):
    """Raised when rating calculation fails due to invalid data."""

    def __init__(self, message: str, player_id: int | None = None) -> None:
        details = {"player_id": player_id} if player_id else {}
        super().__init__(message=message, details=details)


class NonCompetitiveMatchError(RatingEngineError):
    """Raised when a match cannot be rated (e.g., only 1 team)."""

    def __init__(self, team_count: int) -> None:
        super().__init__(
            message=f"Cannot calculate ratings for non-competitive match "
            f"with {team_count} team(s)",
            details={"team_count": team_count},
        )
