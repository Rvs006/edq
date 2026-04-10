"""Integration tests verifying compliance framework mappings in test templates."""

import httpx
import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.api]

TEMPLATES_URL = "/api/test-templates/"
LIBRARY_URL = "/api/test-templates/library"


async def _get_test_library(admin_client: httpx.AsyncClient) -> list:
    """Fetch the test library and return the list of available tests."""
    resp = await admin_client.get(LIBRARY_URL)
    if resp.status_code == 404:
        # Fall back: some builds expose the library at the templates endpoint
        resp = await admin_client.get(TEMPLATES_URL)
    assert resp.status_code == 200, f"Cannot fetch test library: {resp.status_code}"
    body = resp.json()
    if isinstance(body, list):
        return body
    return body.get("items", body.get("tests", body.get("templates", [])))


def _has_framework(tests: list, framework_key: str) -> bool:
    """Check whether at least one test in the library references a compliance framework."""
    for test in tests:
        # Check all possible field names for compliance data
        frameworks = (
            test.get("compliance_map")
            or test.get("compliance_frameworks")
            or test.get("frameworks")
            or test.get("compliance")
            or test.get("tags")
            or []
        )
        if isinstance(frameworks, dict):
            if framework_key in frameworks:
                return True
            # Also check dict values for framework names
            for v in frameworks.values():
                if isinstance(v, str) and framework_key.lower() in v.lower():
                    return True
                if isinstance(v, list):
                    for item in v:
                        s = item if isinstance(item, str) else str(item)
                        if framework_key.lower() in s.lower():
                            return True
        elif isinstance(frameworks, list):
            for f in frameworks:
                name = f if isinstance(f, str) else f.get("name", f.get("framework", ""))
                if framework_key.lower() in name.lower():
                    return True
    return False


async def test_iso27001_mapped(admin_client: httpx.AsyncClient):
    """At least one test in the library maps to ISO 27001."""
    tests = await _get_test_library(admin_client)
    if not tests:
        pytest.skip("Test library is empty")
    assert _has_framework(tests, "iso27001") or _has_framework(tests, "ISO 27001"), (
        "No test maps to ISO 27001 compliance framework"
    )


async def test_cyber_essentials_mapped(admin_client: httpx.AsyncClient):
    """At least one test in the library maps to Cyber Essentials."""
    tests = await _get_test_library(admin_client)
    if not tests:
        pytest.skip("Test library is empty")
    assert (
        _has_framework(tests, "cyber_essentials")
        or _has_framework(tests, "Cyber Essentials")
        or _has_framework(tests, "cyber-essentials")
    ), "No test maps to Cyber Essentials compliance framework"


async def test_soc2_mapped(admin_client: httpx.AsyncClient):
    """At least one test in the library maps to SOC 2."""
    tests = await _get_test_library(admin_client)
    if not tests:
        pytest.skip("Test library is empty")
    assert (
        _has_framework(tests, "soc2")
        or _has_framework(tests, "SOC 2")
        or _has_framework(tests, "SOC2")
    ), "No test maps to SOC 2 compliance framework"
