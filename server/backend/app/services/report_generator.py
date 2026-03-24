"""Report Generation Engine — Excel, Word, and PDF report generation.

Template-based Excel generation: opens actual .xlsx template files using
openpyxl.load_workbook(), fills in data cells, and saves. This preserves
all formatting, merged cells, borders, colours, conditional formatting,
and logos from the original Electracom templates.

Word generation uses python-docx with styled cover page, executive summary,
color-coded results table, detailed findings for FAIL/ADVISORY, and
protocol whitelist comparison.

PDF generation converts the Word doc using LibreOffice headless.

Fallback scratch generation available when template files are missing.
"""

import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

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

_DEFAULT_VERDICT_MAP = {
    "pass": "PASS",
    "qualified_pass": "QUALIFIED PASS",
    "fail": "FAIL",
    "advisory": "ADVISORY",
    "na": "N/A",
    "info": "INFO",
    "error": "ERROR",
    "pending": "PENDING",
    "running": "RUNNING",
    "incomplete": "INCOMPLETE",
}

_OVERALL_VERDICT_MAP = {
    "pass": "PASS",
    "qualified_pass": "QUALIFIED PASS",
    "fail": "FAIL",
    "incomplete": "INCOMPLETE",
}


def _format_date_range(test_run) -> str:
    fmt = "%d/%m/%Y"
    start = test_run.started_at or test_run.created_at
    end = test_run.completed_at or datetime.now(timezone.utc)
    start_str = start.strftime(fmt) if start else ""
    end_str = end.strftime(fmt) if end else ""
    return f"{start_str} - {end_str}"


def _resolve_verdict(result, verdict_map: dict) -> str:
    raw = result.verdict.value if hasattr(result.verdict, "value") else str(result.verdict)
    effective_map = verdict_map if verdict_map else _DEFAULT_VERDICT_MAP
    return effective_map.get(raw, raw.upper())


def _resolve_overall_verdict(test_run) -> str:
    raw = test_run.overall_verdict.value if hasattr(test_run.overall_verdict, "value") else str(test_run.overall_verdict or "INCOMPLETE")
    return _OVERALL_VERDICT_MAP.get(raw, raw.upper())


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


def _get_verdict_raw(result) -> str:
    return result.verdict.value if hasattr(result.verdict, "value") else str(result.verdict)


def _get_tier_raw(result) -> str:
    return result.tier.value if hasattr(result.tier, "value") else str(result.tier)


def _get_overall_verdict_raw(test_run) -> str:
    return test_run.overall_verdict.value if hasattr(test_run.overall_verdict, "value") else str(test_run.overall_verdict or "incomplete")


def _filter_enabled_results(test_results, enabled_test_ids: Optional[list] = None):
    if not enabled_test_ids:
        return list(test_results)
    enabled_set = set(enabled_test_ids)
    return [r for r in test_results if r.test_id in enabled_set]


def _get_tool_versions(test_run) -> dict:
    meta = getattr(test_run, "run_metadata", None) or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except (json.JSONDecodeError, TypeError):
            meta = {}
    return meta.get("tool_versions", {})


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


# ---------------------------------------------------------------------------
# Excel Report Generation
# ---------------------------------------------------------------------------

