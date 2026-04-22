"""add protocol observer settings table

Revision ID: n8o9p0q1r2s3
Revises: m7n8o9p0q1r2
Create Date: 2026-04-21 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "n8o9p0q1r2s3"
down_revision = "m7n8o9p0q1r2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "protocol_observer_settings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "singleton_key",
            sa.String(length=1),
            nullable=False,
            server_default="_",
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("bind_host", sa.String(length=64), nullable=False, server_default="0.0.0.0"),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("dns_port", sa.Integer(), nullable=False, server_default="53"),
        sa.Column("ntp_port", sa.Integer(), nullable=False, server_default="123"),
        sa.Column("dhcp_port", sa.Integer(), nullable=False, server_default="67"),
        sa.Column("dhcp_offer_ip", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("dhcp_subnet_mask", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("dhcp_router_ip", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("dhcp_dns_server", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("dhcp_lease_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "singleton_key",
            name="uq_protocol_observer_settings_singleton",
        ),
    )


def downgrade() -> None:
    op.drop_table("protocol_observer_settings")
