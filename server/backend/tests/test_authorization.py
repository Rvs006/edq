"""Authorization tests — IDOR prevention, role-based access, rate limiting."""

from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from .conftest import register_and_login
from app.middleware.rate_limit import rate_limiter
from app.models.device import Device
from app.models.test_template import TestTemplate as TemplateModel
from app.models.test_run import TestRun as RunModel, TestRunStatus as RunStatus
from app.models.user import User


async def _create_device(db: AsyncSession) -> str:
    """Insert a minimal device and return its ID."""
    device = Device(ip_address="10.0.0.99", category="unknown", status="discovered")
    db.add(device)
    await db.flush()
    await db.refresh(device)
    return device.id


async def _create_template(db: AsyncSession) -> str:
    """Insert a minimal test template and return its ID."""
    tmpl = TemplateModel(name="auth-test-tmpl", test_ids=[], version="1.0")
    db.add(tmpl)
    await db.flush()
    await db.refresh(tmpl)
    return tmpl.id


async def _create_test_run(db: AsyncSession, engineer_id: str, device_id: str, template_id: str) -> str:
    """Insert a test run owned by engineer_id, return its ID."""
    run = RunModel(
        device_id=device_id,
        template_id=template_id,
        engineer_id=engineer_id,
        connection_scenario="test_lab",
        total_tests=0,
        status=RunStatus.PENDING,
    )
    db.add(run)
    await db.flush()
    await db.refresh(run)
    return run.id


async def _get_user_id(db: AsyncSession, username: str) -> str:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one().id


# Helper: register user B, create their test run, then login as user A (the "attacker").
# This ensures A's session cookie is active when making the request.
async def _setup_idor_scenario(client, db_session, suffix):
    """Register user B, create a test run for B, then register+login as A.

    Returns (headers_a, run_id).
    """
    await register_and_login(client, suffix=f"{suffix}B")

    device_id = await _create_device(db_session)
    template_id = await _create_template(db_session)
    user_b_id = await _get_user_id(db_session, f"{suffix}Buser")
    run_id = await _create_test_run(db_session, user_b_id, device_id, template_id)
    await db_session.commit()

    # Login as A last — this sets A's session cookie on the shared client
    headers_a = await register_and_login(client, suffix=f"{suffix}A")
    return headers_a, run_id


# ── IDOR: Engineer cannot access another engineer's test run ─────────────


