"""Shared test fixtures for EDQ backend tests."""

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import update

# Force a test-local configuration so pytest does not inherit the repo's
# shared handoff settings from the root .env file.
_TEST_DATABASE_PATH = Path(tempfile.gettempdir()) / f"edq-backend-tests-{os.getpid()}.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DATABASE_PATH.as_posix()}"
os.environ["JWT_SECRET"] = "test-jwt-secret-not-for-production"
os.environ["JWT_REFRESH_SECRET"] = "test-refresh-secret-not-for-production"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["TOOLS_SIDECAR_URL"] = "http://localhost:8001"
os.environ["TOOLS_API_KEY"] = "test-tools-api-key-minimum-32chars-ok"
os.environ["ALLOW_REGISTRATION"] = "true"
os.environ["COOKIE_SECURE"] = "false"
os.environ["DEBUG"] = "true"

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.models.database import Base, get_db
from app.main import create_app
from app.middleware import rate_limit as rate_limit_module
from app.models.user import User, UserRole
from app.services.tools_client import tools_client

# Module-level ref so helpers can access the session factory
_session_factory: async_sessionmaker | None = None


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.run_until_complete(asyncio.sleep(0))
    loop.close()


@pytest_asyncio.fixture
async def db_engine():
    global _session_factory
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    _session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
    _session_factory = None


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_engine) -> AsyncGenerator[AsyncClient, None]:
    app = create_app()

    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    await tools_client.close()
    limiter = getattr(rate_limit_module, "rate_limiter", None)
    if hasattr(limiter, "_buckets"):
        limiter._buckets.clear()


async def register_and_login(
    client: AsyncClient,
    suffix: str = "default",
    role: str = "engineer",
) -> dict:
    """Register a user, optionally promote to admin/reviewer, return CSRF headers."""
    email = f"{suffix}@example.com"
    username = f"{suffix}user"
    reg_resp = await client.post("/api/auth/register", json={
        "email": email,
        "username": username,
        "password": "TestPass1",
        "full_name": f"{suffix.title()} Tester",
    })

    # Promote role if needed via direct DB update
    if role != "engineer" and _session_factory is not None:
        user_id = reg_resp.json().get("id")
        if user_id:
            role_enum = UserRole.ADMIN if role == "admin" else UserRole.REVIEWER
            async with _session_factory() as session:
                await session.execute(
                    update(User).where(User.id == user_id).values(role=role_enum)
                )
                await session.commit()

    resp = await client.post("/api/auth/login", json={
        "username": username,
        "password": "TestPass1",
    })
    csrf = resp.json().get("csrf_token", "")
    return {"X-CSRF-Token": csrf}
