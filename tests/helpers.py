"""Shared helpers and constants for EDQ integration tests."""

import os
import random

import httpx

BASE_URL = os.getenv("EDQ_TEST_BASE_URL", "http://localhost:3000")

ADMIN_USER = "admin"
ADMIN_PASS = "Edq@2026!"
ENGINEER_USER = "pytest_engineer"
ENGINEER_PASS = "Engineer@2026!"
REVIEWER_USER = "pytest_reviewer"
REVIEWER_PASS = "Reviewer@2026!"


def unique_ip() -> str:
    """Generate a unique private IP in the 10.99.x.x range."""
    return f"10.99.{random.randint(1, 254)}.{random.randint(1, 254)}"


async def _login(username: str, password: str) -> dict:
    """Login and return dict with session_cookie, csrf_token, refresh_cookie."""
    async with httpx.AsyncClient(timeout=30.0) as c:
        resp = await c.post(
            f"{BASE_URL}/api/auth/login",
            json={"username": username, "password": password},
        )
        assert resp.status_code == 200, f"Login failed for {username}: {resp.text}"
        data = resp.json()
        return {
            "session_cookie": resp.cookies.get("edq_session", ""),
            "csrf_token": data.get("csrf_token", ""),
            "refresh_cookie": resp.cookies.get("edq_refresh", ""),
            "user": data.get("user", {}),
        }


def _apply_auth(client: httpx.AsyncClient, auth: dict) -> None:
    """Apply session cookie, CSRF cookie+header to a client."""
    client.cookies.set("edq_session", auth["session_cookie"])
    if auth.get("refresh_cookie"):
        client.cookies.set("edq_refresh", auth["refresh_cookie"])
    # CSRF middleware checks that edq_csrf cookie == X-CSRF-Token header
    client.cookies.set("edq_csrf", auth["csrf_token"])
    client.headers["X-CSRF-Token"] = auth["csrf_token"]
