"""Tests for protocol observer settings routes."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import main as main_module
from app.config import settings
from app.models import database as database_module
from app.models.protocol_observer_settings import ProtocolObserverSettings
from .conftest import register_and_login


@pytest.mark.asyncio
async def test_get_protocol_observer_settings_requires_auth(client):
    resp = await client.get("/api/settings/protocol-observer")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_protocol_observer_settings_returns_runtime_defaults(client, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "PROTOCOL_OBSERVER_ENABLED", True)
    monkeypatch.setattr(settings, "PROTOCOL_OBSERVER_DNS_PORT", 53)
    monkeypatch.setattr(settings, "PROTOCOL_OBSERVER_DHCP_OFFER_IP", "")
    headers = await register_and_login(client, suffix="observer-read", role="engineer")

    resp = await client.get("/api/settings/protocol-observer", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] == settings.PROTOCOL_OBSERVER_ENABLED
    assert data["dns_port"] == settings.PROTOCOL_OBSERVER_DNS_PORT
    assert data["dhcp_offer_ip"] == settings.PROTOCOL_OBSERVER_DHCP_OFFER_IP


@pytest.mark.asyncio
async def test_update_protocol_observer_settings_requires_admin(client):
    headers = await register_and_login(client, suffix="observer-user", role="engineer")

    resp = await client.put(
        "/api/settings/protocol-observer",
        json={"dhcp_offer_ip": "192.168.4.68"},
        headers=headers,
    )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_update_protocol_observer_settings_updates_runtime_and_persists(client, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "PROTOCOL_OBSERVER_DNS_PORT", 53)
    monkeypatch.setattr(settings, "PROTOCOL_OBSERVER_DHCP_OFFER_IP", "")
    headers = await register_and_login(client, suffix="observer-admin", role="admin")

    resp = await client.put(
        "/api/settings/protocol-observer",
        json={
            "enabled": True,
            "timeout_seconds": 45,
            "dns_port": 5300,
            "ntp_port": 1123,
            "dhcp_port": 1067,
            "dhcp_offer_ip": "192.168.4.68",
            "dhcp_subnet_mask": "255.255.255.0",
            "dhcp_router_ip": "192.168.4.1",
            "dhcp_dns_server": "192.168.4.1",
            "dhcp_lease_seconds": 600,
        },
        headers=headers,
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["dns_port"] == 5300
    assert payload["dhcp_offer_ip"] == "192.168.4.68"
    assert settings.PROTOCOL_OBSERVER_DNS_PORT == 5300
    assert settings.PROTOCOL_OBSERVER_DHCP_OFFER_IP == "192.168.4.68"

    follow_up = await client.get("/api/settings/protocol-observer", headers=headers)
    assert follow_up.status_code == 200
    data = follow_up.json()
    assert data["ntp_port"] == 1123
    assert data["dhcp_lease_seconds"] == 600


@pytest.mark.asyncio
async def test_load_protocol_observer_settings_from_db_applies_persisted_runtime_values(
    db_engine,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(database_module, "async_session", session_factory)
    monkeypatch.setattr(settings, "PROTOCOL_OBSERVER_ENABLED", True)
    monkeypatch.setattr(settings, "PROTOCOL_OBSERVER_DNS_PORT", 53)
    monkeypatch.setattr(settings, "PROTOCOL_OBSERVER_DHCP_OFFER_IP", "")

    db_session.add(
        ProtocolObserverSettings(
            singleton_key="_",
            enabled=False,
            bind_host="127.0.0.1",
            timeout_seconds=33,
            dns_port=5301,
            ntp_port=1123,
            dhcp_port=1067,
            dhcp_offer_ip="192.168.4.68",
            dhcp_subnet_mask="255.255.255.0",
            dhcp_router_ip="192.168.4.1",
            dhcp_dns_server="192.168.4.1",
            dhcp_lease_seconds=900,
        )
    )
    await db_session.commit()

    await main_module._load_protocol_observer_settings_from_db()

    assert settings.PROTOCOL_OBSERVER_ENABLED is False
    assert settings.PROTOCOL_OBSERVER_BIND_HOST == "127.0.0.1"
    assert settings.PROTOCOL_OBSERVER_DNS_PORT == 5301
    assert settings.PROTOCOL_OBSERVER_DHCP_OFFER_IP == "192.168.4.68"
    assert settings.PROTOCOL_OBSERVER_DHCP_LEASE_SECONDS == 900
