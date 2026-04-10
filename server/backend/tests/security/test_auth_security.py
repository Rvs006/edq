"""Tests for authentication security: token invalidation on logout and password change."""

import pytest
from httpx import AsyncClient

from tests.conftest import register_and_login


@pytest.mark.asyncio
async def test_logout_invalidates_token(client: AsyncClient):
    """After logout, the previous session token must be rejected.

    The JWT blacklist fix ensures that logging out adds the token to a
    deny-list so subsequent requests with the same cookie return 401.
    """
    headers = await register_and_login(client, suffix="logout_inv")

    # Confirm we can access /me before logout
    me_resp1 = await client.get("/api/auth/me", headers=headers)
    assert me_resp1.status_code == 200

    # Logout
    logout_resp = await client.post("/api/auth/logout", headers=headers)
    assert logout_resp.status_code in (200, 204)

    # After logout, /me should be rejected
    me_resp2 = await client.get("/api/auth/me", headers=headers)
    assert me_resp2.status_code == 401, (
        f"Expected 401 after logout, got {me_resp2.status_code}. "
        "JWT should be blacklisted after logout."
    )


@pytest.mark.asyncio
async def test_session_after_password_change(client: AsyncClient):
    """After changing password, old session tokens must be revoked.

    The fix ensures that password changes invalidate all existing tokens
    for the user, forcing re-authentication.
    """
    headers = await register_and_login(client, suffix="pwchange")

    # Confirm we can access /me before password change
    me_resp1 = await client.get("/api/auth/me", headers=headers)
    assert me_resp1.status_code == 200

    # Change password
    change_resp = await client.post(
        "/api/auth/change-password",
        json={
            "current_password": "TestPass1",
            "new_password": "NewTestPass2",
        },
        headers=headers,
    )
    assert change_resp.status_code in (200, 204)

    # Old session should now be invalid
    me_resp2 = await client.get("/api/auth/me", headers=headers)
    assert me_resp2.status_code == 401, (
        f"Expected 401 after password change, got {me_resp2.status_code}. "
        "Old tokens should be revoked after password change."
    )


@pytest.mark.asyncio
async def test_admin_revoke_sessions_invalidates_access_token(client: AsyncClient):
    """Admin session revocation should invalidate active access tokens immediately."""
    headers = await register_and_login(client, suffix="adminrevoke", role="admin")

    me_resp = await client.get("/api/auth/me", headers=headers)
    assert me_resp.status_code == 200
    user_id = me_resp.json()["id"]

    revoke_resp = await client.post(f"/api/users/{user_id}/revoke-sessions", headers=headers)
    assert revoke_resp.status_code == 200

    me_resp2 = await client.get("/api/auth/me", headers=headers)
    assert me_resp2.status_code == 401, (
        f"Expected 401 after admin session revocation, got {me_resp2.status_code}. "
        "Access tokens should be invalidated immediately."
    )
