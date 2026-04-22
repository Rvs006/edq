"""Regression tests for synopsis provider configuration and status reporting."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.models.test_run import TestRun as RunModel, TestRunStatus as RunStatus
from app.models.test_template import TestTemplate as TemplateModel
from app.models.user import User
from app.routes import synopsis as synopsis_route
from app.config import settings
from .conftest import register_and_login


async def _create_synopsis_run(db: AsyncSession, engineer_username: str) -> str:
    device = Device(ip_address="10.0.0.55", category="unknown", status="discovered")
    template = TemplateModel(name="synopsis-template", test_ids=[], version="1.0")
    db.add_all([device, template])
    await db.flush()
    user = (
        await db.execute(select(User).where(User.username == engineer_username))
    ).scalar_one()
    run = RunModel(
        device_id=device.id,
        template_id=template.id,
        engineer_id=user.id,
        connection_scenario="test_lab",
        total_tests=0,
        status=RunStatus.COMPLETED,
    )
    db.add(run)
    await db.flush()
    await db.refresh(run)
    return run.id


@pytest.mark.asyncio
async def test_synopsis_requires_complete_server_side_provider_config(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    headers = await register_and_login(client, suffix="synCfg")
    run_id = await _create_synopsis_run(db_session, "synCfguser")
    await db_session.commit()

    monkeypatch.setattr(settings, "AI_API_KEY", "server-provider-key")
    monkeypatch.setattr(settings, "AI_API_URL", "")

    response = await client.post(
        "/api/synopsis/generate",
        json={"test_run_id": run_id},
        headers=headers,
    )

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "AI_API_URL is missing" in detail
    assert "repo-root .env" in detail


@pytest.mark.asyncio
async def test_synopsis_provider_failures_return_operational_message(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    headers = await register_and_login(client, suffix="synFail")
    run_id = await _create_synopsis_run(db_session, "synFailuser")
    await db_session.commit()

    monkeypatch.setattr(settings, "AI_API_KEY", "server-provider-key")
    monkeypatch.setattr(settings, "AI_API_URL", "https://provider.example/v1/responses")

    async def fail_provider(prompt: str) -> str:
        raise synopsis_route.HTTPException(
            status_code=502,
            detail="AI synopsis provider is unreachable from the EDQ server. Check AI_API_URL and outbound network access.",
        )

    monkeypatch.setattr(synopsis_route, "_request_synopsis_from_provider", fail_provider)

    response = await client.post(
        "/api/synopsis/generate",
        json={"test_run_id": run_id},
        headers=headers,
    )

    assert response.status_code == 502
    assert "EDQ server" in response.json()["detail"]


@pytest.mark.asyncio
async def test_admin_system_info_reports_ai_provider_configuration_state(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    headers = await register_and_login(client, suffix="synAdmin", role="admin")
    monkeypatch.setattr(settings, "AI_API_KEY", "server-provider-key")
    monkeypatch.setattr(settings, "AI_API_URL", "")

    response = await client.get("/api/admin/system-info", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["ai_enabled"] is False
    assert payload["ai_status"] == "invalid_configuration"
    assert "AI_API_URL is missing" in payload["ai_message"]
