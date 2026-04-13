"""Shared helpers and constants for EDQ integration tests."""

import os
import random
import uuid
from pathlib import Path

import httpx

BASE_URL = os.getenv("EDQ_TEST_BASE_URL", "http://localhost:3000")


def _read_root_env(name: str) -> str | None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() == name:
            return value.strip().strip("\"'")
    return None


ADMIN_USER = "admin"
ADMIN_PASS = os.getenv("EDQ_ADMIN_PASS") or _read_root_env("INITIAL_ADMIN_PASSWORD") or "Edq@2026!"
ENGINEER_USER = "pytest_engineer"
ENGINEER_PASS = "Engineer@2026!"
REVIEWER_USER = "pytest_reviewer"
REVIEWER_PASS = "Reviewer@2026!"


def unique_ip() -> str:
    return f"10.99.{random.randint(1, 254)}.{random.randint(1, 254)}"


def unique_forwarded_for() -> str:
    return f"10.250.{random.randint(1, 254)}.{random.randint(1, 254)}"


async def _login(
    username: str,
    password: str,
    *,
    forwarded_for: str | None = None,
) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as c:
        headers = {}
        if forwarded_for is None:
            forwarded_for = unique_forwarded_for()
        if forwarded_for:
            headers["X-Forwarded-For"] = forwarded_for
        resp = await c.post(
            f"{BASE_URL}/api/auth/login",
            json={"username": username, "password": password},
            headers=headers or None,
        )
        assert resp.status_code == 200, f"Login failed for {username}: {resp.text}"
        data = resp.json()
        return {
            "session_cookie": resp.cookies.get("edq_session", ""),
            "csrf_token": data.get("csrf_token", ""),
            "refresh_cookie": resp.cookies.get("edq_refresh", ""),
            "csrf_cookie": resp.cookies.get("edq_csrf", data.get("csrf_token", "")),
            "user": data.get("user", {}),
        }


def _apply_auth(client: httpx.AsyncClient, auth: dict) -> None:
    client.cookies.set("edq_session", auth["session_cookie"])
    if auth.get("refresh_cookie"):
        client.cookies.set("edq_refresh", auth["refresh_cookie"])
    client.cookies.set("edq_csrf", auth.get("csrf_cookie") or auth["csrf_token"])
    client.headers["X-CSRF-Token"] = auth["csrf_token"]
