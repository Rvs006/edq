"""Device and user schema hardening.

Add mac_address unique constraint and index, ip_address+project_id composite
unique constraint, NOT NULL enforcement for addressing_mode/category/status,
FK ondelete=SET NULL alignment, password_hash/totp secret column widening,
OIDC identity unique constraint, and failed_login_attempts check constraint.

Revision ID: l6m7n8o9p0q1
Revises: k5l6m7n8o9p0
Create Date: 2026-04-11 10:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "l6m7n8o9p0q1"
down_revision: Union[str, None] = "k5l6m7n8o9p0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # ------------------------------------------------------------------
    # Pre-migration data cleanup — devices table
    # ------------------------------------------------------------------

    # 1. Fill NULLs with safe defaults so NOT NULL constraints can be applied.
    bind.execute(
        sa.text("UPDATE devices SET addressing_mode = 'static' WHERE addressing_mode IS NULL")
    )
    bind.execute(
        sa.text("UPDATE devices SET category = 'unknown' WHERE category IS NULL")
    )
    bind.execute(
        sa.text("UPDATE devices SET status = 'discovered' WHERE status IS NULL")
    )

    # 2. Deduplicate mac_address: for every group of duplicate non-NULL
    #    mac_address values, keep the most-recently-updated row and NULL out
    #    the mac_address on all older duplicates so the unique constraint can
    #    be applied without conflicts.
    if bind.dialect.name == "postgresql":
        bind.execute(
            sa.text(
                """
                UPDATE devices AS d
                SET    mac_address = NULL
                WHERE  mac_address IS NOT NULL
                  AND  id NOT IN (
                      SELECT DISTINCT ON (mac_address) id
                      FROM   devices
                      WHERE  mac_address IS NOT NULL
                      ORDER  BY mac_address, updated_at DESC NULLS LAST, id
                  )
                """
            )
        )
    else:
        # SQLite-compatible approach using a correlated subquery.
        bind.execute(
            sa.text(
                """
                UPDATE devices
                SET    mac_address = NULL
                WHERE  mac_address IS NOT NULL
                  AND  id NOT IN (
                      SELECT id
                      FROM (
                          SELECT id,
                                 ROW_NUMBER() OVER (
                                     PARTITION BY mac_address
                                     ORDER BY updated_at DESC, id
                                 ) AS rn
                          FROM   devices
                          WHERE  mac_address IS NOT NULL
                      ) ranked
                      WHERE rn = 1
                  )
                """
            )
        )

    # ------------------------------------------------------------------
    # devices table schema changes
    # ------------------------------------------------------------------
    with op.batch_alter_table("devices", schema=None) as batch_op:
        # Unique constraint on mac_address
        batch_op.create_unique_constraint("uq_device_mac", ["mac_address"])

        # Index on mac_address
        batch_op.create_index("ix_device_mac_address", ["mac_address"], unique=False)

        # Composite unique constraint on (ip_address, project_id)
        batch_op.create_unique_constraint(
            "uq_device_ip_project", ["ip_address", "project_id"]
        )

        # Enforce NOT NULL on addressing_mode (already backfilled above)
        batch_op.alter_column(
            "addressing_mode",
            existing_type=sa.Enum(
                "static", "dhcp", "unknown", name="addressingmode"
            ),
            nullable=False,
        )

        # Enforce NOT NULL on category
        batch_op.alter_column(
            "category",
            existing_type=sa.Enum(
                "camera",
                "controller",
                "intercom",
                "access_panel",
                "lighting",
                "hvac",
                "iot_sensor",
                "meter",
                "unknown",
                name="devicecategory",
            ),
            nullable=False,
        )

        # Enforce NOT NULL on status
        batch_op.alter_column(
            "status",
            existing_type=sa.Enum(
                "discovered",
                "identified",
                "testing",
                "tested",
                "qualified",
                "failed",
                name="devicestatus",
            ),
            nullable=False,
        )

        # Align FK ondelete for profile_id
        batch_op.drop_constraint("devices_profile_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "devices_profile_id_fkey",
            "device_profiles",
            ["profile_id"],
            ["id"],
            ondelete="SET NULL",
        )

        # Align FK ondelete for project_id
        batch_op.drop_constraint("devices_project_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "devices_project_id_fkey",
            "projects",
            ["project_id"],
            ["id"],
            ondelete="SET NULL",
        )

        # Align FK ondelete for discovered_by
        batch_op.drop_constraint("devices_discovered_by_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "devices_discovered_by_fkey",
            "agents",
            ["discovered_by"],
            ["id"],
            ondelete="SET NULL",
        )

    # ------------------------------------------------------------------
    # users table schema changes
    # ------------------------------------------------------------------
    with op.batch_alter_table("users", schema=None) as batch_op:
        # Widen password_hash from String(256) -> String(512)
        batch_op.alter_column(
            "password_hash",
            existing_type=sa.String(length=256),
            type_=sa.String(length=512),
            nullable=False,
        )

        # Widen totp_secret from String(32) -> String(256)
        batch_op.alter_column(
            "totp_secret",
            existing_type=sa.String(length=32),
            type_=sa.String(length=256),
            nullable=True,
        )

        # Widen totp_provisional_secret from String(32) -> String(256)
        batch_op.alter_column(
            "totp_provisional_secret",
            existing_type=sa.String(length=32),
            type_=sa.String(length=256),
            nullable=True,
        )

        # Unique constraint on (oidc_provider, oidc_subject)
        batch_op.create_unique_constraint(
            "uq_user_oidc_identity", ["oidc_provider", "oidc_subject"]
        )

        # Check constraint: failed_login_attempts >= 0
        batch_op.create_check_constraint(
            "ck_user_failed_attempts_nonneg",
            "failed_login_attempts >= 0",
        )


def downgrade() -> None:
    # ------------------------------------------------------------------
    # users table — reverse in reverse order
    # ------------------------------------------------------------------
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_constraint(
            "ck_user_failed_attempts_nonneg", type_="check"
        )
        batch_op.drop_constraint("uq_user_oidc_identity", type_="unique")

        # Revert totp_provisional_secret back to String(32)
        batch_op.alter_column(
            "totp_provisional_secret",
            existing_type=sa.String(length=256),
            type_=sa.String(length=32),
            nullable=True,
        )

        # Revert totp_secret back to String(32)
        batch_op.alter_column(
            "totp_secret",
            existing_type=sa.String(length=256),
            type_=sa.String(length=32),
            nullable=True,
        )

        # Revert password_hash back to String(256)
        batch_op.alter_column(
            "password_hash",
            existing_type=sa.String(length=512),
            type_=sa.String(length=256),
            nullable=False,
        )

    # ------------------------------------------------------------------
    # devices table — reverse in reverse order
    # ------------------------------------------------------------------
    with op.batch_alter_table("devices", schema=None) as batch_op:
        # Restore FKs without ondelete (drop-and-recreate without clause)
        batch_op.drop_constraint("devices_discovered_by_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "devices_discovered_by_fkey",
            "agents",
            ["discovered_by"],
            ["id"],
        )

        batch_op.drop_constraint("devices_project_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "devices_project_id_fkey",
            "projects",
            ["project_id"],
            ["id"],
        )

        batch_op.drop_constraint("devices_profile_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "devices_profile_id_fkey",
            "device_profiles",
            ["profile_id"],
            ["id"],
        )

        # Revert NOT NULL -> nullable for status, category, addressing_mode
        batch_op.alter_column(
            "status",
            existing_type=sa.Enum(
                "discovered",
                "identified",
                "testing",
                "tested",
                "qualified",
                "failed",
                name="devicestatus",
            ),
            nullable=True,
        )

        batch_op.alter_column(
            "category",
            existing_type=sa.Enum(
                "camera",
                "controller",
                "intercom",
                "access_panel",
                "lighting",
                "hvac",
                "iot_sensor",
                "meter",
                "unknown",
                name="devicecategory",
            ),
            nullable=True,
        )

        batch_op.alter_column(
            "addressing_mode",
            existing_type=sa.Enum(
                "static", "dhcp", "unknown", name="addressingmode"
            ),
            nullable=True,
        )

        # Drop composite unique constraint on (ip_address, project_id)
        batch_op.drop_constraint("uq_device_ip_project", type_="unique")

        # Drop index on mac_address
        batch_op.drop_index("ix_device_mac_address")

        # Drop unique constraint on mac_address
        batch_op.drop_constraint("uq_device_mac", type_="unique")
