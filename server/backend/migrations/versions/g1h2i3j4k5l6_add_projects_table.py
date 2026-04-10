"""Add projects table and project_id to devices/test_runs.

Revision ID: g1h2i3j4k5l6
Revises: f93782ca9fb5
Create Date: 2026-04-09
"""
from alembic import op
import sqlalchemy as sa

revision = 'g1h2i3j4k5l6'
down_revision = 'f93782ca9fb5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'projects',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('status', sa.String(20), server_default='active'),
        sa.Column('created_by', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('client_name', sa.String(255), nullable=True),
        sa.Column('location', sa.String(255), nullable=True),
        sa.Column('device_count', sa.Integer, server_default='0'),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('is_archived', sa.Boolean, server_default=sa.text('0')),
    )

    with op.batch_alter_table('devices') as batch_op:
        batch_op.add_column(sa.Column('project_id', sa.String(36), nullable=True))
        batch_op.create_foreign_key(
            'fk_devices_project_id_projects',
            'projects',
            ['project_id'],
            ['id'],
        )

    with op.batch_alter_table('test_runs') as batch_op:
        batch_op.add_column(sa.Column('project_id', sa.String(36), nullable=True))
        batch_op.create_foreign_key(
            'fk_test_runs_project_id_projects',
            'projects',
            ['project_id'],
            ['id'],
        )


def downgrade() -> None:
    with op.batch_alter_table('test_runs') as batch_op:
        batch_op.drop_constraint('fk_test_runs_project_id_projects', type_='foreignkey')
        batch_op.drop_column('project_id')
    with op.batch_alter_table('devices') as batch_op:
        batch_op.drop_constraint('fk_devices_project_id_projects', type_='foreignkey')
        batch_op.drop_column('project_id')
    op.drop_table('projects')
