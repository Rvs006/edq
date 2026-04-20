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


def test_build_report_document_uses_template_mapping_for_layout():
    report = report_generator.build_report_document(
        _make_test_run(),
        [_make_test_result()],
        template_key="pelco_camera",
    )

    assert report.summary_section_title == "TEST SYNOPSIS"
    assert report.testplan_section_title == "TESTPLAN"
    assert report.additional_section_title == "ADDITIONAL INFO"
    assert report.summary_text_label == "Synopsis"
    assert [key for key, _ in report.summary_fields] == [
        "test_attempt",
        "date_range",
        "system",
        "manufacturer",
        "model",
        "firmware",
        "serial",
        "tester_name",
        "overall_result",
    ]
    assert [label for _, label in report.testplan_columns] == [
        "Test Number",
        "Brief Description",
        "Test Description",
        "Essential Pass",
        "Test Result",
        "Test Comments",
        "Engineer Notes",
        "Script Flag",
    ]


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
            "General Test Information",
            "Test Results",
            "Additional Device Information",
        ]
    finally:
        workbook.close()


def test_output_path_uses_full_run_uuid(tmp_path, monkeypatch):
    monkeypatch.setattr(report_generator.settings, "REPORT_DIR", str(tmp_path))
    run = _make_test_run()
    run.id = "12345678-1234-1234-1234-123456789abc"

    path = report_generator._output_path(run, "generic", ".xlsx")

    assert "12345678-1234-1234-1234-123456789abc" in path.name


@pytest.mark.asyncio
@pytest.mark.skipif(not DOCX_AVAILABLE, reason="python-docx not installed in local test environment")
async def test_generate_word_report_includes_template_profile_and_branding(tmp_path, monkeypatch):
    from docx import Document

    monkeypatch.setattr(report_generator.settings, "REPORT_DIR", str(tmp_path))

    output = await report_generator.generate_word_report(
        _make_test_run(),
        [_make_test_result()],
        template_key="pelco_camera",
        branding_settings=_make_branding(),
    )

    document = Document(output)
    full_text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    table_text = "\n".join(cell.text for table in document.tables for row in table.rows for cell in row.cells)

    assert "Verdent QA" in full_text
    assert "Template Profile: Pelco Camera (Rev 2)" in full_text
    assert "IP Device Qualification Report" in full_text
    assert "TEST SYNOPSIS" in full_text
    assert "ADDITIONAL INFO" in full_text
    assert "Essential Pass" in table_text
    assert "Script Flag" in table_text


@pytest.mark.asyncio
@pytest.mark.skipif(not FPDF_AVAILABLE, reason="fpdf2 not installed in local test environment")
async def test_generate_pdf_report_includes_template_profile_and_branding(tmp_path, monkeypatch):
    monkeypatch.setattr(report_generator.settings, "REPORT_DIR", str(tmp_path))
    monkeypatch.setenv("EDQ_USE_LIBREOFFICE", "0")

    output = await report_generator.generate_pdf_report(
        _make_test_run(),
        [_make_test_result()],
        template_key="pelco_camera",
        branding_settings=_make_branding(),
    )

    pdf_bytes = BytesIO(Path(output).read_bytes())
    content = pdf_bytes.getvalue().decode("latin-1", errors="ignore")

    assert "IP DEVICE QUALIFICATION REPORT" in content
    assert "Pelco Camera" in content and "Rev 2" in content
    assert "TEST SYNOPSIS" in content
    assert "ADDITIONAL INFO" in content
    assert "Essential Pass" in content
    assert "Script Flag" in content


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

    assert "TEST SYNOPSIS" in csv_text
    assert "Template Profile" in csv_text
    assert "Device responded as expected." in csv_text
    assert "Readiness Status" in csv_text
    assert "TESTPLAN" in csv_text
    assert "ADDITIONAL INFO" in csv_text
    assert "Synopsis" in csv_text
    assert "Essential Pass" in csv_text
    assert "Script Flag" in csv_text


