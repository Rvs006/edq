"""Align auth hardening and test result override schema.

Revision ID: k5l6m7n8o9p0
Revises: j4k5l6m7n8o9
Create Date: 2026-04-10 19:30:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "k5l6m7n8o9p0"
down_revision: Union[str, None] = "j4k5l6m7n8o9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _assert_casefold_uniqueness(bind) -> None:
    duplicate_usernames = bind.execute(
        sa.text(
            """
            SELECT lower(username) AS normalized
            FROM users
            GROUP BY lower(username)
            HAVING COUNT(*) > 1
            """
        )
    ).fetchall()
    duplicate_emails = bind.execute(
        sa.text(
            """
            SELECT lower(email) AS normalized
            FROM users
            GROUP BY lower(email)
            HAVING COUNT(*) > 1
            """
        )
    ).fetchall()
    if duplicate_usernames or duplicate_emails:
        raise RuntimeError(
            "Cannot add case-insensitive unique indexes because duplicate users already exist. "
            "Resolve duplicate usernames/emails before applying this migration."
        )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    with op.batch_alter_table("test_results", schema=None) as batch_op:
        if not _has_column(inspector, "test_results", "override_reason"):
            batch_op.add_column(sa.Column("override_reason", sa.Text(), nullable=True))
        if not _has_column(inspector, "test_results", "override_verdict"):
            batch_op.add_column(sa.Column("override_verdict", sa.String(length=32), nullable=True))
        if not _has_column(inspector, "test_results", "overridden_by_user_id"):
            batch_op.add_column(sa.Column("overridden_by_user_id", sa.String(length=36), nullable=True))
        if not _has_column(inspector, "test_results", "overridden_by_username"):
            batch_op.add_column(sa.Column("overridden_by_username", sa.String(length=64), nullable=True))
        if not _has_column(inspector, "test_results", "overridden_at"):
            batch_op.add_column(sa.Column("overridden_at", sa.DateTime(), nullable=True))

    op.execute("CREATE INDEX IF NOT EXISTS ix_devices_project_id ON devices (project_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_test_runs_project_id ON test_runs (project_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_test_templates_created_by ON test_templates (created_by)")

    _assert_casefold_uniqueness(bind)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_username_lower ON users (lower(username))")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_email_lower ON users (lower(email))")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_users_email_lower")
    op.execute("DROP INDEX IF EXISTS ux_users_username_lower")
    op.execute("DROP INDEX IF EXISTS ix_test_templates_created_by")
    op.execute("DROP INDEX IF EXISTS ix_test_runs_project_id")
    op.execute("DROP INDEX IF EXISTS ix_devices_project_id")

    bind = op.get_bind()
    inspector = sa.inspect(bind)

    with op.batch_alter_table("test_results", schema=None) as batch_op:
        if _has_column(inspector, "test_results", "overridden_at"):
            batch_op.drop_column("overridden_at")
        if _has_column(inspector, "test_results", "overridden_by_username"):
            batch_op.drop_column("overridden_by_username")
        if _has_column(inspector, "test_results", "overridden_by_user_id"):
            batch_op.drop_column("overridden_by_user_id")
        if _has_column(inspector, "test_results", "override_verdict"):
            batch_op.drop_column("override_verdict")
        if _has_column(inspector, "test_results", "override_reason"):
            batch_op.drop_column("override_reason")
