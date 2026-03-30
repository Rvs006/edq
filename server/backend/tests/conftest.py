"""Shared test fixtures for EDQ backend tests."""

import asyncio
import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import update

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-not-for-production")
os.environ.setdefault("JWT_REFRESH_SECRET", "test-refresh-secret-not-for-production")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("TOOLS_SIDECAR_URL", "http://localhost:8001")
os.environ.setdefault("TOOLS_API_KEY", "test-tools-api-key")
os.environ.setdefault("ALLOW_REGISTRATION", "true")

from app.models.database import Base, get_db
from app.main import create_app
from app.middleware.rate_limit import rate_limiter
from app.models.user import User, UserRole

# Module-level ref so helpers can access the session factory
_session_factory: async_sessionmaker | None = None


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
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
    # Clear rate limiter state between tests
    rate_limiter._buckets.clear()


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
