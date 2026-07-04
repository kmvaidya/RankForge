# src/rankforge/db/models.py

"""Database models for the RankForge application."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, TypedDict

from sqlalchemy import (
    JSON,
    ForeignKey,
    String,
    UniqueConstraint,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import (
    Mapped,
    declarative_base,
    mapped_column,
    relationship,
)

Base = declarative_base()


# ===============================================
# Type Definitions for JSON Fields
# ===============================================


class RatingInfo(TypedDict):
    """Standard rating info structure for Glicko-2.

    Keys:
        rating: The player's skill rating (default: 1500.0)
        rd: Rating deviation / uncertainty (default: 350.0)
        vol: Volatility / consistency (default: 0.06)
    """

    rating: float
    rd: float
    vol: float


# Default rating for players who haven't played a game yet.
# TODO: Make configurable per-game via a Game.default_rating_info column.
DEFAULT_RATING_INFO: RatingInfo = {"rating": 1500.0, "rd": 350.0, "vol": 0.06}


def utcnow_naive() -> datetime:
    """Current UTC time as a naive datetime.

    All datetime columns store naive UTC. Aware values must never reach the
    database: asyncpg rejects them on TIMESTAMP WITHOUT TIME ZONE columns,
    and SQLite stores them as offset-suffixed strings that break lexical
    comparison/ordering (played_at windows, replay order).
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ===============================================
# Mixins for Common Columns
# ===============================================


class TimestampMixin:
    """Mixin providing created_at and updated_at timestamp columns."""

    created_at: Mapped[datetime] = mapped_column(
        default=utcnow_naive,
        nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        default=None,
        onupdate=utcnow_naive,
        nullable=True,
    )


class VersionMixin:
    """Mixin providing optimistic locking via version column."""

    version: Mapped[int] = mapped_column(default=1, nullable=False)


class SoftDeleteMixin:
    """Mixin providing soft delete support via deleted_at column."""

    deleted_at: Mapped[datetime | None] = mapped_column(default=None, nullable=True)

    @property
    def is_deleted(self) -> bool:
        """Check if this record has been soft-deleted."""
        return self.deleted_at is not None


# ===============================================
# Core Tables: Player and Game
# ===============================================


class Player(Base, SoftDeleteMixin):
    """Represents a unique person across all games.

    Attributes:
        is_anonymous: If True, this player represents an unknown/one-time
            participant who should be excluded from leaderboards.
    """

    __tablename__ = "players"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    is_anonymous: Mapped[bool] = mapped_column(default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        default=utcnow_naive,
        nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        default=None,
        onupdate=utcnow_naive,
        nullable=True,
    )
    version: Mapped[int] = mapped_column(default=1, nullable=False)

    # A player has a collection of profiles, one for each game they play
    game_profiles: Mapped[List["GameProfile"]] = relationship(
        back_populates="player", cascade="all, delete-orphan"
    )
    # With soft delete, we use passive_deletes to preserve match history
    match_participations: Mapped[List["MatchParticipant"]] = relationship(
        back_populates="player", passive_deletes=True
    )

    def __init__(self, name: str, **kw: Any):
        super().__init__(**kw)
        self.name = name


class Game(Base, TimestampMixin, VersionMixin, SoftDeleteMixin):
    """Represents a game that can be played."""

    __tablename__ = "games"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)

    # The name of the calculation strategy,
    # e.g., 'glicko2_team_binary', 'glicko2_hybrid_ranked'
    rating_strategy: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)

    # Per-game rating-behavior knobs. Known keys (all optional):
    #   min_swing: float >= 0 — guaranteed minimum rating gain on a win /
    #       drop on a loss (0/absent = pure Glicko-2)
    #   margin_weight_factor: float >= 0 — scales match weight by score margin
    #   score_preset: int >= 1 — typical winning score, used by quick entry UI
    #   leaderboard_mode: "rating" | "conservative" — default leaderboard sort
    #   tau: float in (0, 3] — Glicko-2 system constant (default 0.5); tune
    #       with `python -m rankforge.tools.tune`
    rating_config: Mapped[dict] = mapped_column(
        JSON, default=lambda: {}, server_default="{}", nullable=False
    )

    # A game has many profiles associated with it
    game_profiles: Mapped[List["GameProfile"]] = relationship(
        back_populates="game", cascade="all, delete-orphan"
    )
    matches: Mapped[List["Match"]] = relationship(back_populates="game")

    def __init__(self, **kw: Any):
        super().__init__(**kw)


class GameProfile(Base, TimestampMixin, VersionMixin, SoftDeleteMixin):
    """Stores a player's rating and stats for a specific game."""

    __tablename__ = "game_profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id"), nullable=False, index=True
    )
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id"), nullable=False, index=True
    )

    # Rating info for Glicko-2: {'rating': 1500.0, 'rd': 350.0, 'vol': 0.06}
    # See RatingInfo TypedDict for structure documentation
    rating_info: Mapped[dict] = mapped_column(JSON, nullable=False)

    # Flexible JSON blob for stats.
    # Ex: {'wins': 10, 'losses': 5, 'win_rate': 0.66, 'spymaster_wins': 4}
    stats: Mapped[dict] = mapped_column(JSON, default=lambda: {})

    player: Mapped["Player"] = relationship(back_populates="game_profiles")
    game: Mapped["Game"] = relationship(back_populates="game_profiles")

    __table_args__ = (UniqueConstraint("player_id", "game_id", name="_player_game_uc"),)

    def __init__(self, **kw: Any):
        super().__init__(**kw)

    @classmethod
    async def find_by_player_and_game(
        cls, db: AsyncSession, player_id: int, game_id: int
    ) -> "GameProfile | None":
        """Find a game profile by player and game IDs."""
        query = select(cls).where(cls.player_id == player_id, cls.game_id == game_id)
        result = await db.execute(query)
        return result.scalar_one_or_none()


