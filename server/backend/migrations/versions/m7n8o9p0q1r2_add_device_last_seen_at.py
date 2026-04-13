"""Add last_seen_at column to devices table.

Revision ID: m7n8o9p0q1r2
Revises: l6m7n8o9p0q1
Create Date: 2026-04-13
"""
from alembic import op
import sqlalchemy as sa

revision = "m7n8o9p0q1r2"
down_revision = "l6m7n8o9p0q1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("last_seen_at", sa.DateTime(), nullable=True))
    op.create_index(op.f("ix_devices_last_seen_at"), "devices", ["last_seen_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_devices_last_seen_at"), table_name="devices")
    op.drop_column("devices", "last_seen_at")
