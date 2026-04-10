from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from openpyxl import load_workbook

from app.services import report_generator


def _make_test_run():
    device = SimpleNamespace(
        category="camera",
        manufacturer="Axis",
        model="P3245",
        firmware_version="10.12",
        serial_number="SN-001",
    )
    engineer = SimpleNamespace(full_name="Engineer One")
    return SimpleNamespace(
        id="run-12345678",
        created_at=datetime(2026, 4, 10, tzinfo=timezone.utc),
        completed_at=datetime(2026, 4, 10, tzinfo=timezone.utc),
        overall_verdict="pass",
        connection_scenario="direct",
        device=device,
        engineer=engineer,
        synopsis=None,
    )


def _make_test_result():
    return SimpleNamespace(
        test_id="U01",
        test_name="Network Reachability",
        verdict="pass",
        comment="Device responded as expected.",
        comment_override=None,
        engineer_notes=None,
        override_reason=None,
        is_essential="YES",
    )


def test_generic_template_is_available():
    templates = {item["key"]: item for item in report_generator.get_available_templates()}
    assert templates["generic"]["template_exists"] is True
    assert templates["generic"]["mapping_exists"] is True


@pytest.mark.asyncio
async def test_generate_excel_report_preserves_generic_workbook_structure(tmp_path, monkeypatch):
    monkeypatch.setattr(report_generator.settings, "REPORT_DIR", str(tmp_path))

    output = await report_generator.generate_excel_report(
        _make_test_run(),
        [_make_test_result()],
        template_key="generic",
    )

    workbook = load_workbook(output)
    try:
        assert workbook.sheetnames == [
            "TEST SUMMARY",
            "TESTPLAN",
            "ADDITIONAL INFORMATION",
        ]
    finally:
        workbook.close()