@pytest.mark.asyncio
async def test_engineer_cannot_get_other_test_run(client: AsyncClient, db_session: AsyncSession):
    """Engineer A cannot GET a test run owned by Engineer B."""
    headers_a, run_id = await _setup_idor_scenario(client, db_session, "idor")

    resp = await client.get(f"/api/test-runs/{run_id}", headers=headers_a)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_engineer_cannot_patch_other_test_run(client: AsyncClient, db_session: AsyncSession):
    """Engineer A cannot PATCH a test run owned by Engineer B."""
    headers_a, run_id = await _setup_idor_scenario(client, db_session, "patch")

    resp = await client.patch(
        f"/api/test-runs/{run_id}",
        json={"status": "completed"},
        headers=headers_a,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_engineer_cannot_start_other_test_run(client: AsyncClient, db_session: AsyncSession):
    """Engineer A cannot start Engineer B's test run."""
    headers_a, run_id = await _setup_idor_scenario(client, db_session, "start")

    resp = await client.post(f"/api/test-runs/{run_id}/start", headers=headers_a)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_engineer_cannot_pause_other_test_run(client: AsyncClient, db_session: AsyncSession):
    """Engineer A cannot pause Engineer B's test run."""
    headers_a, run_id = await _setup_idor_scenario(client, db_session, "pause")

    resp = await client.post(f"/api/test-runs/{run_id}/pause", headers=headers_a)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_engineer_cannot_stop_other_test_run(client: AsyncClient, db_session: AsyncSession):
    """Engineer A cannot complete/stop Engineer B's test run."""
    headers_a, run_id = await _setup_idor_scenario(client, db_session, "stop")

    resp = await client.post(f"/api/test-runs/{run_id}/complete", headers=headers_a)
    assert resp.status_code == 403


# ── Admin CAN access any test run ────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_can_access_any_test_run(client: AsyncClient, db_session: AsyncSession):
    """Admin can GET a test run owned by any engineer."""
    await register_and_login(client, suffix="engAcc")

    device_id = await _create_device(db_session)
    template_id = await _create_template(db_session)
    eng_id = await _get_user_id(db_session, "engAccuser")
    run_id = await _create_test_run(db_session, eng_id, device_id, template_id)
    await db_session.commit()

    # Login as admin last so admin's cookie is active
    admin_headers = await register_and_login(client, suffix="adminAcc", role="admin")

    resp = await client.get(f"/api/test-runs/{run_id}", headers=admin_headers)
    assert resp.status_code == 200


# ── Engineer CAN access own test run ─────────────────────────────────────


@pytest.mark.asyncio
async def test_engineer_can_access_own_test_run(client: AsyncClient, db_session: AsyncSession):
    """Engineer can GET their own test run."""
    headers = await register_and_login(client, suffix="ownRun")

    device_id = await _create_device(db_session)
    template_id = await _create_template(db_session)
    user_id = await _get_user_id(db_session, "ownRunuser")
    run_id = await _create_test_run(db_session, user_id, device_id, template_id)
    await db_session.commit()

    resp = await client.get(f"/api/test-runs/{run_id}", headers=headers)
    assert resp.status_code == 200


# ── IDOR: Engineer cannot generate report for another's test run ─────────


@pytest.mark.asyncio
async def test_engineer_cannot_generate_report_for_other(client: AsyncClient, db_session: AsyncSession):
    """Engineer A cannot generate a report for Engineer B's test run."""
    headers_a, run_id = await _setup_idor_scenario(client, db_session, "rpt")

    resp = await client.post(
        "/api/reports/generate",
        json={"test_run_id": run_id, "report_type": "excel"},
        headers=headers_a,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_engineer_cannot_download_report_for_other(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Engineer A cannot download Engineer B's report by guessing the filename."""
    headers_a, run_id = await _setup_idor_scenario(client, db_session, "rptdl")
    monkeypatch.setattr(settings, "REPORT_DIR", str(tmp_path))

    filename = f"EDQ_Report_{run_id}_generic_20260413_120000.xlsx"
    (tmp_path / filename).write_bytes(b"test report")

    resp = await client.get(f"/api/reports/download/{filename}", headers=headers_a)
    assert resp.status_code == 403


# ── Devices: engineer cannot PATCH devices (admin only) ──────────────────


@pytest.mark.asyncio
async def test_engineer_can_patch_device(client: AsyncClient, db_session: AsyncSession):
    """Any authenticated user can update devices (no role restriction on PATCH)."""
    device_id = await _create_device(db_session)
    await db_session.commit()

    headers = await register_and_login(client, suffix="devEng")

    resp = await client.patch(
        f"/api/devices/{device_id}",
        json={"hostname": "updated"},
        headers=headers,
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_admin_can_patch_device(client: AsyncClient, db_session: AsyncSession):
    """Admin users can update devices."""
    device_id = await _create_device(db_session)
    await db_session.commit()

    headers = await register_and_login(client, suffix="devAdmin", role="admin")

    resp = await client.patch(
        f"/api/devices/{device_id}",
        json={"hostname": "legit-update"},
        headers=headers,
    )
    assert resp.status_code == 200


# ── Users: non-admin cannot list users ───────────────────────────────────


@pytest.mark.asyncio
async def test_engineer_cannot_list_users(client: AsyncClient):
    """Engineers cannot list all users (admin only)."""
    headers = await register_and_login(client, suffix="listEng")
    resp = await client.get("/api/users/", headers=headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_reviewer_cannot_list_users(client: AsyncClient):
    """Reviewers cannot list all users (admin only)."""
    headers = await register_and_login(client, suffix="listRev", role="reviewer")
    resp = await client.get("/api/users/", headers=headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_list_users(client: AsyncClient):
    """Admin can list all users."""
    headers = await register_and_login(client, suffix="listAdmin", role="admin")
    resp = await client.get("/api/users/", headers=headers)
    assert resp.status_code == 200


# ── Rate limiting on report generation ───────────────────────────────────


@pytest.mark.asyncio
async def test_report_generate_rate_limit(client: AsyncClient, db_session: AsyncSession):
    """Report generation should eventually hit rate limiting before auth logic changes it."""
    rate_limiter._buckets.clear()

    headers = await register_and_login(client, suffix="rlRpt")

    device_id = await _create_device(db_session)
    template_id = await _create_template(db_session)
    user_id = await _get_user_id(db_session, "rlRptuser")
    run_id = await _create_test_run(db_session, user_id, device_id, template_id)
    await db_session.commit()

    seen_rate_limit = False
    for i in range(65):
        resp = await client.post(
            "/api/reports/generate",
            json={"test_run_id": run_id, "report_type": "excel"},
            headers=headers,
        )
        if resp.status_code == 429:
            seen_rate_limit = True
            break
        assert resp.status_code in {200, 404, 409, 500}, (
            f"Unexpected status before rate limit on request {i + 1}: {resp.status_code}"
        )

    assert seen_rate_limit, "Expected report generation to hit a rate limit after repeated requests"


# ── Request ID middleware ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_request_id_header_present(client: AsyncClient):
    """Every response should include an X-Request-ID header."""
    resp = await client.get("/api/health")
    assert "X-Request-ID" in resp.headers
    # Should be a valid UUID-like string
    assert len(resp.headers["X-Request-ID"]) >= 32


@pytest.mark.asyncio
async def test_request_id_echoed_when_provided(client: AsyncClient):
    """When client sends X-Request-ID, it should be echoed back."""
    custom_id = "test-req-12345"
    resp = await client.get("/api/health", headers={"X-Request-ID": custom_id})
    assert resp.headers.get("X-Request-ID") == custom_id


# ── IDOR: Engineer cannot access nessus endpoints on another's run ────


@pytest.mark.asyncio
async def test_engineer_cannot_upload_nessus_for_other(client: AsyncClient, db_session: AsyncSession):
    """Engineer A cannot upload a nessus file to Engineer B's test run."""
    headers_a, run_id = await _setup_idor_scenario(client, db_session, "nup")

    # Simulate a file upload (will fail at auth before file parsing)
    resp = await client.post(
        f"/api/test-runs/{run_id}/nessus/upload",
        files={"file": ("scan.nessus", b"<xml>fake</xml>", "text/xml")},
        headers=headers_a,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_engineer_cannot_list_nessus_findings_for_other(client: AsyncClient, db_session: AsyncSession):
    """Engineer A cannot list nessus findings for Engineer B's test run."""
    headers_a, run_id = await _setup_idor_scenario(client, db_session, "nfind")

    resp = await client.get(f"/api/test-runs/{run_id}/nessus/findings", headers=headers_a)
    assert resp.status_code == 403


# ── Reviewer CAN access any test run ─────────────────────────────────


@pytest.mark.asyncio
async def test_reviewer_can_access_any_test_run(client: AsyncClient, db_session: AsyncSession):
    """Reviewer can GET a test run owned by any engineer."""
    await register_and_login(client, suffix="engRev")

    device_id = await _create_device(db_session)
    template_id = await _create_template(db_session)
    eng_id = await _get_user_id(db_session, "engRevuser")
    run_id = await _create_test_run(db_session, eng_id, device_id, template_id)
    await db_session.commit()

    reviewer_headers = await register_and_login(client, suffix="revAcc", role="reviewer")

    resp = await client.get(f"/api/test-runs/{run_id}", headers=reviewer_headers)
    assert resp.status_code == 200


# ── IDOR: Synopsis generation ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_engineer_cannot_generate_synopsis_for_other(client: AsyncClient, db_session: AsyncSession):
    """Engineer A cannot generate a synopsis for Engineer B's test run."""
    headers_a, run_id = await _setup_idor_scenario(client, db_session, "syn")

    resp = await client.post(
        "/api/synopsis/generate",
        json={"test_run_id": run_id},
        headers=headers_a,
    )
    # Should be 403 (access denied) — not 503 (AI not configured)
    assert resp.status_code == 403


# ── IDOR: List endpoint scoping ───────────────────────────────────────


@pytest.mark.asyncio
async def test_engineer_list_only_own_test_runs(client: AsyncClient, db_session: AsyncSession):
    """GET /test-runs/ should return only the engineer's own runs."""
    # Create a run owned by user B
    await register_and_login(client, suffix="listB")
    device_id = await _create_device(db_session)
    template_id = await _create_template(db_session)
    user_b_id = await _get_user_id(db_session, "listBuser")
    await _create_test_run(db_session, user_b_id, device_id, template_id)
    await db_session.commit()

    # Login as A and list — should not see B's run
    headers_a = await register_and_login(client, suffix="listA")
    resp = await client.get("/api/test-runs/", headers=headers_a)
    assert resp.status_code == 200
    runs = resp.json()
    user_a_id = await _get_user_id(db_session, "listAuser")
    for run in runs:
        assert run["engineer_id"] == user_a_id, "Engineer should only see own test runs"


# ── Change-password rate limit ────────────────────────────────────────


@pytest.mark.asyncio
async def test_change_password_rate_limit(client: AsyncClient):
    """Change-password should be rate-limited to 3/min."""
    rate_limiter._buckets.clear()

    headers = await register_and_login(client, suffix="cpRL")

    # Fire 3 requests (will fail with wrong password, but should not be 429)
    for i in range(3):
        resp = await client.post(
            "/api/auth/change-password",
            json={"current_password": "WrongPass1", "new_password": "NewPass123"},
            headers=headers,
        )
        assert resp.status_code != 429, f"Request {i+1} should not be rate-limited"

    # 4th request should be rate-limited
    resp = await client.post(
        "/api/auth/change-password",
        json={"current_password": "WrongPass1", "new_password": "NewPass123"},
        headers=headers,
    )
    assert resp.status_code == 429
