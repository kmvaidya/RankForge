"""Add external sync tracking tables

Revision ID: 20251222_external_sync
Revises: 20251220_is_anonymous
Create Date: 2025-12-22

This migration adds game-agnostic tables for tracking external system syncs:
- external_sync_batches: Tracks each export batch (DUPR, UTR, FIDE, etc.)
- external_sync_records: Links individual matches to batches with exclusion tracking

The design supports any external rating/tracking system without schema changes.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20251222_external_sync"
down_revision: Union[str, Sequence[str], None] = "20251220_is_anonymous"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create external sync tracking tables."""
    # Create external_sync_batches table
    op.create_table(
        "external_sync_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("system_name", sa.String(), nullable=False),
        sa.Column("batch_id", sa.String(), unique=True, nullable=False),
        sa.Column("export_file_path", sa.String(), nullable=True),
        sa.Column("match_count", sa.Integer(), nullable=False),
        sa.Column("first_match_id", sa.Integer(), nullable=False),
        sa.Column("last_match_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("synced_at", sa.DateTime(), nullable=True),
        sa.Column("sync_notes", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_external_sync_batches_system_name",
        "external_sync_batches",
        ["system_name"],
    )

    # Create external_sync_records table
    # Note: SQLite doesn't support adding constraints after table creation,
    # so we use a composite unique index instead of UniqueConstraint
    op.create_table(
        "external_sync_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "batch_id",
            sa.Integer(),
            sa.ForeignKey("external_sync_batches.id"),
            nullable=False,
        ),
        sa.Column(
            "match_id",
            sa.Integer(),
            sa.ForeignKey("matches.id"),
            nullable=False,
        ),
        sa.Column("system_name", sa.String(), nullable=False),
        sa.Column("included", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("exclusion_reason", sa.String(), nullable=True),
    )

    # Create indexes for efficient queries
    op.create_index(
        "ix_external_sync_records_batch_id", "external_sync_records", ["batch_id"]
    )
    op.create_index(
        "ix_external_sync_records_match_id", "external_sync_records", ["match_id"]
    )
    op.create_index(
        "ix_external_sync_records_system_name", "external_sync_records", ["system_name"]
    )
    # Composite unique index to prevent duplicate syncs per system
    op.create_index(
        "ix_external_sync_records_system_match",
        "external_sync_records",
        ["system_name", "match_id"],
        unique=True,
    )


def downgrade() -> None:
    """Drop external sync tracking tables."""
    op.drop_index("ix_external_sync_records_system_match", "external_sync_records")
    op.drop_index("ix_external_sync_records_system_name", "external_sync_records")
    op.drop_index("ix_external_sync_records_match_id", "external_sync_records")
    op.drop_index("ix_external_sync_records_batch_id", "external_sync_records")
    op.drop_table("external_sync_records")
    op.drop_index("ix_external_sync_batches_system_name", "external_sync_batches")
    op.drop_table("external_sync_batches")