# ===============================================
# Match and Results Tables
# ===============================================


class Match(Base, TimestampMixin, VersionMixin, SoftDeleteMixin):
    """Represents a single instance of a game being played."""

    __tablename__ = "matches"
    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id"), nullable=False, index=True
    )
    # Business timestamp: when the match was actually played.
    # Indexed: the recalculation cascade and list endpoints query/sort on it.
    played_at: Mapped[datetime] = mapped_column(default=utcnow_naive, index=True)

    # Pillar 3: Contextual Metadata
    # Ex: {'map': 'A Diverse World', 'game_length': '3 minutes',
    #       'championship_match': true}
    match_metadata: Mapped[dict] = mapped_column(JSON, default=lambda: {})

    game: Mapped["Game"] = relationship(back_populates="matches")
    participants: Mapped[List["MatchParticipant"]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )


class MatchParticipant(Base, TimestampMixin, VersionMixin, SoftDeleteMixin):
    """Links a Player to a Match, recording their specific involvement and result."""

    __tablename__ = "match_participants"
    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.id"), nullable=False, index=True
    )
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id"), nullable=False, index=True
    )

    # Pillar 1: Participation Structure
    # An integer to group players into teams for this match.
    # For free-for-all, each player can have a unique team_id.
    team_id: Mapped[int] = mapped_column(nullable=False)

    # Pillar 2: Performance Data
    # The single source of truth for the result.
    # Golf Ex: {'team_rank': 1, 'individual_rank': 3, 'score': -4}
    # Geoguessr Ex: {'result': 'win', 'score': 24150}
    outcome: Mapped[dict] = mapped_column(JSON, nullable=False)

    # For auditing and historical analysis
    # Uses RatingInfo structure: {'rating': float, 'rd': float, 'vol': float}
    rating_info_before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    rating_info_change: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    player: Mapped["Player"] = relationship(back_populates="match_participations")
    match: Mapped["Match"] = relationship(back_populates="participants")


# ===============================================
# External System Sync Tracking (Game-Agnostic)
# ===============================================


class ExternalSyncBatch(Base, TimestampMixin):
    """Tracks export batches to external rating/tracking systems.

    This is a game-agnostic design that supports any external system:
    - Pickleball: DUPR
    - Tennis: UTR
    - Chess: FIDE, Lichess, Chess.com
    - Any future integrations

    Each batch represents a single export (CSV, API call, etc.) that can
    contain multiple matches.
    """

    __tablename__ = "external_sync_batches"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Which external system this batch is for (e.g., "dupr", "utr", "fide")
    system_name: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # Unique batch identifier within this system: {SYSTEM}-YYYYMMDD-HHMMSS
    batch_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)

    # Path to the generated export file (relative to project root), if applicable
    export_file_path: Mapped[str | None] = mapped_column(String, nullable=True)

    # Summary statistics for this batch
    match_count: Mapped[int] = mapped_column(nullable=False)
    first_match_id: Mapped[int] = mapped_column(nullable=False)
    last_match_id: Mapped[int] = mapped_column(nullable=False)

    # Sync status tracking
    # pending: Export generated, awaiting sync to external system
    # synced: Successfully synced to external system
    # failed: Sync attempt failed
    status: Mapped[str] = mapped_column(String, default="pending", nullable=False)
    synced_at: Mapped[datetime | None] = mapped_column(nullable=True)
    sync_notes: Mapped[str | None] = mapped_column(String, nullable=True)

    # Relationship to individual sync records
    records: Mapped[List["ExternalSyncRecord"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )


class ExternalSyncRecord(Base):
    """Links individual matches to their external sync batch.

    Tracks both included matches and excluded matches with reasons.
    The unique constraint on (system_name, match_id) prevents duplicate
    syncs of the same match to the same external system.
    """

    __tablename__ = "external_sync_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("external_sync_batches.id"), nullable=False, index=True
    )
    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.id"), nullable=False, index=True
    )

    # Which external system (denormalized from batch for query efficiency)
    system_name: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # Whether this match was included in the export or excluded
    included: Mapped[bool] = mapped_column(default=True, nullable=False)

    # If excluded, the reason why
    # Examples:
    #   "ineligible_game_type:Bo1 game", "no_external_id:GuestPlayer", "missing_score"
    exclusion_reason: Mapped[str | None] = mapped_column(String, nullable=True)

    batch: Mapped["ExternalSyncBatch"] = relationship(back_populates="records")

    # Prevent the same match from being synced twice to the same system
    __table_args__ = (
        UniqueConstraint("system_name", "match_id", name="_external_sync_match_uc"),
    )
