"""Add is_anonymous column to players table

Revision ID: 20251220_is_anonymous
Revises: 20251220_timestamps
Create Date: 2025-12-20

This migration adds the is_anonymous boolean column to the players table
to support anonymous/one-time participants in casual matches.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20251220_is_anonymous"
down_revision: Union[str, Sequence[str], None] = "20251220_timestamps"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add is_anonymous column with index."""
    op.add_column(
        "players",
        sa.Column("is_anonymous", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.create_index("ix_players_is_anonymous", "players", ["is_anonymous"])


def downgrade() -> None:
    """Remove is_anonymous column and index."""
    op.drop_index("ix_players_is_anonymous", "players")
    op.drop_column("players", "is_anonymous")
