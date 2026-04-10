"""Report generation engine."""

from __future__ import annotations

import csv
import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.config import settings
from app.utils.datetime import as_utc, utcnow_naive

logger = logging.getLogger(__name__)

_ILLEGAL_XML_CHARS = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]")
_MAPPINGS_DIR = Path(__file__).resolve().parent / "cell_mappings"

TEMPLATE_FILES = {
    "pelco_camera": "1TS - Pelco SMLE1-15V5-3H Camera Device Qualification Rev 2.xlsx",
    "easyio_controller": "EasyIO FW08 - Device Testing Plan - v1.1.xlsx",
    "generic": "[MANUFACTURER] - [MODEL] - IP Device Qualification Template (Rev00) C00.xlsx",
}

TEMPLATE_INFO = {
    "pelco_camera": {"name": "Pelco Camera (Rev 2)", "device_category": "camera", "description": "Pelco camera workbook."},
    "easyio_controller": {"name": "EasyIO Controller", "device_category": "controller", "description": "EasyIO controller workbook."},
    "generic": {"name": "Generic IP Device (Rev00 C00)", "device_category": "generic", "description": "Canonical generic 3-sheet workbook."},
}


def _resolve_templates_dir() -> Path:
    here = Path(__file__).resolve()
    candidates: list[Path] = []

    env_value = os.getenv("EDQ_TEMPLATES_DIR")
    if env_value:
        candidates.append(Path(env_value))

    for depth in (2, 4):
        try:
            candidates.append(here.parents[depth] / "templates")
        except IndexError:
            continue

    candidates.append(Path.cwd() / "templates")

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return candidates[0]


_TEMPLATES_DIR = _resolve_templates_dir()

