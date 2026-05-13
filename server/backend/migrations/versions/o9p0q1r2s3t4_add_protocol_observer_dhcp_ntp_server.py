"""add DHCP NTP server option to protocol observer settings

Revision ID: o9p0q1r2s3t4
Revises: n8o9p0q1r2s3
Create Date: 2026-05-09 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "o9p0q1r2s3t4"
down_revision = "n8o9p0q1r2s3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "protocol_observer_settings",
        sa.Column("dhcp_ntp_server", sa.String(length=64), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("protocol_observer_settings", "dhcp_ntp_server")
