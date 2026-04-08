"""add_dhcp_addressing_mode

Make ip_address nullable and add addressing_mode column to devices table
to support DHCP devices that don't have an IP address yet.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-04-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite requires batch mode for ALTER TABLE
    with op.batch_alter_table('devices', schema=None) as batch_op:
        # Make ip_address nullable for DHCP devices
        batch_op.alter_column(
            'ip_address',
            existing_type=sa.String(length=45),
            nullable=True,
        )
        # Add addressing_mode column: static, dhcp, or unknown
        batch_op.add_column(
            sa.Column(
                'addressing_mode',
                sa.Enum('static', 'dhcp', 'unknown', name='addressingmode'),
                nullable=True,
                server_default='static',
            )
        )

    # Backfill existing rows
    op.execute("UPDATE devices SET addressing_mode = 'static' WHERE addressing_mode IS NULL")


def downgrade() -> None:
    with op.batch_alter_table('devices', schema=None) as batch_op:
        batch_op.drop_column('addressing_mode')
        batch_op.alter_column(
            'ip_address',
            existing_type=sa.String(length=45),
            nullable=False,
        )