_VERDICT_MAP = {
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
_SUMMARY_FIELDS = [
    ("test_attempt", "Test Attempt"),
    ("date_range", "Date Test Started - Date Test Finished"),
    ("system", "System"),
    ("system_owner", "System Owner"),
    ("manufacturer", "Manufacturer"),
    ("model", "Model"),
    ("firmware", "Firmware Version"),
    ("serial", "Serial Number"),
    ("tester_name", "Name Of Tester"),
    ("overall_result", "TEST RESULT"),
]


@dataclass
class ReportRow:
    test_number: str
    brief_description: str
    test_description: str
    essential_test: str
    test_result: str
    test_comments: str
    template_backed: bool = False


@dataclass
class ReportSection:
    title: str
    body: str


@dataclass
class ReportDocument:
    template_key: str
    template_path: Path
    mapping: dict[str, Any]
    metadata: dict[str, str]
    rows: list[ReportRow] = field(default_factory=list)
    additional_sections: list[ReportSection] = field(default_factory=list)


def _sanitize(value: Any) -> Any:
    return _ILLEGAL_XML_CHARS.sub("", value) if isinstance(value, str) else value


def _safe_attr(obj: Any, attr: str, default: str = "") -> str:
    value = getattr(obj, attr, None) if obj is not None else None
    if hasattr(value, "value"):
        value = value.value
    return default if value is None else str(value)


def _load_mapping(template_key: str) -> dict[str, Any]:
    path = _MAPPINGS_DIR / f"{template_key}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _format_date_range(test_run: Any) -> str:
    start = getattr(test_run, "started_at", None) or getattr(test_run, "created_at", None)
    end = getattr(test_run, "completed_at", None) or utcnow_naive()
    return f"{start.strftime('%d/%m/%Y') if start else ''} - {end.strftime('%d/%m/%Y') if end else ''}".strip(" -")


def _overall_result(test_run: Any) -> str:
    raw = getattr(test_run, "overall_verdict", None)
    raw = raw.value if hasattr(raw, "value") else str(raw or "incomplete")
    return _VERDICT_MAP.get(raw, raw.upper())


def _comment(result: Any) -> str:
    parts = [getattr(result, "comment_override", None) or getattr(result, "comment", None) or ""]
    notes = getattr(result, "engineer_notes", None)
    if notes:
        parts.append(f"[Engineer Notes: {notes}]")
    reason = getattr(result, "override_reason", None)
    if reason:
        parts.append(f"[Override: {reason}]")
    return " ".join(part for part in parts if part).strip()


def _summary_text(test_run: Any, metadata: dict[str, str], include_synopsis: bool) -> str:
    synopsis = (getattr(test_run, "synopsis", None) or "").replace("[AI-DRAFTED] ", "").strip()
    if include_synopsis and synopsis:
        return synopsis
    return (
        f"Qualification testing for {metadata.get('manufacturer') or 'Unknown manufacturer'} "
        f"{metadata.get('model') or 'Unknown model'} completed with an overall result of "
        f"{metadata.get('overall_result') or 'INCOMPLETE'}."
    )


def build_report_document(
    test_run: Any,
    test_results: list[Any],
    report_config: Any = None,
    template_key: str = "generic",
    enabled_test_ids: Optional[list[str]] = None,
    whitelist_entries: Optional[list[Any]] = None,
    include_synopsis: bool = False,
) -> ReportDocument:
    del whitelist_entries
    if template_key not in TEMPLATE_FILES:
        raise ValueError(f"Unknown template_key '{template_key}'")
    filtered_results = [r for r in test_results if not enabled_test_ids or getattr(r, "test_id", None) in set(enabled_test_ids)]
    mapping = _load_mapping(template_key)
    template_path = _TEMPLATES_DIR / TEMPLATE_FILES[template_key]

    device = getattr(test_run, "device", None)
    engineer = getattr(test_run, "engineer", None)
    metadata = {
        "test_attempt": "1",
        "date_range": _format_date_range(test_run),
        "system": _safe_attr(device, "category").replace("_", " ").title(),
        "system_owner": _safe_attr(report_config, "client_name"),
        "manufacturer": _safe_attr(device, "manufacturer"),
        "model": _safe_attr(device, "model"),
        "firmware": _safe_attr(device, "firmware_version"),
        "serial": _safe_attr(device, "serial_number"),
        "tester_name": _safe_attr(engineer, "full_name"),
        "overall_result": _overall_result(test_run),
        "summary_text": "",
    }
    metadata["summary_text"] = _summary_text(test_run, metadata, include_synopsis)

    rows: list[ReportRow] = []
    if template_key == "generic" and template_path.exists() and mapping:
        from openpyxl import load_workbook

        wb = load_workbook(str(template_path), read_only=True, data_only=False)
        try:
            ws = wb[mapping["testplan_sheet"]]
            cols = mapping["testplan_columns"]
            start = mapping["testplan_start_row"]
            count = mapping["testplan_row_count"]
            result_by_id = {str(getattr(r, "test_id", "")): r for r in filtered_results}
            sources = mapping.get("row_sources", {})
            for row_index in range(start, start + count):
                number = str(ws[f"{cols['test_number']}{row_index}"].value or "").strip()
                source_ids = sources.get(number, [])
                source = next((result_by_id[test_id] for test_id in source_ids if test_id in result_by_id), None)
                rows.append(
                    ReportRow(
                        test_number=number,
                        brief_description=str(ws[f"{cols['brief_description']}{row_index}"].value or ""),
                        test_description=str(ws[f"{cols['test_description']}{row_index}"].value or ""),
                        essential_test=str(ws[f"{cols.get('essential_test', cols.get('essential_pass'))}{row_index}"].value or ""),
                        test_result=_VERDICT_MAP.get((_safe_attr(source, "verdict") or "").lower(), _safe_attr(source, "verdict").upper()) if source else "",
                        test_comments=_comment(source) if source else "",
                        template_backed=True,
                    )
                )
        finally:
            wb.close()
    else:
        for idx, result in enumerate(filtered_results, start=1):
            rows.append(
                ReportRow(
                    test_number=str(idx),
                    brief_description=_safe_attr(result, "test_name"),
                    test_description="",
                    essential_test=_safe_attr(result, "is_essential").upper(),
                    test_result=_VERDICT_MAP.get((_safe_attr(result, "verdict") or "").lower(), _safe_attr(result, "verdict").upper()),
                    test_comments=_comment(result),
                )
            )

    additional_sections = [
        ReportSection("Executive Summary", metadata["summary_text"]),
        ReportSection("Supporting Evidence and Findings", f"Connection Scenario: {_safe_attr(test_run, 'connection_scenario', 'direct')}"),
    ]
    return ReportDocument(template_key=template_key, template_path=template_path, mapping=mapping, metadata=metadata, rows=rows, additional_sections=additional_sections)


def get_available_templates() -> list[dict[str, Any]]:
    items = []
    for key, info in TEMPLATE_INFO.items():
        items.append({
            "key": key,
            "name": info["name"],
            "device_category": info["device_category"],
            "description": info["description"],
            "template_exists": (_TEMPLATES_DIR / TEMPLATE_FILES[key]).exists(),
            "mapping_exists": (_MAPPINGS_DIR / f"{key}.json").exists(),
        })
    return items


def _output_path(test_run: Any, template_key: str, extension: str) -> Path:
    output_dir = Path(settings.REPORT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return output_dir / f"EDQ_Report_{str(test_run.id)[:8]}_{template_key}_{stamp}{extension}"


async def generate_excel_report(
    test_run: Any,
    test_results: list[Any],
    report_config: Any = None,
    template_key: str = "generic",
    enabled_test_ids: Optional[list[str]] = None,
    whitelist_entries: Optional[list[Any]] = None,
    include_synopsis: bool = False,
) -> str:
    report = build_report_document(test_run, test_results, report_config, template_key, enabled_test_ids, whitelist_entries, include_synopsis)
    from openpyxl import Workbook, load_workbook

    if report.template_path.exists() and report.mapping:
        wb = load_workbook(str(report.template_path))
        summary_ws = wb[report.mapping["synopsis_sheet"]]
        for key, cell in report.mapping.get("metadata_cells", {}).items():
            summary_ws[cell] = _sanitize(report.metadata.get(key, ""))
        testplan_ws = wb[report.mapping["testplan_sheet"]]
        cols = report.mapping["testplan_columns"]
        start = report.mapping["testplan_start_row"]
        for offset, row in enumerate(report.rows):
            testplan_ws[f"{cols['test_result']}{start + offset}"] = _sanitize(row.test_result) or None
            testplan_ws[f"{cols['test_comments']}{start + offset}"] = _sanitize(row.test_comments) or None
        additional_ws = wb[report.mapping["additional_sheet"]]
        cells = report.mapping.get("additional_cells", {})
        if report.additional_sections:
            additional_ws[cells["section_1_title"]] = report.additional_sections[0].title
            additional_ws[cells["section_1_body"]] = report.additional_sections[0].body
        if len(report.additional_sections) > 1:
            additional_ws[cells["section_2_title"]] = report.additional_sections[1].title
            additional_ws[cells["section_2_body"]] = report.additional_sections[1].body
    else:
        wb = Workbook()
        wb.active.title = "TEST SUMMARY"
        wb.create_sheet("TESTPLAN")
        wb.create_sheet("ADDITIONAL INFORMATION")
    path = _output_path(test_run, template_key, ".xlsx")
    wb.save(str(path))
    return str(path)


async def generate_word_report(
    test_run: Any,
    test_results: list[Any],
    report_config: Any = None,
    include_synopsis: bool = False,
    enabled_test_ids: Optional[list[str]] = None,
    whitelist_entries: Optional[list[Any]] = None,
    template_key: str = "generic",
) -> str:
    from docx import Document

    report = build_report_document(test_run, test_results, report_config, template_key, enabled_test_ids, whitelist_entries, include_synopsis)
    doc = Document()
    doc.add_heading("IP Device Qualification Report", level=0)
    doc.add_heading("TEST SUMMARY", level=1)
    table = doc.add_table(rows=0, cols=2)
    for key, label in _SUMMARY_FIELDS:
        row = table.add_row()
        row.cells[0].text = label
        row.cells[1].text = str(report.metadata.get(key, ""))
    doc.add_paragraph(report.metadata.get("summary_text", ""))
    doc.add_page_break()
    doc.add_heading("TESTPLAN", level=1)
    results_table = doc.add_table(rows=1, cols=6)
    for idx, header in enumerate(["Test Number", "Brief Description", "Test Description", "Essential Test", "Test Result", "Test Comments"]):
        results_table.rows[0].cells[idx].text = header
    for item in report.rows:
        row = results_table.add_row()
        row.cells[0].text = item.test_number
        row.cells[1].text = item.brief_description
        row.cells[2].text = item.test_description
        row.cells[3].text = item.essential_test
        row.cells[4].text = item.test_result
        row.cells[5].text = item.test_comments
    doc.add_page_break()
    doc.add_heading("ADDITIONAL INFORMATION", level=1)
    for section in report.additional_sections:
        doc.add_heading(section.title, level=2)
        doc.add_paragraph(section.body)
    path = _output_path(test_run, template_key, ".docx")
    doc.save(str(path))
    return str(path)


async def _generate_pdf_via_libreoffice(docx_path: str) -> str:
    import asyncio
    output_dir = str(Path(docx_path).parent)
    proc = await asyncio.create_subprocess_exec(
        "libreoffice", "--headless", "--norestore", "--convert-to", "pdf",
        "--outdir", output_dir, docx_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(f"LibreOffice conversion failed: {stderr.decode()[:200]}")
    pdf_path = Path(docx_path).with_suffix(".pdf")
    if not pdf_path.exists():
        raise RuntimeError(f"Expected PDF file not found at {pdf_path}")
    return str(pdf_path)


async def _generate_pdf_via_fpdf(
    test_run: Any,
    test_results: list[Any],
    report_config: Any = None,
    include_synopsis: bool = False,
    enabled_test_ids: Optional[list[str]] = None,
    whitelist_entries: Optional[list[Any]] = None,
    template_key: str = "generic",
) -> str:
    from fpdf import FPDF

    report = build_report_document(test_run, test_results, report_config, template_key, enabled_test_ids, whitelist_entries, include_synopsis)
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=10)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "IP DEVICE QUALIFICATION REPORT", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "TEST SUMMARY", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    for key, label in _SUMMARY_FIELDS:
        pdf.cell(60, 6, f"{label}:")
        pdf.cell(0, 6, str(report.metadata.get(key, "")), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.multi_cell(0, 5, report.metadata.get("summary_text", ""))
    pdf.add_page(orientation="L")
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "TESTPLAN", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8)
    for row in report.rows:
        pdf.multi_cell(0, 5, f"{row.test_number} | {row.brief_description} | {row.test_result} | {row.test_comments}")
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "ADDITIONAL INFORMATION", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    for section in report.additional_sections:
        pdf.multi_cell(0, 5, f"{section.title}\n{section.body}\n")
    path = _output_path(test_run, template_key, ".pdf")
    pdf.output(str(path))
    return str(path)


async def generate_pdf_report(
    test_run: Any,
    test_results: list[Any],
    report_config: Any = None,
    include_synopsis: bool = False,
    enabled_test_ids: Optional[list[str]] = None,
    whitelist_entries: Optional[list[Any]] = None,
    template_key: str = "generic",
) -> str:
    try:
        docx_path = await generate_word_report(test_run, test_results, report_config, include_synopsis, enabled_test_ids, whitelist_entries, template_key)
        return await _generate_pdf_via_libreoffice(docx_path)
    except Exception:
        return await _generate_pdf_via_fpdf(test_run, test_results, report_config, include_synopsis, enabled_test_ids, whitelist_entries, template_key)


async def generate_csv_report(
    test_run: Any,
    test_results: list[Any],
    report_config: Any = None,
    include_synopsis: bool = False,
    enabled_test_ids: Optional[list[str]] = None,
    whitelist_entries: Optional[list[Any]] = None,
    template_key: str = "generic",
) -> str:
    report = build_report_document(test_run, test_results, report_config, template_key, enabled_test_ids, whitelist_entries, include_synopsis)
    path = _output_path(test_run, template_key, ".csv")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["TEST SUMMARY"])
        writer.writerow(["Field", "Value"])
        for key, label in _SUMMARY_FIELDS:
            writer.writerow([label, report.metadata.get(key, "")])
        writer.writerow(["Summary", report.metadata.get("summary_text", "")])
        writer.writerow([])
        writer.writerow(["TESTPLAN"])
        writer.writerow(["Test Number", "Brief Description", "Test Description", "Essential Test", "Test Result", "Test Comments"])
        for row in report.rows:
            writer.writerow([row.test_number, row.brief_description, row.test_description, row.essential_test, row.test_result, row.test_comments])
        writer.writerow([])
        writer.writerow(["ADDITIONAL INFORMATION"])
        writer.writerow(["Section", "Content"])
        for section in report.additional_sections:
            writer.writerow([section.title, section.body])
    return str(path)
