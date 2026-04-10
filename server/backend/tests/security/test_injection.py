"""Tests for input sanitization and injection prevention."""

import pytest
from httpx import AsyncClient

from ..conftest import register_and_login


@pytest.mark.asyncio
async def test_xss_project_name(client: AsyncClient):
    """Project names with XSS payloads should be sanitized on storage.

    After the sanitization fix, HTML tags are stripped from project names
    via sanitize_dict(), so a payload like <img onerror=alert(1) src=x>
    must not appear in the stored value.
    """
    headers = await register_and_login(client, suffix="xss_proj")

    xss_payload = '<img onerror=alert(1) src=x>'
    resp = await client.post(
        "/api/projects/",
        json={"name": xss_payload, "description": "XSS test"},
        headers=headers,
    )
    assert resp.status_code == 201

    data = resp.json()
    stored_name = data["name"]

    # The raw XSS payload must NOT survive sanitization
    assert "<img" not in stored_name, (
        f"XSS payload was stored unescaped: {stored_name!r}"
    )
    assert "onerror" not in stored_name, (
        f"Event handler survived sanitization: {stored_name!r}"
    )
    assert "<script" not in stored_name.lower(), (
        f"Script tag survived sanitization: {stored_name!r}"
    )
