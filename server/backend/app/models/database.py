"""Database engine, session management, and initialization.

PostgreSQL is the primary runtime for direct and Docker deployments.
SQLite remains available as an explicit override for tests and single-user fallback.
"""

import asyncio
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.config import settings


_is_sqlite = settings.DATABASE_URL.startswith("sqlite")


class Base(DeclarativeBase):
    pass


def _set_sqlite_pragmas(dbapi_connection, connection_record):
    """Enable WAL mode, foreign keys, and set busy timeout for SQLite."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA cache_size=-64000")       # 64 MB page cache
    cursor.execute("PRAGMA mmap_size=268435456")     # 256 MB memory-mapped I/O
    cursor.execute("PRAGMA temp_store=MEMORY")       # Temp tables in RAM
    cursor.close()


# Engine kwargs — tune pool size for PostgreSQL concurrent workloads
_engine_kwargs = {
    "echo": settings.DEBUG,
    "future": True,
    "pool_pre_ping": True,
}
if not _is_sqlite:
    # PostgreSQL: larger pool for concurrent device scans (20+ devices)
    _engine_kwargs.update({
        "pool_size": 20,
        "max_overflow": 30,
        "pool_timeout": 30,
        "pool_recycle": 1800,  # Recycle connections every 30 min
    })

# Async engine for the running application
engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)

if _is_sqlite:
    event.listen(engine.sync_engine, "connect", _set_sqlite_pragmas)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Sync engine for init scripts and migrations
if _is_sqlite:
    sync_url = settings.DATABASE_URL.replace("+aiosqlite", "")
else:
    sync_url = settings.DATABASE_URL.replace("+asyncpg", "")
sync_engine = create_engine(sync_url, echo=settings.DEBUG)
if _is_sqlite:
    event.listen(sync_engine, "connect", _set_sqlite_pragmas)
SessionLocal = sessionmaker(bind=sync_engine, autocommit=False, autoflush=False)

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _BACKEND_DIR / "alembic.ini"
_FALSE_SQL = "0" if _is_sqlite else "FALSE"
_LEGACY_SCHEMA_PATCHES = (
    "ALTER TABLE users ADD COLUMN failed_login_attempts INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN locked_until TIMESTAMP",
    "ALTER TABLE users ADD COLUMN totp_secret TEXT",
    "ALTER TABLE users ADD COLUMN totp_provisional_secret TEXT",
    "ALTER TABLE users ADD COLUMN oidc_provider TEXT",
    "ALTER TABLE users ADD COLUMN oidc_subject TEXT",
    "ALTER TABLE users ADD COLUMN oidc_email TEXT",
    "ALTER TABLE users ADD COLUMN access_tokens_revoked_at TIMESTAMP",
    "ALTER TABLE devices ADD COLUMN addressing_mode TEXT DEFAULT 'static'",
    "ALTER TABLE devices ADD COLUMN project_id TEXT",
    "ALTER TABLE devices ADD COLUMN location TEXT",
    "ALTER TABLE devices ADD COLUMN serial_number TEXT",
    "ALTER TABLE test_runs ADD COLUMN project_id TEXT",
    "ALTER TABLE test_results ADD COLUMN override_reason TEXT",
    "ALTER TABLE test_results ADD COLUMN override_verdict TEXT",
    "ALTER TABLE test_results ADD COLUMN overridden_by_user_id TEXT",
    "ALTER TABLE test_results ADD COLUMN overridden_by_username TEXT",
    "ALTER TABLE test_results ADD COLUMN overridden_at TIMESTAMP",
    f"ALTER TABLE device_profiles ADD COLUMN auto_generated BOOLEAN DEFAULT {_FALSE_SQL}",
)


def _import_all_models() -> None:
    """Import every model module so Base.metadata is complete."""
    from app.models import (  # noqa: F401
        agent,
        attachment,
        audit_log,
        authorized_network,
        branding,
        device,
        device_profile,
        nessus_finding,
        network_scan,
        project,
        protocol_whitelist,
        refresh_token,
        report_config,
        scan_schedule,
        sync_queue,
        test_plan,
        test_result,
        test_run,
        test_template,
        user,
    )


def _should_skip_schema_ensure() -> bool:
    """Allow tests to bypass runtime migrations and keep in-memory DBs simple."""
    if os.environ.get("EDQ_SKIP_DB_MIGRATIONS") == "1":
        return True
    return settings.DATABASE_URL.startswith("sqlite") and ":memory:" in settings.DATABASE_URL


def _create_missing_indexes(connection) -> None:
    """Backfill indexes for reconciled legacy databases."""
    for table in Base.metadata.sorted_tables:
        for index in table.indexes:
            index.create(bind=connection, checkfirst=True)


def _validate_schema(connection) -> None:
    """Validate that reconciled legacy databases match the ORM shape."""
    inspector = inspect(connection)
    existing_tables = set(inspector.get_table_names())
    expected_tables = set(Base.metadata.tables.keys())

    missing_tables = sorted(expected_tables - existing_tables)
    if missing_tables:
        raise RuntimeError(
            f"Legacy schema reconciliation failed; missing tables: {', '.join(missing_tables)}"
        )

    missing_columns: list[str] = []
    for table_name, table in Base.metadata.tables.items():
        existing_columns = {col["name"] for col in inspector.get_columns(table_name)}
        expected_columns = {column.name for column in table.columns}
        for column_name in sorted(expected_columns - existing_columns):
            missing_columns.append(f"{table_name}.{column_name}")

    if missing_columns:
        raise RuntimeError(
            "Legacy schema reconciliation failed; missing columns: "
            + ", ".join(missing_columns)
        )


def _reconcile_legacy_schema(connection) -> None:
    """Create missing legacy tables/columns before stamping the DB current."""
    _import_all_models()
    Base.metadata.create_all(bind=connection)
    for sql in _LEGACY_SCHEMA_PATCHES:
        try:
            connection.execute(text(sql))
        except Exception:
            pass
    _create_missing_indexes(connection)
    _validate_schema(connection)


def _get_alembic_config() -> Config:
    config = Config(str(_ALEMBIC_INI))
    config.set_main_option("script_location", str(_BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", sync_url)
    return config


def ensure_database_schema_sync() -> None:
    """Ensure the on-disk runtime database is on the current Alembic head.

    Fresh and versioned databases upgrade through Alembic. Unversioned legacy
    databases are first reconciled against the ORM, validated, then stamped as
    current to avoid blindly marking an incomplete schema as healthy.
    """
    if _should_skip_schema_ensure():
        return

    _import_all_models()
    alembic_cfg = _get_alembic_config()

    legacy_needs_stamp = False
    with sync_engine.begin() as connection:
        tables = set(inspect(connection).get_table_names())
        has_version_table = "alembic_version" in tables
        app_tables = tables - {"alembic_version"}

        if app_tables and not has_version_table:
            _reconcile_legacy_schema(connection)
            legacy_needs_stamp = True

    if legacy_needs_stamp:
        command.stamp(alembic_cfg, "head")
        sync_engine.dispose()
        return

    command.upgrade(alembic_cfg, "head")
    with sync_engine.begin() as connection:
        try:
            _validate_schema(connection)
        except RuntimeError:
            if not _is_sqlite:
                raise
            _reconcile_legacy_schema(connection)
    sync_engine.dispose()


async def get_db():
    """Dependency: yield an async database session.

    Always commits on success. SQLAlchemy's autobegin only starts a
    transaction when SQL is first executed, so committing a clean
    session is a no-op. The previous conditional check on session.new /
    session.dirty / session.deleted was unsafe: db.flush() moves objects
    out of session.new into the identity map, causing the commit to be
    skipped even when real changes were pending.
    """
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Async wrapper for runtime schema readiness."""
    await asyncio.to_thread(ensure_database_schema_sync)
