"""Report Generation Engine — Excel and Word report generation.

Template-based Excel generation: opens actual .xlsx template files using
openpyxl.load_workbook(), fills in data cells, and saves. This preserves
all formatting, merged cells, borders, colours, conditional formatting,
and logos from the original Electracom templates.

Fallback scratch generation available when template files are missing.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from app.config import settings

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "templates"
_MAPPINGS_DIR = Path(__file__).resolve().parent / "cell_mappings"

TEMPLATE_FILES = {
    "pelco_camera": "1TS - Pelco SMLE1-15V5-3H Camera Device Qualification Rev 2.xlsx",
    "easyio_controller": "EasyIO FW08 - Device Testing Plan - v1.1.xlsx",
    "generic": "[MANUFACTURER] - [MODEL] - IP Device Qualification Template C00 - ADDED SCRIPT NO YES 1.xlsx",
}

TEMPLATE_INFO = {
    "pelco_camera": {
        "name": "Pelco Camera (Rev 2)",
        "device_category": "camera",
        "description": "Pelco SMLE1-15V5-3H camera qualification template with 31 tests",
    },
    "easyio_controller": {
        "name": "EasyIO Controller (FW08)",
        "device_category": "controller",
        "description": "EasyIO FW-08 controller testing plan with 46 tests and protocol whitelist",
    },
    "generic": {
        "name": "Generic IP Device (C00)",
        "device_category": "generic",
        "description": "Universal IP device qualification template with 43 tests",
    },
}


def _format_date_range(test_run) -> str:
    fmt = "%d/%m/%Y"
    start = test_run.started_at or test_run.created_at
    end = test_run.completed_at or datetime.now(timezone.utc)
    start_str = start.strftime(fmt) if start else ""
    end_str = end.strftime(fmt) if end else ""
    return f"{start_str} - {end_str}"


_DEFAULT_VERDICT_MAP = {
    "pass": "PASS",
    "fail": "FAIL",
    "advisory": "ADVISORY",
    "na": "N/A",
    "info": "INFO",
    "error": "ERROR",
    "pending": "PENDING",
    "running": "RUNNING",
}


def _resolve_verdict(result, verdict_map: dict) -> str:
    raw = result.verdict.value if hasattr(result.verdict, "value") else str(result.verdict)
    effective_map = verdict_map if verdict_map else _DEFAULT_VERDICT_MAP
    return effective_map.get(raw, raw.upper())


def _resolve_script_flag(result) -> str:
    tier = result.tier.value if hasattr(result.tier, "value") else str(result.tier)
    return "Yes" if tier == "automatic" else "No"


def _resolve_comment(result) -> str:
    return result.comment_override or result.comment or ""


def _safe_attr(obj, attr: str, default: str = "") -> str:
    val = getattr(obj, attr, None)
    if val is None:
        return default
    return str(val)


def get_available_templates() -> list:
    available = []
    for key, info in TEMPLATE_INFO.items():
        template_file = _TEMPLATES_DIR / TEMPLATE_FILES[key]
        mapping_file = _MAPPINGS_DIR / f"{key}.json"
        available.append({
            "key": key,
            "name": info["name"],
            "device_category": info["device_category"],
            "description": info["description"],
            "template_exists": template_file.exists(),
            "mapping_exists": mapping_file.exists(),
        })
    return available


async def generate_excel_report(
    test_run,
    test_results,
    report_config=None,
    template_key: str = "generic",
) -> str:
    """Generate Excel report by filling actual template file.

    Opens the real .xlsx template with load_workbook (data_only=False to
    preserve formulas), writes metadata + test results into the mapped
    cells, and saves to the reports directory.

    Callers must pass a valid key from TEMPLATE_FILES ("generic",
    "pelco_camera", or "easyio_controller"). The routes layer enforces
    this via Pydantic Literal validation, so invalid keys are rejected
    with a 422 before reaching this function.

    Falls back to scratch generation only if the on-disk template or
    mapping file is physically missing (e.g. deleted after deployment).
    """
    if template_key not in TEMPLATE_FILES:
        raise ValueError(
            f"Unknown template_key '{template_key}'. "
            f"Valid keys: {', '.join(TEMPLATE_FILES.keys())}"
        )

    template_file = _TEMPLATES_DIR / TEMPLATE_FILES[template_key]
    mapping_file = _MAPPINGS_DIR / f"{template_key}.json"

    if not template_file.exists() or not mapping_file.exists():
        logger.warning(
            "Template or mapping missing for '%s' (template=%s, mapping=%s). "
            "Falling back to scratch generation.",
            template_key,
            template_file.exists(),
            mapping_file.exists(),
        )
        return await generate_excel_report_scratch(test_run, test_results, report_config)

    from openpyxl import load_workbook

    mapping = json.loads(mapping_file.read_text())
    wb = load_workbook(str(template_file))  # data_only=False preserves formulas

    device = getattr(test_run, "device", None)
    engineer = getattr(test_run, "engineer", None)

    # --- Fill synopsis / summary sheet metadata ---
    synopsis_ws = wb[mapping["synopsis_sheet"]]
    meta = mapping["metadata_cells"]

    metadata_values = {
        "test_attempt": "1",
        "date_range": _format_date_range(test_run),
        "system": _safe_attr(device, "category", ""),
        "manufacturer": _safe_attr(device, "manufacturer"),
        "model": _safe_attr(device, "model"),
        "firmware": _safe_attr(device, "firmware_version"),
        "serial": "",
        "tester_name": _safe_attr(engineer, "full_name"),
        "overall_result": (test_run.overall_verdict.value if hasattr(test_run.overall_verdict, "value") else str(test_run.overall_verdict or "INCOMPLETE")).upper(),
        "synopsis_text": test_run.synopsis or "",
    }

    if template_key == "easyio_controller":
        start_dt = test_run.started_at or test_run.created_at
        end_dt = test_run.completed_at or datetime.now(timezone.utc)
        if start_dt and hasattr(start_dt, "tzinfo") and start_dt.tzinfo is not None:
            start_dt = start_dt.replace(tzinfo=None)
        if end_dt and hasattr(end_dt, "tzinfo") and end_dt.tzinfo is not None:
            end_dt = end_dt.replace(tzinfo=None)
        metadata_values["start_date"] = start_dt
        metadata_values["end_date"] = end_dt

    for field_key, cell_addr in meta.items():
        if cell_addr and field_key in metadata_values:
            value = metadata_values[field_key]
            try:
                synopsis_ws[cell_addr] = value
            except Exception:
                logger.warning("Could not write to cell %s in synopsis sheet", cell_addr)

    # --- Fill test results into testplan sheet ---
    testplan_ws = wb[mapping["testplan_sheet"]]
    cols = mapping["testplan_columns"]
    verdict_map = mapping.get("verdict_map", {})
    start_row = mapping["testplan_start_row"]

    for i, result in enumerate(test_results):
        row = start_row + i

        if cols.get("test_result"):
            testplan_ws[f"{cols['test_result']}{row}"] = _resolve_verdict(result, verdict_map)
        if cols.get("test_comments"):
            testplan_ws[f"{cols['test_comments']}{row}"] = _resolve_comment(result)
        if cols.get("script_flag"):
            testplan_ws[f"{cols['script_flag']}{row}"] = _resolve_script_flag(result)

    # --- Save output ---
    output_dir = Path(settings.REPORT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"EDQ_Report_{test_run.id[:8]}_{template_key}_{timestamp}.xlsx"
    output_path = output_dir / filename
    wb.save(str(output_path))
    logger.info("Template-based Excel report saved: %s", output_path)
    return str(output_path)


async def generate_excel_report_scratch(test_run, test_results, report_config=None) -> str:
    """Fallback: generate an Excel report from scratch when no template is available.

    Creates a basic formatted workbook with Summary and Test Results sheets.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = Workbook()

    ws_summary = wb.active
    ws_summary.title = "Summary"
    ws_summary.column_dimensions["A"].width = 25
    ws_summary.column_dimensions["B"].width = 40

    header_font = Font(name="Calibri", size=14, bold=True, color="1F4E79")
    label_font = Font(name="Calibri", size=11, bold=True)
    value_font = Font(name="Calibri", size=11)

    ws_summary["A1"] = "EDQ Device Qualification Report"
    ws_summary["A1"].font = Font(name="Calibri", size=18, bold=True, color="1F4E79")

    ws_summary["A3"] = "Test Run ID"
    ws_summary["A3"].font = label_font
    ws_summary["B3"] = test_run.id
    ws_summary["B3"].font = value_font

    ws_summary["A4"] = "Device ID"
    ws_summary["A4"].font = label_font
    ws_summary["B4"] = test_run.device_id

    ws_summary["A5"] = "Overall Verdict"
    ws_summary["A5"].font = label_font
    verdict_str = str(test_run.overall_verdict) if test_run.overall_verdict else "Incomplete"
    ws_summary["B5"] = verdict_str.upper()
    verdict_colors = {"pass": "27AE60", "fail": "E74C3C", "advisory": "F39C12"}
    ws_summary["B5"].font = Font(
        name="Calibri", size=11, bold=True, color=verdict_colors.get(verdict_str, "000000")
    )

    ws_summary["A7"] = "Tests Passed"
    ws_summary["B7"] = test_run.passed_tests
    ws_summary["A8"] = "Tests Failed"
    ws_summary["B8"] = test_run.failed_tests
    ws_summary["A9"] = "Advisories"
    ws_summary["B9"] = test_run.advisory_tests
    ws_summary["A10"] = "N/A"
    ws_summary["B10"] = test_run.na_tests
    ws_summary["A11"] = "Total Tests"
    ws_summary["B11"] = test_run.total_tests

    ws_summary["A13"] = "Generated"
    ws_summary["B13"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    ws_results = wb.create_sheet("Test Results")
    headers = ["Test ID", "Test Name", "Tier", "Tool", "Essential", "Verdict", "Comment", "Compliance"]
    ws_results.column_dimensions["A"].width = 10
    ws_results.column_dimensions["B"].width = 35
    ws_results.column_dimensions["C"].width = 15
    ws_results.column_dimensions["D"].width = 12
    ws_results.column_dimensions["E"].width = 10
    ws_results.column_dimensions["F"].width = 12
    ws_results.column_dimensions["G"].width = 50
    ws_results.column_dimensions["H"].width = 30

    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    header_font_white = Font(name="Calibri", size=11, bold=True, color="FFFFFF")

    for col, header in enumerate(headers, 1):
        cell = ws_results.cell(row=1, column=col, value=header)
        cell.font = header_font_white
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    verdict_fills = {
        "pass": PatternFill(start_color="D5F5E3", end_color="D5F5E3", fill_type="solid"),
        "fail": PatternFill(start_color="FADBD8", end_color="FADBD8", fill_type="solid"),
        "advisory": PatternFill(start_color="FEF9E7", end_color="FEF9E7", fill_type="solid"),
        "na": PatternFill(start_color="EAEDED", end_color="EAEDED", fill_type="solid"),
    }

    for row_idx, result in enumerate(test_results, 2):
        verdict_val = result.verdict.value if hasattr(result.verdict, "value") else str(result.verdict)
        tier_val = result.tier.value if hasattr(result.tier, "value") else str(result.tier)
        compliance = ", ".join(result.compliance_map) if result.compliance_map else ""

        ws_results.cell(row=row_idx, column=1, value=result.test_id)
        ws_results.cell(row=row_idx, column=2, value=result.test_name)
        ws_results.cell(row=row_idx, column=3, value=tier_val)
        ws_results.cell(row=row_idx, column=4, value=result.tool or "—")
        ws_results.cell(row=row_idx, column=5, value=result.is_essential.upper())
        verdict_cell = ws_results.cell(row=row_idx, column=6, value=verdict_val.upper())
        verdict_cell.fill = verdict_fills.get(verdict_val, PatternFill())
        ws_results.cell(row=row_idx, column=7, value=result.comment_override or result.comment or "")
        ws_results.cell(row=row_idx, column=8, value=compliance)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"EDQ_Report_{test_run.id[:8]}_scratch_{timestamp}.xlsx"
    file_path = os.path.join(settings.REPORT_DIR, filename)
    wb.save(file_path)
    logger.info("Scratch Excel report saved: %s", file_path)
    return file_path


async def generate_word_report(test_run, test_results, report_config=None, include_synopsis=False) -> str:
    """Generate a Word report for a test run.

    Uses python-docx to create a formatted Word document.
    """
    from docx import Document
    from docx.shared import Pt
    from docx.shared import RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()

    title = doc.add_heading("EDQ Device Qualification Report", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_heading("Executive Summary", level=1)
    verdict_str = str(test_run.overall_verdict) if test_run.overall_verdict else "Incomplete"
    summary = doc.add_paragraph()
    summary.add_run("Overall Verdict: ").bold = True
    verdict_run = summary.add_run(verdict_str.upper())
    verdict_run.bold = True
    if verdict_str == "pass":
        verdict_run.font.color.rgb = RGBColor(39, 174, 96)
    elif verdict_str == "fail":
        verdict_run.font.color.rgb = RGBColor(231, 76, 60)
    elif verdict_str == "advisory":
        verdict_run.font.color.rgb = RGBColor(243, 156, 18)

    doc.add_paragraph(f"Test Run: {test_run.id}")
    doc.add_paragraph(f"Device: {test_run.device_id}")
    doc.add_paragraph(
        f"Tests: {test_run.passed_tests} passed, {test_run.failed_tests} failed, "
        f"{test_run.advisory_tests} advisories out of {test_run.total_tests} total"
    )

    if include_synopsis and test_run.synopsis:
        doc.add_heading("Synopsis", level=1)
        doc.add_paragraph(test_run.synopsis)

    doc.add_heading("Test Results", level=1)
    table = doc.add_table(rows=1, cols=5)
    table.style = "Table Grid"
    headers = ["Test ID", "Test Name", "Essential", "Verdict", "Comment"]
    for i, header in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = header
        for paragraph in cell.paragraphs:
            for run in paragraph.runs:
                run.font.bold = True

    for result in test_results:
        row = table.add_row()
        verdict_val = result.verdict.value if hasattr(result.verdict, "value") else str(result.verdict)
        row.cells[0].text = result.test_id
        row.cells[1].text = result.test_name
        row.cells[2].text = result.is_essential.upper()
        row.cells[3].text = verdict_val.upper()
        row.cells[4].text = result.comment_override or result.comment or ""

    doc.add_heading("Compliance Mapping", level=1)
    doc.add_paragraph("This report maps test results to the following compliance frameworks:")
    doc.add_paragraph("• ISO 27001 — Information Security Management")
    doc.add_paragraph("• Cyber Essentials — UK Government Cyber Security Standard")
    doc.add_paragraph("• SOC2 — Service Organization Control 2")

    doc.add_paragraph()
    footer = doc.add_paragraph()
    footer.add_run(
        f"Report generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    ).italic = True

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"EDQ_Report_{test_run.id[:8]}_{timestamp}.docx"
    file_path = os.path.join(settings.REPORT_DIR, filename)
    doc.save(file_path)
    return file_path
