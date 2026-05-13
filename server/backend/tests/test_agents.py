"""Compatibility tests for legacy agent handshake routes."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from .conftest import register_and_login


async def _register_agent(client: AsyncClient) -> dict:
    headers = await register_and_login(client, suffix="agentadmin", role="admin")
    response = await client.post(
        "/api/agent/register",
        json={
            "name": "Lab Runner",
            "hostname": "lab-runner.local",
            "platform": "windows",
            "agent_version": "1.0.0",
            "capabilities": {"nmap": True},
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_legacy_agent_register_alias_works(client: AsyncClient, db_session: AsyncSession):
    payload = await _register_agent(client)

    assert payload["name"] == "Lab Runner"
    assert payload["api_key"]
    assert payload["api_key_prefix"] == payload["api_key"][:8]

    result = await db_session.execute(select(Agent).where(Agent.id == payload["id"]))
    agent = result.scalar_one()
    assert agent.name == "Lab Runner"
    assert agent.hostname == "lab-runner.local"


@pytest.mark.asyncio
async def test_legacy_agent_heartbeat_accepts_bearer_auth_and_returns_version_status(
    client: AsyncClient,
    db_session: AsyncSession,
):
    payload = await _register_agent(client)
    client.cookies.clear()

    response = await client.post(
        "/api/agent/heartbeat",
        json={
            "status": "busy",
            "current_task": "run-123",
            "ip_address": "192.168.1.44",
            "agent_version": "0.9.8",
            "capabilities": {"nmap": True, "testssl": False},
        },
        headers={"Authorization": f"Bearer {payload['api_key']}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["agent_id"] == payload["id"]
    assert body["version_status"] == "incompatible"
    assert body["min_agent_version"] == "1.0.0"
    assert body["server_version"] == "1.0.0"

    result = await db_session.execute(select(Agent).where(Agent.id == payload["id"]))
    agent = result.scalar_one()
    assert agent.status == "busy"
    assert agent.current_task == "run-123"
    assert agent.ip_address == "192.168.1.44"
    assert agent.agent_version == "0.9.8"
    assert agent.capabilities == {"nmap": True, "testssl": False}
    assert agent.last_heartbeat is not None


@pytest.mark.asyncio
async def test_agent_heartbeat_requires_authentication(client: AsyncClient):
    response = await client.post("/api/agent/heartbeat", json={"status": "online"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Agent authentication required"
