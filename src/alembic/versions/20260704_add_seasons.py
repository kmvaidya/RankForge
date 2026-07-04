# src/alembic/versions/20260704_add_seasons.py

"""Add seasons table

Season boundaries per game: creating one resets profile RDs and zeroes
per-season stats; the recalculation cascade replays boundaries between
matches deterministically.

Revision ID: 20260704_seasons
Revises: 20260704_rating_config
Create Date: 2026-07-04
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260704_seasons"
down_revision: Union[str, Sequence[str], None] = "20260704_rating_config"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the seasons table."""
    op.create_table(
        "seasons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("game_id", sa.Integer(), sa.ForeignKey("games.id"), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("game_id", "number", name="_game_season_number_uc"),
    )
    op.create_index("ix_seasons_game_id", "seasons", ["game_id"])


def downgrade() -> None:
    """Drop the seasons table."""
    op.drop_index("ix_seasons_game_id", table_name="seasons")
    op.drop_table("seasons")
