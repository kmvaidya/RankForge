# src/alembic/versions/20260704_add_game_rating_config.py

"""Add games.rating_config

Per-game rating-behavior knobs (JSON): min_swing, margin_weight_factor,
score_preset, leaderboard_mode. Additive column with a constant server
default so SQLite accepts it.

Revision ID: 20260704_rating_config
Revises: 20260703_played_at_idx
Create Date: 2026-07-04
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260704_rating_config"
down_revision: Union[str, Sequence[str], None] = "20260703_played_at_idx"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add rating_config JSON column to games."""
    op.add_column(
        "games",
        sa.Column("rating_config", sa.JSON(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    """Remove rating_config column from games."""
    op.drop_column("games", "rating_config")
