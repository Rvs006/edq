"""Tests for audit log routes."""

import pytest
from httpx import AsyncClient

from tests.conftest import register_and_login


@pytest.mark.asyncio
async def test_list_audit_logs(client: AsyncClient):
    """List audit logs returns paginated structure."""
    headers = await register_and_login(client, "auditlist", role="admin")
    resp = await client.get("/api/audit-logs/", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_audit_logs_pagination(client: AsyncClient):
    """Audit logs support skip/limit pagination."""
    headers = await register_and_login(client, "auditpage", role="admin")
    resp = await client.get("/api/audit-logs/?skip=0&limit=10", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["skip"] == 0
    assert data["limit"] == 10


@pytest.mark.asyncio
async def test_audit_logs_filter_by_action(client: AsyncClient):
    """Audit logs can be filtered by action."""
    headers = await register_and_login(client, "auditfilter", role="admin")
    resp = await client.get("/api/audit-logs/?action=login", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_audit_logs_export_csv(client: AsyncClient):
    """Audit logs CSV export returns proper content type."""
    headers = await register_and_login(client, "auditcsv", role="admin")
    resp = await client.get("/api/audit-logs/export", headers=headers)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_compliance_summary(client: AsyncClient):
    """Compliance summary endpoint returns framework data."""
    headers = await register_and_login(client, "auditcomp", role="admin")
    resp = await client.get("/api/audit-logs/compliance-summary", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "frameworks" in data
    assert "ISO 27001" in data["frameworks"]
    assert "Cyber Essentials" in data["frameworks"]
