"""smart_device_profiling

Add auto_generated column to device_profiles and create Universal template.

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-03-30 10:00:00.000000

"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c8d9e0f1a2'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UNIVERSAL_TEMPLATE_ID = "00000000-0000-0000-0000-000000000001"

ALL_TEST_IDS = [
    "U01", "U02", "U03", "U04", "U05", "U06", "U07", "U08", "U09",
    "U10", "U11", "U12", "U13", "U14", "U15", "U16", "U17", "U18", "U19",
    "U20", "U21", "U22", "U23", "U24", "U25", "U26", "U27", "U28", "U29",
    "U30", "U31", "U32", "U33", "U34", "U35", "U36", "U37", "U38", "U39",
    "U40", "U41", "U42", "U43",
]


def upgrade() -> None:
    # 1. Add auto_generated column to device_profiles
    with op.batch_alter_table('device_profiles', schema=None) as batch_op:
        batch_op.add_column(sa.Column('auto_generated', sa.Boolean(), nullable=True, server_default=sa.text('0')))

    # 2. Mark existing templates as non-default
    op.execute("UPDATE test_templates SET is_default = 0")

    # 3. Create the Universal template with all 43 tests
    import json
    op.execute(
        sa.text(
            "INSERT OR IGNORE INTO test_templates (id, name, description, version, test_ids, is_default, is_active, created_at, updated_at) "
            "VALUES (:id, :name, :desc, :ver, :test_ids, :is_default, :is_active, datetime('now'), datetime('now'))"
        ).bindparams(
            id=UNIVERSAL_TEMPLATE_ID,
            name="Universal (Smart Profiling)",
            desc="All 43 tests — the device fingerprinter automatically skips tests that don't apply to the detected device type.",
            ver="2.0",
            test_ids=json.dumps(ALL_TEST_IDS),
            is_default=1,
            is_active=1,
        )
    )


def downgrade() -> None:
    # Remove universal template
    op.execute(
        sa.text("DELETE FROM test_templates WHERE id = :id").bindparams(id=UNIVERSAL_TEMPLATE_ID)
    )

    # Remove auto_generated column
    with op.batch_alter_table('device_profiles', schema=None) as batch_op:
        batch_op.drop_column('auto_generated')
