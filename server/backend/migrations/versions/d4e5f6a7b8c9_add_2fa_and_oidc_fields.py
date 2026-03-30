"""add_2fa_and_oidc_fields

Add TOTP 2FA and OIDC columns to users table.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-03-30 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("totp_secret", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("totp_provisional_secret", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("oidc_provider", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("oidc_subject", sa.String(256), nullable=True))
        batch_op.add_column(sa.Column("oidc_email", sa.String(320), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("oidc_email")
        batch_op.drop_column("oidc_subject")
        batch_op.drop_column("oidc_provider")
        batch_op.drop_column("totp_provisional_secret")
        batch_op.drop_column("totp_secret")
