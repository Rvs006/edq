from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import importlib.util

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


def _make_branding():
    return SimpleNamespace(
        company_name="Verdent QA",
        primary_color="#123456",
        footer_text="Confidential Qualification Report",
        logo_path="",
    )


DOCX_AVAILABLE = importlib.util.find_spec("docx") is not None
FPDF_AVAILABLE = importlib.util.find_spec("fpdf") is not None


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


@pytest.mark.asyncio
@pytest.mark.skipif(not DOCX_AVAILABLE, reason="python-docx not installed in local test environment")
async def test_generate_word_report_includes_template_profile_and_branding(tmp_path, monkeypatch):
    from docx import Document

    monkeypatch.setattr(report_generator.settings, "REPORT_DIR", str(tmp_path))

    output = await report_generator.generate_word_report(
        _make_test_run(),
        [_make_test_result()],
        template_key="generic",
        branding_settings=_make_branding(),
    )

    document = Document(output)
    full_text = "\n".join(paragraph.text for paragraph in document.paragraphs)

    assert "Verdent QA" in full_text
    assert "Template Profile: Generic IP Device (Rev00 C00)" in full_text
    assert "IP Device Qualification Report" in full_text


@pytest.mark.asyncio
@pytest.mark.skipif(not FPDF_AVAILABLE, reason="fpdf2 not installed in local test environment")
async def test_generate_pdf_report_includes_template_profile_and_branding(tmp_path, monkeypatch):
    monkeypatch.setattr(report_generator.settings, "REPORT_DIR", str(tmp_path))
    monkeypatch.setenv("EDQ_USE_LIBREOFFICE", "0")

    output = await report_generator.generate_pdf_report(
        _make_test_run(),
        [_make_test_result()],
        template_key="generic",
        branding_settings=_make_branding(),
    )

    pdf_bytes = BytesIO(Path(output).read_bytes())
    content = pdf_bytes.getvalue().decode("latin-1", errors="ignore")

    assert "IP DEVICE QUALIFICATION REPORT" in content


@pytest.mark.asyncio
async def test_generate_csv_report_uses_template_profile_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(report_generator.settings, "REPORT_DIR", str(tmp_path))

    output = await report_generator.generate_csv_report(
        _make_test_run(),
        [_make_test_result()],
        template_key="pelco_camera",
        branding_settings=_make_branding(),
    )

    csv_text = Path(output).read_text(encoding="utf-8")

    assert "TEST SUMMARY" in csv_text
    assert "Template Profile" in csv_text
    assert "Device responded as expected." in csv_text
    assert "Readiness Status" in csv_text


def test_build_report_document_includes_readiness_summary():
    report = report_generator.build_report_document(
        _make_test_run(),
        [_make_test_result()],
        template_key="generic",
        readiness_summary={
            "score": 9,
            "level": "conditional",
            "label": "Operational with advisories",
            "report_ready": True,
            "operational_ready": False,
            "blocking_issue_count": 0,
            "pending_manual_count": 0,
            "release_blocking_failure_count": 0,
            "review_required_issue_count": 0,
            "manual_evidence_pending_count": 0,
            "advisory_count": 1,
            "override_count": 0,
            "failed_test_count": 0,
            "completed_result_count": 1,
            "total_result_count": 1,
            "trust_tier_counts": {
                "release_blocking": 1,
                "review_required": 0,
                "advisory": 0,
                "manual_evidence": 0,
            },
            "next_step": "Issue the report with the advisory notes and follow-up actions captured.",
            "reasons": ["1 advisory finding should be called out in the report."],
            "summary": "Operational with advisories (9/10). 1 advisory finding should be called out in the report.",
        },
    )

    assert report.readiness_summary["score"] == 9
    assert "Readiness status: Operational with advisories (9/10)." in report.metadata["summary_text"]
    assert "Official Report Ready: Yes" in report.additional_sections[1].body