async def generate_excel_report(
    test_run,
    test_results,
    report_config=None,
    template_key: str = "generic",
    enabled_test_ids: Optional[list] = None,
) -> str:
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
    from openpyxl.styles import Font, PatternFill

    filtered_results = _filter_enabled_results(test_results, enabled_test_ids)

    mapping = json.loads(mapping_file.read_text())
    wb = load_workbook(str(template_file))

    device = getattr(test_run, "device", None)
    engineer = getattr(test_run, "engineer", None)

    overall_verdict_str = _resolve_overall_verdict(test_run)

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
        "overall_result": overall_verdict_str,
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

    overall_cell = meta.get("overall_result")
    if overall_cell:
        verdict_fills = {
            "PASS": PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid"),
            "QUALIFIED PASS": PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid"),
            "FAIL": PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid"),
        }
        verdict_fonts = {
            "PASS": Font(name="Calibri", size=11, bold=True, color="006100"),
            "QUALIFIED PASS": Font(name="Calibri", size=11, bold=True, color="9C6500"),
            "FAIL": Font(name="Calibri", size=11, bold=True, color="9C0006"),
        }
        try:
            cell = synopsis_ws[overall_cell]
            cell.fill = verdict_fills.get(overall_verdict_str, PatternFill())
            cell.font = verdict_fonts.get(overall_verdict_str, Font(name="Calibri", size=11, bold=True))
        except Exception:
            logger.warning("Could not style overall verdict cell %s", overall_cell)

    tool_versions = _get_tool_versions(test_run)
    if tool_versions:
        tools_text = ", ".join(f"{k}: {v}" for k, v in tool_versions.items())
        tools_cell = meta.get("tool_versions")
        if tools_cell:
            try:
                synopsis_ws[tools_cell] = tools_text
            except Exception:
                pass

    testplan_ws = wb[mapping["testplan_sheet"]]
    cols = mapping["testplan_columns"]
    verdict_map = mapping.get("verdict_map", {})
    start_row = mapping["testplan_start_row"]
    template_row_count = mapping.get("testplan_row_count", 43)

    for i, result in enumerate(filtered_results):
        row = start_row + i

        if i >= template_row_count:
            testplan_ws.insert_rows(row)

        if cols.get("test_result"):
            testplan_ws[f"{cols['test_result']}{row}"] = _resolve_verdict(result, verdict_map)
        if cols.get("test_comments"):
            testplan_ws[f"{cols['test_comments']}{row}"] = _resolve_comment(result)
        if cols.get("script_flag"):
            testplan_ws[f"{cols['script_flag']}{row}"] = _resolve_script_flag(result)

    total_template_rows = max(template_row_count, len(filtered_results))
    if len(filtered_results) < template_row_count:
        rows_to_clear = template_row_count - len(filtered_results)
        clear_start = start_row + len(filtered_results)
        for row_idx in range(clear_start, clear_start + rows_to_clear):
            for col_key in ["test_number", "brief_description", "test_description",
                            "essential_pass", "test_result", "test_comments", "script_flag"]:
                col_letter = cols.get(col_key)
                if col_letter:
                    try:
                        testplan_ws[f"{col_letter}{row_idx}"] = None
                    except Exception:
                        pass

    output_dir = Path(settings.REPORT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"EDQ_Report_{test_run.id[:8]}_{template_key}_{timestamp}.xlsx"
    output_path = output_dir / filename
    wb.save(str(output_path))
    logger.info("Template-based Excel report saved: %s", output_path)
    return str(output_path)


async def generate_excel_report_scratch(test_run, test_results, report_config=None) -> str:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = Workbook()

    ws_summary = wb.active
    ws_summary.title = "Summary"
    ws_summary.column_dimensions["A"].width = 25
    ws_summary.column_dimensions["B"].width = 40

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
    overall_verdict_str = _resolve_overall_verdict(test_run)
    ws_summary["B5"] = overall_verdict_str
    verdict_colors = {"PASS": "27AE60", "QUALIFIED PASS": "F39C12", "FAIL": "E74C3C"}
    ws_summary["B5"].font = Font(
        name="Calibri", size=11, bold=True, color=verdict_colors.get(overall_verdict_str, "000000")
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

    tool_versions = _get_tool_versions(test_run)
    if tool_versions:
        ws_summary["A13"] = "Tool Versions"
        ws_summary["A13"].font = label_font
        row_offset = 14
        for tool_name, tool_ver in tool_versions.items():
            ws_summary[f"A{row_offset}"] = tool_name
            ws_summary[f"B{row_offset}"] = tool_ver
            row_offset += 1
        ws_summary[f"A{row_offset + 1}"] = "Generated"
        ws_summary[f"B{row_offset + 1}"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    else:
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
        verdict_val = _get_verdict_raw(result)
        tier_val = _get_tier_raw(result)
        compliance = ", ".join(result.compliance_map) if result.compliance_map else ""

        ws_results.cell(row=row_idx, column=1, value=result.test_id)
        ws_results.cell(row=row_idx, column=2, value=result.test_name)
        ws_results.cell(row=row_idx, column=3, value=tier_val)
        ws_results.cell(row=row_idx, column=4, value=result.tool or "—")
        ws_results.cell(row=row_idx, column=5, value=result.is_essential.upper())
        verdict_cell = ws_results.cell(row=row_idx, column=6, value=verdict_val.upper())
        verdict_cell.fill = verdict_fills.get(verdict_val, PatternFill())
        ws_results.cell(row=row_idx, column=7, value=_resolve_comment(result))
        ws_results.cell(row=row_idx, column=8, value=compliance)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"EDQ_Report_{test_run.id[:8]}_scratch_{timestamp}.xlsx"
    file_path = os.path.join(settings.REPORT_DIR, filename)
    wb.save(file_path)
    logger.info("Scratch Excel report saved: %s", file_path)
    return file_path


# ---------------------------------------------------------------------------
# Word Report Generation
# ---------------------------------------------------------------------------

_VERDICT_COLORS = {
    "pass": (39, 174, 96),
    "qualified_pass": (243, 156, 18),
    "fail": (231, 76, 60),
    "advisory": (243, 156, 18),
    "info": (52, 152, 219),
    "na": (149, 165, 166),
    "pending": (149, 165, 166),
}

_VERDICT_BG_COLORS = {
    "pass": "D5F5E3",
    "fail": "FADBD8",
    "advisory": "FEF9E7",
    "info": "D6EAF8",
    "na": "EAEDED",
}


def _set_cell_shading(cell, color_hex: str):
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), color_hex)
    shading.set(qn("w:val"), "clear")
    cell._tc.get_or_add_tcPr().append(shading)


def _add_styled_paragraph(doc, text: str, bold=False, size=11, color=None, alignment=None, space_after=None):
    from docx.shared import Pt, RGBColor
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.font.name = "Calibri"
    run.font.size = Pt(size)
    run.bold = bold
    if color:
        run.font.color.rgb = RGBColor(*color)
    if alignment:
        p.alignment = alignment
    if space_after is not None:
        from docx.shared import Pt as PtSpace
        p.paragraph_format.space_after = PtSpace(space_after)
    return p


async def generate_word_report(
    test_run,
    test_results,
    report_config=None,
    include_synopsis=False,
    enabled_test_ids: Optional[list] = None,
    whitelist_entries: Optional[list] = None,
) -> str:
    from docx import Document
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT

    filtered_results = _filter_enabled_results(test_results, enabled_test_ids)

    device = getattr(test_run, "device", None)
    engineer = getattr(test_run, "engineer", None)
    overall_raw = _get_overall_verdict_raw(test_run)
    overall_display = _resolve_overall_verdict(test_run)

    doc = Document()

    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    # --- Cover Page ---
    for _ in range(4):
        doc.add_paragraph()

    title_p = doc.add_paragraph()
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title_p.add_run("DEVICE QUALIFICATION REPORT")
    title_run.font.name = "Calibri"
    title_run.font.size = Pt(28)
    title_run.bold = True
    title_run.font.color.rgb = RGBColor(31, 78, 121)

    doc.add_paragraph()

    subtitle_p = doc.add_paragraph()
    subtitle_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub_run = subtitle_p.add_run("Electracom Projects Ltd")
    sub_run.font.name = "Calibri"
    sub_run.font.size = Pt(16)
    sub_run.font.color.rgb = RGBColor(89, 89, 89)

    doc.add_paragraph()

    info_items = [
        ("Device", _safe_attr(device, "hostname") or _safe_attr(device, "ip_address", "Unknown")),
        ("Manufacturer", _safe_attr(device, "manufacturer", "N/A")),
        ("Model", _safe_attr(device, "model", "N/A")),
        ("Firmware", _safe_attr(device, "firmware_version", "N/A")),
        ("IP Address", _safe_attr(device, "ip_address", "N/A")),
        ("Test Date", _format_date_range(test_run)),
        ("Engineer", _safe_attr(engineer, "full_name", "N/A")),
        ("Connection", getattr(test_run, "connection_scenario", "direct")),
    ]

    info_table = doc.add_table(rows=len(info_items), cols=2)
    info_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, (label, value) in enumerate(info_items):
        info_table.rows[i].cells[0].text = label
        info_table.rows[i].cells[1].text = str(value)
        for paragraph in info_table.rows[i].cells[0].paragraphs:
            paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            for run in paragraph.runs:
                run.font.bold = True
                run.font.size = Pt(12)
                run.font.name = "Calibri"
        for paragraph in info_table.rows[i].cells[1].paragraphs:
            for run in paragraph.runs:
                run.font.size = Pt(12)
                run.font.name = "Calibri"

    doc.add_paragraph()
    doc.add_paragraph()

    verdict_p = doc.add_paragraph()
    verdict_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    verdict_label = verdict_p.add_run("OVERALL VERDICT: ")
    verdict_label.font.name = "Calibri"
    verdict_label.font.size = Pt(20)
    verdict_label.bold = True
    verdict_value = verdict_p.add_run(overall_display)
    verdict_value.font.name = "Calibri"
    verdict_value.font.size = Pt(20)
    verdict_value.bold = True
    color_tuple = _VERDICT_COLORS.get(overall_raw, (0, 0, 0))
    verdict_value.font.color.rgb = RGBColor(*color_tuple)

    if overall_raw == "qualified_pass":
        note_p = doc.add_paragraph()
        note_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        note_run = note_p.add_run(
            "All essential tests passed but advisory findings were noted."
        )
        note_run.font.name = "Calibri"
        note_run.font.size = Pt(11)
        note_run.italic = True
        note_run.font.color.rgb = RGBColor(150, 150, 150)

    doc.add_page_break()

    # --- Executive Summary ---
    doc.add_heading("Executive Summary", level=1)

    if include_synopsis and test_run.synopsis:
        synopsis_text = test_run.synopsis.replace("[AI-DRAFTED] ", "")
        p = doc.add_paragraph(synopsis_text)
        p.paragraph_format.space_after = Pt(12)
    else:
        p = doc.add_paragraph(
            f"This report presents the results of the cybersecurity qualification "
            f"testing for the {_safe_attr(device, 'manufacturer', 'device')} "
            f"{_safe_attr(device, 'model', '')} at IP address "
            f"{_safe_attr(device, 'ip_address', 'N/A')}."
        )
        p.paragraph_format.space_after = Pt(12)

    doc.add_heading("Key Findings", level=2)

    findings_table = doc.add_table(rows=6, cols=2)
    findings_table.style = "Table Grid"
    findings_data = [
        ("Total Tests", str(len(filtered_results))),
        ("Passed", str(test_run.passed_tests or 0)),
        ("Failed", str(test_run.failed_tests or 0)),
        ("Advisory", str(test_run.advisory_tests or 0)),
        ("N/A", str(test_run.na_tests or 0)),
        ("Overall Verdict", overall_display),
    ]
    for i, (label, value) in enumerate(findings_data):
        findings_table.rows[i].cells[0].text = label
        findings_table.rows[i].cells[1].text = value
        for paragraph in findings_table.rows[i].cells[0].paragraphs:
            for run in paragraph.runs:
                run.font.bold = True
                run.font.name = "Calibri"
        if i == 5:
            bg = {"pass": "C6EFCE", "qualified_pass": "FFEB9C", "fail": "FFC7CE"}.get(overall_raw, "FFFFFF")
            _set_cell_shading(findings_table.rows[i].cells[1], bg)

    doc.add_paragraph()

    scenario = getattr(test_run, "connection_scenario", "direct")
    _add_styled_paragraph(doc, f"Connection Scenario: {scenario}", bold=True, size=11)

    tool_versions = _get_tool_versions(test_run)
    if tool_versions:
        doc.add_heading("Tool Versions", level=2)
        tv_table = doc.add_table(rows=len(tool_versions) + 1, cols=2)
        tv_table.style = "Table Grid"
        tv_table.rows[0].cells[0].text = "Tool"
        tv_table.rows[0].cells[1].text = "Version"
        for paragraph in tv_table.rows[0].cells[0].paragraphs:
            for run in paragraph.runs:
                run.font.bold = True
        for paragraph in tv_table.rows[0].cells[1].paragraphs:
            for run in paragraph.runs:
                run.font.bold = True
        for i, (tool_name, tool_ver) in enumerate(tool_versions.items(), 1):
            tv_table.rows[i].cells[0].text = tool_name
            tv_table.rows[i].cells[1].text = str(tool_ver)

    doc.add_page_break()

    # --- Test Results Table ---
    doc.add_heading("Test Results", level=1)

    results_table = doc.add_table(rows=1, cols=6)
    results_table.style = "Table Grid"
    result_headers = ["#", "Test Name", "Tier", "Essential", "Verdict", "Comments"]
    for i, header in enumerate(result_headers):
        cell = results_table.rows[0].cells[i]
        cell.text = header
        _set_cell_shading(cell, "1F4E79")
        for paragraph in cell.paragraphs:
            for run in paragraph.runs:
                run.font.bold = True
                run.font.color.rgb = RGBColor(255, 255, 255)
                run.font.name = "Calibri"
                run.font.size = Pt(10)

    for result in filtered_results:
        row = results_table.add_row()
        verdict_raw = _get_verdict_raw(result)
        tier_raw = _get_tier_raw(result)

        row.cells[0].text = result.test_id
        row.cells[1].text = result.test_name
        row.cells[2].text = tier_raw.replace("_", " ").title()
        row.cells[3].text = result.is_essential.upper()
        row.cells[4].text = _resolve_verdict(result, {})
        row.cells[5].text = _resolve_comment(result)[:200]

        bg_hex = _VERDICT_BG_COLORS.get(verdict_raw)
        if bg_hex:
            for cell in row.cells:
                _set_cell_shading(cell, bg_hex)

        for cell in row.cells:
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.font.name = "Calibri"
                    run.font.size = Pt(9)

    doc.add_page_break()

    # --- Detailed Findings (FAIL and ADVISORY only) ---
    fail_advisory = [
        r for r in filtered_results
        if _get_verdict_raw(r) in ("fail", "advisory")
    ]

    if fail_advisory:
        doc.add_heading("Detailed Findings", level=1)
        _add_styled_paragraph(
            doc,
            "The following tests returned FAIL or ADVISORY verdicts and require attention.",
            size=11,
        )

        for result in fail_advisory:
            verdict_raw = _get_verdict_raw(result)
            color_tuple = _VERDICT_COLORS.get(verdict_raw, (0, 0, 0))

            h = doc.add_heading(level=2)
            h_run = h.add_run(f"{result.test_id} — {result.test_name}")
            h_run.font.name = "Calibri"

            verdict_p = doc.add_paragraph()
            v_label = verdict_p.add_run("Verdict: ")
            v_label.bold = True
            v_label.font.name = "Calibri"
            v_value = verdict_p.add_run(_resolve_verdict(result, {}).upper())
            v_value.bold = True
            v_value.font.color.rgb = RGBColor(*color_tuple)
            v_value.font.name = "Calibri"

            comment = _resolve_comment(result)
            if comment:
                doc.add_paragraph(f"Comment: {comment}")

            findings = getattr(result, "findings", None)
            if findings:
                doc.add_paragraph("Findings:", style="List Bullet")
                if isinstance(findings, list):
                    for f in findings:
                        doc.add_paragraph(
                            str(f) if isinstance(f, str) else json.dumps(f),
                            style="List Bullet 2",
                        )
                elif isinstance(findings, dict):
                    for k, v in findings.items():
                        doc.add_paragraph(f"{k}: {v}", style="List Bullet 2")

            raw_output = getattr(result, "raw_output", None)
            if raw_output:
                doc.add_paragraph("Tool Output (excerpt):", style="List Bullet")
                excerpt = raw_output[:500]
                if len(raw_output) > 500:
                    excerpt += "..."
                p = doc.add_paragraph()
                run = p.add_run(excerpt)
                run.font.name = "Courier New"
                run.font.size = Pt(8)

            doc.add_paragraph()

        doc.add_page_break()

    # --- Protocol Whitelist Comparison ---
    has_u09 = any(r.test_id == "U09" for r in filtered_results)
    if has_u09 and whitelist_entries:
        doc.add_heading("Protocol Whitelist Comparison", level=1)
        _add_styled_paragraph(
            doc,
            "Comparison of discovered open ports against the approved protocol whitelist.",
            size=11,
        )

        wl_table = doc.add_table(rows=1, cols=4)
        wl_table.style = "Table Grid"
        wl_headers = ["Protocol / Service", "Port", "Expected", "Status"]
        for i, header in enumerate(wl_headers):
            cell = wl_table.rows[0].cells[i]
            cell.text = header
            _set_cell_shading(cell, "1F4E79")
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.font.bold = True
                    run.font.color.rgb = RGBColor(255, 255, 255)
                    run.font.name = "Calibri"

        u09_result = next((r for r in filtered_results if r.test_id == "U09"), None)
        parsed = getattr(u09_result, "parsed_data", None) or {} if u09_result else {}
        non_compliant_ports = set()
        if isinstance(parsed, dict):
            for item in parsed.get("non_compliant", []):
                non_compliant_ports.add(item.get("port"))

        for entry in whitelist_entries:
            if isinstance(entry, str):
                try:
                    entry = json.loads(entry)
                except (json.JSONDecodeError, TypeError):
                    continue
            row = wl_table.add_row()
            service = entry.get("service", "Unknown")
            port = entry.get("port", "")
            protocol = entry.get("protocol", "")
            row.cells[0].text = service
            row.cells[1].text = f"{port}/{protocol}"
            row.cells[2].text = "Allowed"
            is_compliant = port not in non_compliant_ports
            row.cells[3].text = "Compliant" if is_compliant else "Non-Compliant"
            if not is_compliant:
                _set_cell_shading(row.cells[3], "FFC7CE")

    # --- Footer ---
    doc.add_paragraph()
    footer = doc.add_paragraph()
    footer_run = footer.add_run(
        f"Report generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} | "
        f"EDQ v{settings.APP_VERSION}"
    )
    footer_run.italic = True
    footer_run.font.size = Pt(9)
    footer_run.font.color.rgb = RGBColor(150, 150, 150)

    output_dir = Path(settings.REPORT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"EDQ_Report_{test_run.id[:8]}_{timestamp}.docx"
    output_path = output_dir / filename
    doc.save(str(output_path))
    logger.info("Word report saved: %s", output_path)
    return str(output_path)


# ---------------------------------------------------------------------------
# PDF Report Generation
# ---------------------------------------------------------------------------

async def generate_pdf_report(
    test_run,
    test_results,
    report_config=None,
    include_synopsis=False,
    enabled_test_ids: Optional[list] = None,
    whitelist_entries: Optional[list] = None,
) -> str:
    docx_path = await generate_word_report(
        test_run,
        test_results,
        report_config=report_config,
        include_synopsis=include_synopsis,
        enabled_test_ids=enabled_test_ids,
        whitelist_entries=whitelist_entries,
    )

    output_dir = str(Path(docx_path).parent)

    try:
        subprocess.run(
            [
                "libreoffice",
                "--headless",
                "--norestore",
                "--convert-to", "pdf",
                "--outdir", output_dir,
                docx_path,
            ],
            check=True,
            timeout=120,
            capture_output=True,
        )
    except FileNotFoundError:
        logger.error("libreoffice not found — cannot convert to PDF")
        raise RuntimeError(
            "PDF generation requires LibreOffice. "
            "Install libreoffice-writer in the container."
        )
    except subprocess.TimeoutExpired:
        logger.error("LibreOffice conversion timed out after 120s")
        raise RuntimeError("PDF conversion timed out")
    except subprocess.CalledProcessError as e:
        logger.error("LibreOffice conversion failed: %s", e.stderr.decode(errors="replace"))
        raise RuntimeError(f"PDF conversion failed: {e.stderr.decode(errors='replace')}")

    pdf_path = Path(docx_path).with_suffix(".pdf")
    if not pdf_path.exists():
        raise RuntimeError(f"Expected PDF file not found at {pdf_path}")

    logger.info("PDF report saved: %s", pdf_path)
    return str(pdf_path)
