"""Add timestamps, indexes, version, and soft delete columns

Revision ID: 20251220_timestamps
Revises: 67205d1019b0
Create Date: 2025-12-20

This migration adds:
- created_at, updated_at timestamps to all tables
- version column for optimistic locking
- deleted_at column for soft delete support
- Indexes on all foreign key columns

Note: SQLite requires constant defaults for ALTER TABLE ADD COLUMN,
so we use a fixed timestamp string for created_at on existing rows.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20251220_timestamps"
down_revision: Union[str, Sequence[str], None] = "67205d1019b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Fixed timestamp for existing rows (SQLite requires constant default)
MIGRATION_TIMESTAMP = "2025-12-20 00:00:00"


def upgrade() -> None:
    """Add timestamps, version, deleted_at, and indexes to all tables."""
    # === PLAYERS ===
    # Player already has created_at, add updated_at, version, deleted_at
    op.add_column(
        "players",
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "players",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "players",
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )

    # === GAMES ===
    op.add_column(
        "games",
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=MIGRATION_TIMESTAMP,
        ),
    )
    op.add_column(
        "games",
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "games",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "games",
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )

    # === GAME_PROFILES ===
    op.add_column(
        "game_profiles",
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=MIGRATION_TIMESTAMP,
        ),
    )
    op.add_column(
        "game_profiles",
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "game_profiles",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "game_profiles",
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )
    # Add indexes on foreign keys
    op.create_index("ix_game_profiles_player_id", "game_profiles", ["player_id"])
    op.create_index("ix_game_profiles_game_id", "game_profiles", ["game_id"])

    # === MATCHES ===
    # Match has played_at (business field), add created_at for audit
    op.add_column(
        "matches",
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=MIGRATION_TIMESTAMP,
        ),
    )
    op.add_column(
        "matches",
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "matches",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "matches",
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )
    # Add index on foreign key
    op.create_index("ix_matches_game_id", "matches", ["game_id"])

    # === MATCH_PARTICIPANTS ===
    op.add_column(
        "match_participants",
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=MIGRATION_TIMESTAMP,
        ),
    )
    op.add_column(
        "match_participants",
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "match_participants",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "match_participants",
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )
    # Add indexes on foreign keys
    op.create_index(
        "ix_match_participants_match_id", "match_participants", ["match_id"]
    )
    op.create_index(
        "ix_match_participants_player_id", "match_participants", ["player_id"]
    )


def downgrade() -> None:
    """Remove timestamps, version, deleted_at, and indexes from all tables."""
    # === MATCH_PARTICIPANTS ===
    op.drop_index("ix_match_participants_player_id", "match_participants")
    op.drop_index("ix_match_participants_match_id", "match_participants")
    op.drop_column("match_participants", "deleted_at")
    op.drop_column("match_participants", "version")
    op.drop_column("match_participants", "updated_at")
    op.drop_column("match_participants", "created_at")

    # === MATCHES ===
    op.drop_index("ix_matches_game_id", "matches")
    op.drop_column("matches", "deleted_at")
    op.drop_column("matches", "version")
    op.drop_column("matches", "updated_at")
    op.drop_column("matches", "created_at")

    # === GAME_PROFILES ===
    op.drop_index("ix_game_profiles_game_id", "game_profiles")
    op.drop_index("ix_game_profiles_player_id", "game_profiles")
    op.drop_column("game_profiles", "deleted_at")
    op.drop_column("game_profiles", "version")
    op.drop_column("game_profiles", "updated_at")
    op.drop_column("game_profiles", "created_at")

    # === GAMES ===
    op.drop_column("games", "deleted_at")
    op.drop_column("games", "version")
    op.drop_column("games", "updated_at")
    op.drop_column("games", "created_at")

    # === PLAYERS ===
    op.drop_column("players", "deleted_at")
    op.drop_column("players", "version")
    op.drop_column("players", "updated_at")
