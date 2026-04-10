"""Regression tests for scheduled scans and OIDC validation flow."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
import jwt as jose_jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.models.device import Device
from app.models.scan_schedule import ScanSchedule, ScheduleFrequency
from app.models.test_result import TestResult
from app.models.test_run import TestRun, TestRunStatus
from app.models.test_template import TestTemplate
from app.models.user import User
from app.services import scan_scheduler
from app.routes import oidc
from .conftest import register_and_login


async def _create_schedule_fixture(db: AsyncSession, creator_id: str) -> ScanSchedule:
    device = Device(ip_address="10.0.0.77", category="unknown", status="discovered")
    template = TestTemplate(name="schedule-template", test_ids=["U01"], version="1.0")
    db.add_all([device, template])
    await db.flush()
    await db.refresh(device)
    await db.refresh(template)

    schedule = ScanSchedule(
        device_id=device.id,
        template_id=template.id,
        created_by=creator_id,
        frequency=ScheduleFrequency.DAILY,
        next_run_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        is_active=True,
    )
    db.add(schedule)
    await db.flush()
    await db.refresh(schedule)
    return schedule


async def _get_user_id(db: AsyncSession, username: str) -> str:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one().id


@pytest.mark.asyncio
async def test_due_schedule_launches_background_execution(
    client: AsyncClient,
    db_engine,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    await register_and_login(client, suffix="scheduleAdmin", role="admin")
    admin_id = await _get_user_id(db_session, "scheduleAdminuser")
    schedule = await _create_schedule_fixture(db_session, admin_id)
    await db_session.commit()

    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(scan_scheduler, "async_session", session_factory)

    started = asyncio.Event()
    launched: list[str] = []

    def fake_launch(run_id: str):
        launched.append(run_id)

        async def mark_started():
            async with session_factory() as session:
                run = await session.get(TestRun, run_id)
                assert run is not None
                run.status = TestRunStatus.RUNNING
                run.started_at = datetime.now(timezone.utc)
                await session.commit()
            started.set()

        return asyncio.create_task(mark_started())

    monkeypatch.setattr(scan_scheduler, "launch_test_run", fake_launch)

    await scan_scheduler._execute_scheduled_scan(schedule.id)
    await asyncio.wait_for(started.wait(), timeout=1)

    async with session_factory() as verify_session:
        runs_result = await verify_session.execute(
            select(TestRun).where(TestRun.template_id == schedule.template_id)
        )
        runs = runs_result.scalars().all()
        assert len(runs) == 1
        run = runs[0]
        assert run.id in launched
        assert run.status == TestRunStatus.RUNNING
        assert run.started_at is not None

        results_result = await verify_session.execute(
            select(TestResult).where(TestResult.test_run_id == run.id)
        )
        assert len(results_result.scalars().all()) == 1

        refreshed_schedule = await verify_session.get(ScanSchedule, schedule.id)
        assert refreshed_schedule is not None
        assert refreshed_schedule.run_count == 1
        assert refreshed_schedule.last_run_at is not None


@pytest.mark.asyncio
async def test_validate_id_token_uses_verified_claims(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "OIDC_CLIENT_ID", "client-id")

    async def fake_http_get_json(url: str):
        assert url == "https://idp.example/jwks"
        return {"keys": [{"kid": "kid-1", "kty": "RSA"}]}

    def fake_get_unverified_header(token: str):
        assert token == "signed-token"
        return {"alg": "RS256", "kid": "kid-1"}

    def fake_decode(token: str, key: dict, algorithms: list[str], audience: str, issuer: str):
        assert token == "signed-token"
        assert key["kid"] == "kid-1"
        assert algorithms == ["RS256"]
        assert audience == "client-id"
        assert issuer == "https://idp.example"
        return {
            "sub": "oidc-subject",
            "email": "oidc@example.com",
            "nonce": "nonce-123",
        }

    monkeypatch.setattr(oidc, "_http_get_json", fake_http_get_json)
    monkeypatch.setattr(jose_jwt, "get_unverified_header", fake_get_unverified_header)
    monkeypatch.setattr(jose_jwt, "decode", fake_decode)

    claims = await oidc._validate_id_token(
        "signed-token",
        {"jwks_uri": "https://idp.example/jwks", "issuer": "https://idp.example"},
        "nonce-123",
    )

    assert claims["sub"] == "oidc-subject"
    assert claims["email"] == "oidc@example.com"


@pytest.mark.asyncio
async def test_validate_id_token_rejects_nonce_mismatch(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "OIDC_CLIENT_ID", "client-id")

    async def fake_http_get_json(url: str):
        return {"keys": [{"kid": "kid-1", "kty": "RSA"}]}

    monkeypatch.setattr(oidc, "_http_get_json", fake_http_get_json)
    monkeypatch.setattr(
        jose_jwt,
        "get_unverified_header",
        lambda token: {"alg": "RS256", "kid": "kid-1"},
    )
    monkeypatch.setattr(
        jose_jwt,
        "decode",
        lambda *args, **kwargs: {
            "sub": "oidc-subject",
            "email": "oidc@example.com",
            "nonce": "unexpected",
        },
    )

    with pytest.raises(HTTPException) as exc_info:
        await oidc._validate_id_token(
            "signed-token",
            {"jwks_uri": "https://idp.example/jwks", "issuer": "https://idp.example"},
            "nonce-123",
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "OIDC nonce validation failed"


@pytest.mark.asyncio
async def test_oidc_callback_requires_validated_claims_and_nonce(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "OIDC_PROVIDER", "google")
    monkeypatch.setattr(settings, "OIDC_CLIENT_ID", "client-id")
    monkeypatch.setattr(settings, "OIDC_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(settings, "OIDC_ALLOWED_DOMAINS", "")

    async def fake_discovery(provider: str):
        assert provider == "google"
        return {
            "token_endpoint": "https://idp.example/token",
            "issuer": "https://idp.example",
            "jwks_uri": "https://idp.example/jwks",
        }

    async def fake_exchange(code: str, redirect_uri: str, token_endpoint: str, code_verifier: str | None):
        assert code == "code-123"
        assert redirect_uri == "http://test/login"
        assert token_endpoint == "https://idp.example/token"
        assert code_verifier == "v" * 43
        return {"id_token": "signed-token"}

    async def fake_validate(id_token: str, discovery: dict, expected_nonce: str):
        assert id_token == "signed-token"
        assert discovery["issuer"] == "https://idp.example"
        assert expected_nonce == "nonce-123"
        return {
            "email": "oidc@example.com",
            "sub": "oidc-subject",
            "name": "OIDC User",
            "nonce": "nonce-123",
        }

    monkeypatch.setattr(oidc, "_get_oidc_discovery", fake_discovery)
    monkeypatch.setattr(oidc, "_exchange_code_for_tokens", fake_exchange)
    monkeypatch.setattr(oidc, "_validate_id_token", fake_validate)

    resp = await client.post(
        "/api/auth/oidc/callback",
        json={
            "code": "code-123",
            "redirect_uri": "http://test/login",
            "nonce": "nonce-123",
            "code_verifier": "v" * 43,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["user"]["email"] == "oidc@example.com"


@pytest.mark.asyncio
async def test_oidc_callback_rejects_invalid_nonce(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "OIDC_PROVIDER", "google")
    monkeypatch.setattr(settings, "OIDC_CLIENT_ID", "client-id")
    monkeypatch.setattr(settings, "OIDC_CLIENT_SECRET", "client-secret")

    async def fake_discovery(provider: str):
        return {
            "token_endpoint": "https://idp.example/token",
            "issuer": "https://idp.example",
            "jwks_uri": "https://idp.example/jwks",
        }

    async def fake_exchange(code: str, redirect_uri: str, token_endpoint: str, code_verifier: str | None):
        return {"id_token": "signed-token"}

    async def fake_validate(id_token: str, discovery: dict, expected_nonce: str):
        raise HTTPException(status_code=401, detail="OIDC nonce validation failed")

    monkeypatch.setattr(oidc, "_get_oidc_discovery", fake_discovery)
    monkeypatch.setattr(oidc, "_exchange_code_for_tokens", fake_exchange)
    monkeypatch.setattr(oidc, "_validate_id_token", fake_validate)

    resp = await client.post(
        "/api/auth/oidc/callback",
        json={
            "code": "code-123",
            "redirect_uri": "http://test/login",
            "nonce": "bad-nonce",
        },
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "OIDC nonce validation failed"
