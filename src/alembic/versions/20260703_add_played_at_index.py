# src/alembic/versions/20260703_add_played_at_index.py

"""Add index on matches.played_at

The match update cascade (forward rating recalculation) and the match list
endpoints query and sort by played_at; give it an index.

Revision ID: 20260703_played_at_idx
Revises: 20251222_external_sync
Create Date: 2026-07-03
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260703_played_at_idx"
down_revision: Union[str, Sequence[str], None] = "20251222_external_sync"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add index on matches.played_at."""
    op.create_index("ix_matches_played_at", "matches", ["played_at"])


def downgrade() -> None:
    """Remove index on matches.played_at."""
    op.drop_index("ix_matches_played_at", table_name="matches")
