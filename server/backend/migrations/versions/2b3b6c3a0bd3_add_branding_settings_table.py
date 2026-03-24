"""add branding_settings table

Revision ID: 2b3b6c3a0bd3
Revises: 0aeebda00bb4
Create Date: 2026-03-24 01:20:33.498570

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2b3b6c3a0bd3'
down_revision: Union[str, None] = '0aeebda00bb4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'branding_settings',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('company_name', sa.String(255), nullable=True),
        sa.Column('logo_path', sa.String(512), nullable=True),
        sa.Column('primary_color', sa.String(7), nullable=True),
        sa.Column('footer_text', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('branding_settings')
