"""Merge Alembic heads after DHCP and projects/auth/device branches.

Revision ID: j4k5l6m7n8o9
Revises: e5f6a7b8c9d0, i3j4k5l6m7n8
Create Date: 2026-04-10 18:10:00.000000
"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "j4k5l6m7n8o9"
down_revision: Union[str, tuple[str, str], None] = ("e5f6a7b8c9d0", "i3j4k5l6m7n8")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