def _make_test_result_with_notes(notes: str = "Check firmware 1.2.3 manually on next reboot"):
    return SimpleNamespace(
        test_id="U01",
        test_name="Network Reachability",
        verdict="pass",
        comment="Device responded as expected.",
        comment_override=None,
        engineer_notes=notes,
        override_reason=None,
        is_essential="YES",
    )


@pytest.mark.asyncio
async def test_engineer_notes_exported_as_dedicated_csv_column(tmp_path, monkeypatch):
    monkeypatch.setattr(report_generator.settings, "REPORT_DIR", str(tmp_path))
    note = "Check firmware 1.2.3 manually on next reboot"

    output = await report_generator.generate_csv_report(
        _make_test_run(),
        [_make_test_result_with_notes(note)],
        template_key="pelco_camera",
    )

    csv_text = Path(output).read_text(encoding="utf-8")

    assert "Engineer Notes" in csv_text
    assert note in csv_text
    assert "[Engineer Notes:" not in csv_text


def test_engineer_notes_resolved_as_separate_column_in_document():
    report = report_generator.build_report_document(
        _make_test_run(),
        [_make_test_result_with_notes("Inspect after reboot")],
        template_key="pelco_camera",
    )

    attrs = [attr for attr, _ in report.testplan_columns]
    assert "engineer_notes" in attrs
    row = report.rows[0]
    assert row.engineer_notes == "Inspect after reboot"
    assert "[Engineer Notes:" not in row.test_comments


@pytest.mark.asyncio
async def test_excel_export_refreshes_dimension_and_row_spans(tmp_path, monkeypatch):
    import re
    import zipfile

    monkeypatch.setattr(report_generator.settings, "REPORT_DIR", str(tmp_path))

    output = await report_generator.generate_excel_report(
        _make_test_run(),
        [_make_test_result_with_notes("H-col regression fixture")],
        template_key="generic",
    )

    with zipfile.ZipFile(output) as zf:
        sheet = zf.read("xl/worksheets/sheet2.xml").decode()

    dim = re.search(r'<dimension ref="([^"]+)"/>', sheet)
    assert dim is not None
    max_col = dim.group(1).split(":")[1]
    assert re.match(r"^[H-Z]+\d+$", max_col), f"dimension not extended to H+: {dim.group(1)}"

    for m in re.finditer(r'<row r="(\d+)" spans="(\d+):(\d+)"[^>]*>', sheet):
        row_no, low, high = m.group(1), int(m.group(2)), int(m.group(3))
        row_end = sheet.find("</row>", m.end())
        body = sheet[m.end():row_end] if row_end > 0 else ""
        if 'r="H' + row_no + '"' in body:
            assert high >= 8, f"row {row_no} has H cell but spans={low}:{high}"


@pytest.mark.asyncio
async def test_excel_export_strips_template_trash_entries(tmp_path, monkeypatch):
    import zipfile

    monkeypatch.setattr(report_generator.settings, "REPORT_DIR", str(tmp_path))

    output = await report_generator.generate_excel_report(
        _make_test_run(),
        [_make_test_result()],
        template_key="generic",
    )

    with zipfile.ZipFile(output) as zf:
        names = [i.filename for i in zf.infolist()]

    assert not any(n.startswith("[trash]/") for n in names), \
        f"Stray [trash]/ entries survived patching: {names}"


@pytest.mark.asyncio
async def test_engineer_notes_written_to_excel_cell(tmp_path, monkeypatch):
    monkeypatch.setattr(report_generator.settings, "REPORT_DIR", str(tmp_path))
    note = "Manual reboot observation"

    output = await report_generator.generate_excel_report(
        _make_test_run(),
        [_make_test_result_with_notes(note)],
        template_key="generic",
    )

    wb = load_workbook(output)
    try:
        ws = wb["Test Results"]
        header = ws["H10"].value
        assert header == "Engineer Notes"
        column_values = [ws[f"H{row}"].value for row in range(11, 54)]
        assert note in column_values
    finally:
        wb.close()


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
