"""Alembic env.py — EDQ database migration environment.

Imports all SQLAlchemy models so autogenerate can detect schema changes.
Supports both offline (SQL script) and online (direct DB) migration modes.
"""

import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.models.database import Base
from app.models.user import User
from app.models.device import Device
from app.models.device_profile import DeviceProfile
from app.models.test_template import TestTemplate
from app.models.test_run import TestRun
from app.models.test_result import TestResult
from app.models.attachment import Attachment
from app.models.agent import Agent
from app.models.audit_log import AuditLog
from app.models.report_config import ReportConfig
from app.models.sync_queue import SyncQueue
from app.models.protocol_whitelist import ProtocolWhitelist
from app.models.nessus_finding import NessusFinding
from app.models.network_scan import NetworkScan
from app.models.test_plan import TestPlan
from app.models.branding import BrandingSettings
from app.models.scan_schedule import ScanSchedule
from app.models.refresh_token import RefreshToken
from app.models.authorized_network import AuthorizedNetwork
from app.models.project import Project

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

db_url = os.environ.get("DATABASE_URL", "")
if db_url:
    # Convert async driver URLs to sync equivalents for Alembic
    sync_url = db_url.replace("+aiosqlite", "").replace("+asyncpg", "")
    config.set_main_option("sqlalchemy.url", sync_url)

_effective_url = config.get_main_option("sqlalchemy.url")
_is_sqlite = _effective_url.startswith("sqlite")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Emits SQL to stdout without requiring a live database connection.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=_is_sqlite,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode with a live database connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=_is_sqlite,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
