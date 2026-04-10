"""Database engine, session management, and initialization.

Supports both SQLite (default, local dev) and PostgreSQL (production).
Set DATABASE_URL in .env to switch:
  SQLite:      sqlite+aiosqlite:///./data/edq.db
  PostgreSQL:  postgresql+asyncpg://user:pass@host:5432/edq
"""

from sqlalchemy import create_engine, event
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
    """Create all tables on startup (safe for multiple workers)."""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("Tables created successfully.")
    except Exception as e:
        if "already exists" in str(e):
            print("Tables already exist (another worker created them).")
        else:
            raise
