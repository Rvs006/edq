"""Report generation engine."""

from __future__ import annotations

import csv
import json
import logging
import os
import re
import subprocess
import textwrap
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.config import settings
from app.services.run_readiness import build_run_readiness_summary
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
_SUMMARY_LABELS = {
    **dict(_SUMMARY_FIELDS),
    "start_date": "Date Test Started",
    "end_date": "Date Test Finished",
}
_TESTPLAN_COLUMN_LABELS = {
    "test_number": "Test Number",
    "brief_description": "Brief Description",
    "test_description": "Test Description",
    "essential_test": "Essential Test",
    "essential_pass": "Essential Pass",
    "test_result": "Test Result",
    "test_comments": "Test Comments",
    "script_flag": "Script Flag",
}


@dataclass
class ReportRow:
    test_number: str
    brief_description: str
    test_description: str
    essential_test: str
    test_result: str
    test_comments: str
    script_flag: str = ""
    template_backed: bool = False


@dataclass
class ReportSection:
    title: str
    body: str


@dataclass
class ReportBranding:
    company_name: str = ""
    primary_color: str = ""
    footer_text: str = ""
    logo_path: str = ""


@dataclass
class ReportDocument:
    template_key: str
    template_path: Path
    mapping: dict[str, Any]
    metadata: dict[str, str]
    summary_section_title: str = "TEST SUMMARY"
    testplan_section_title: str = "TESTPLAN"
    additional_section_title: str = "ADDITIONAL INFORMATION"
    summary_text_label: str = "Summary"
    summary_fields: list[tuple[str, str]] = field(default_factory=list)
    testplan_columns: list[tuple[str, str]] = field(default_factory=list)
    branding: ReportBranding = field(default_factory=ReportBranding)
    readiness_summary: dict[str, Any] = field(default_factory=dict)
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


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _resolve_branding(report_config: Any = None, branding_settings: Any = None) -> ReportBranding:
    config_branding = _json_dict(getattr(report_config, "branding", None))
    company_name = (
        _safe_attr(branding_settings, "company_name")
        or _safe_attr(report_config, "client_name")
        or str(config_branding.get("company_name") or "")
        or settings.APP_NAME
    )
    primary_color = (
        _safe_attr(branding_settings, "primary_color")
        or str(config_branding.get("primary_color") or "")
        or "#2563eb"
    )
    footer_text = (
        _safe_attr(branding_settings, "footer_text")
        or str(config_branding.get("footer_text") or "")
    )
    logo_path = (
        _safe_attr(branding_settings, "logo_path")
        or _safe_attr(report_config, "logo_path")
        or str(config_branding.get("logo_path") or "")
    )
    return ReportBranding(
        company_name=company_name,
        primary_color=primary_color,
        footer_text=footer_text,
        logo_path=logo_path,
    )


def _report_window(test_run: Any) -> tuple[Any, Any]:
    start = getattr(test_run, "started_at", None) or getattr(test_run, "created_at", None)
    end = getattr(test_run, "completed_at", None) or utcnow_naive()
    return start, end


def _format_date_range(test_run: Any) -> str:
    start, end = _report_window(test_run)
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


def _summary_text(
    test_run: Any,
    metadata: dict[str, str],
    include_synopsis: bool,
    readiness_summary: dict[str, Any],
) -> str:
    synopsis = (getattr(test_run, "synopsis", None) or "").replace("[AI-DRAFTED] ", "").strip()
    readiness_line = (
        f" Readiness status: {readiness_summary.get('label', 'Unknown')} "
        f"({readiness_summary.get('score', 1)}/10)."
    )
    if include_synopsis and synopsis:
        return f"{synopsis.rstrip('.')}.{readiness_line}" if not synopsis.endswith(".") else f"{synopsis}{readiness_line}"
    summary = (
        f"Qualification testing for {metadata.get('manufacturer') or 'Unknown manufacturer'} "
        f"{metadata.get('model') or 'Unknown model'} completed with an overall result of "
        f"{metadata.get('overall_result') or 'INCOMPLETE'}."
    )
    return f"{summary}{readiness_line}"


def _supporting_evidence_body(
    test_run: Any,
    branding: ReportBranding,
    readiness_summary: dict[str, Any],
) -> str:
    parts = [
        f"Readiness Status: {readiness_summary.get('label', 'Unknown')} ({readiness_summary.get('score', 1)}/10)",
        f"Official Report Ready: {'Yes' if readiness_summary.get('report_ready') else 'No'}",
        f"Operationally Ready: {'Yes' if readiness_summary.get('operational_ready') else 'No'}",
        f"Next Step: {readiness_summary.get('next_step', 'Review the remaining findings.')}",
        "Key Reasons:",
    ]
    for reason in readiness_summary.get("reasons", [])[:4]:
        parts.append(f"- {reason}")
    parts.append(f"Connection Scenario: {_safe_attr(test_run, 'connection_scenario', 'direct')}")
    if branding.footer_text:
        parts.append(f"Report Footer: {branding.footer_text}")
    return "\n".join(parts)


def _resolve_summary_fields(mapping: dict[str, Any]) -> list[tuple[str, str]]:
    metadata_cells = mapping.get("metadata_cells") or {}
    ordered_keys = [key for key in metadata_cells if key not in {"summary_text", "synopsis_text"}]
    if not ordered_keys:
        return list(_SUMMARY_FIELDS)
    return [(key, _SUMMARY_LABELS.get(key, key.replace("_", " ").title())) for key in ordered_keys]


def _resolve_testplan_columns(mapping: dict[str, Any]) -> list[tuple[str, str]]:
    columns = mapping.get("testplan_columns") or {}
    ordered_keys = [
        "test_number",
        "brief_description",
        "test_description",
        "essential_test",
        "essential_pass",
        "test_result",
        "test_comments",
        "script_flag",
    ]
    resolved: list[tuple[str, str]] = []
    for key in ordered_keys:
        if key not in columns:
            continue
        attribute = "essential_test" if key == "essential_pass" else key
        resolved.append((attribute, _TESTPLAN_COLUMN_LABELS.get(key, key.replace("_", " ").title())))
    if resolved:
        return resolved
    return [
        ("test_number", "Test Number"),
        ("brief_description", "Brief Description"),
        ("test_description", "Test Description"),
        ("essential_test", "Essential Test"),
        ("test_result", "Test Result"),
        ("test_comments", "Test Comments"),
    ]


def _resolve_summary_text_label(mapping: dict[str, Any]) -> str:
    metadata_cells = mapping.get("metadata_cells") or {}
    return "Synopsis" if "synopsis_text" in metadata_cells else "Summary"


def _report_row_values(row: ReportRow, columns: list[tuple[str, str]]) -> list[str]:
    return [str(getattr(row, attribute, "") or "") for attribute, _ in columns]


def _pdf_safe_width(pdf: Any) -> float:
    return max(float(pdf.w) - float(pdf.l_margin) - float(pdf.r_margin), 20.0)


def _pdf_safe_text(value: str) -> str:
    text = str(value or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("|", " - ")
    text = (
        text.replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2022", "-")
        .replace("\u2026", "...")
        .replace("\u00a0", " ")
    )
    return text.encode("latin-1", "replace").decode("latin-1")


def _pdf_wrapped_lines(value: str, width: int = 140) -> list[str]:
    lines: list[str] = []
    for paragraph in _pdf_safe_text(value).split("\n"):
        wrapped = textwrap.wrap(
            paragraph,
            width=width,
            break_long_words=True,
            break_on_hyphens=True,
        )
        lines.extend(wrapped or [""])
    return lines or [""]


def _write_pdf_lines(pdf: Any, value: str, line_height: float = 5, wrap_width: int = 140) -> None:
    width = _pdf_safe_width(pdf)
    for line in _pdf_wrapped_lines(value, width=wrap_width):
        pdf.set_x(pdf.l_margin)
        pdf.cell(width, line_height, _pdf_safe_text(line or " "), new_x="LMARGIN", new_y="NEXT")


def build_report_document(
    test_run: Any,
    test_results: list[Any],
    report_config: Any = None,
    template_key: str = "generic",
    enabled_test_ids: Optional[list[str]] = None,
    whitelist_entries: Optional[list[Any]] = None,
    include_synopsis: bool = False,
    branding_settings: Any = None,
    readiness_summary: Optional[dict[str, Any]] = None,
) -> ReportDocument:
    del whitelist_entries
    if template_key not in TEMPLATE_FILES:
        raise ValueError(f"Unknown template_key '{template_key}'")
    filtered_results = [r for r in test_results if not enabled_test_ids or getattr(r, "test_id", None) in set(enabled_test_ids)]
    mapping = _load_mapping(template_key)
    template_path = _TEMPLATES_DIR / TEMPLATE_FILES[template_key]
    branding = _resolve_branding(report_config, branding_settings)
    start, end = _report_window(test_run)
    resolved_readiness = readiness_summary or build_run_readiness_summary(test_run, filtered_results)
    summary_section_title = str(mapping.get("synopsis_sheet") or "TEST SUMMARY")
    testplan_section_title = str(mapping.get("testplan_sheet") or "TESTPLAN")
    additional_section_title = str(mapping.get("additional_sheet") or "ADDITIONAL INFORMATION")
    summary_text_label = _resolve_summary_text_label(mapping)
    summary_fields = _resolve_summary_fields(mapping)
    testplan_columns = _resolve_testplan_columns(mapping)

    device = getattr(test_run, "device", None)
    engineer = getattr(test_run, "engineer", None)
    metadata = {
        "test_attempt": "1",
        "date_range": _format_date_range(test_run),
        "start_date": start.strftime("%d/%m/%Y") if start else "",
        "end_date": end.strftime("%d/%m/%Y") if end else "",
        "system": _safe_attr(device, "category").replace("_", " ").title(),
        "system_owner": _safe_attr(report_config, "client_name") or branding.company_name,
        "manufacturer": _safe_attr(device, "manufacturer"),
        "model": _safe_attr(device, "model"),
        "firmware": _safe_attr(device, "firmware_version"),
        "serial": _safe_attr(device, "serial_number"),
        "tester_name": _safe_attr(engineer, "full_name"),
        "overall_result": _overall_result(test_run),
        "summary_text": "",
    }
    metadata["summary_text"] = _summary_text(
        test_run,
        metadata,
        include_synopsis,
        resolved_readiness,
    )
    metadata["synopsis_text"] = metadata["summary_text"]

    rows: list[ReportRow] = []
    if template_path.exists() and mapping and mapping.get("row_sources"):
        from openpyxl import load_workbook

        wb = load_workbook(str(template_path), read_only=True, data_only=False)
        try:
            ws = wb[mapping["testplan_sheet"]]
            cols = mapping["testplan_columns"]
            start = mapping["testplan_start_row"]
            count = mapping["testplan_row_count"]
            result_by_id = {str(getattr(r, "test_id", "")): r for r in filtered_results}
            sources = mapping.get("row_sources", {})
            brief_column = cols.get("brief_description") or cols.get("test_description")
            description_column = cols.get("test_description") or brief_column
            essential_column = cols.get("essential_test", cols.get("essential_pass"))
            script_column = cols.get("script_flag")
            for row_index in range(start, start + count):
                number = str(ws[f"{cols['test_number']}{row_index}"].value or "").strip()
                source_ids = sources.get(number, [])
                source = next((result_by_id[test_id] for test_id in source_ids if test_id in result_by_id), None)
                rows.append(
                    ReportRow(
                        test_number=number,
                        brief_description=str(ws[f"{brief_column}{row_index}"].value or "") if brief_column else "",
                        test_description=str(ws[f"{description_column}{row_index}"].value or "") if description_column else "",
                        essential_test=str(ws[f"{essential_column}{row_index}"].value or "") if essential_column else "",
                        test_result=_VERDICT_MAP.get((_safe_attr(source, "verdict") or "").lower(), _safe_attr(source, "verdict").upper()) if source else "",
                        test_comments=_comment(source) if source else "",
                        script_flag=str(ws[f"{script_column}{row_index}"].value or "") if script_column else "",
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
                    script_flag="",
                )
            )

    additional_sections = [
        ReportSection("Executive Summary", metadata["summary_text"]),
        ReportSection(
            "Readiness and Supporting Evidence",
            _supporting_evidence_body(test_run, branding, resolved_readiness),
        ),
    ]
    return ReportDocument(
        template_key=template_key,
        template_path=template_path,
        mapping=mapping,
        metadata=metadata,
        summary_section_title=summary_section_title,
        testplan_section_title=testplan_section_title,
        additional_section_title=additional_section_title,
        summary_text_label=summary_text_label,
        summary_fields=summary_fields,
        testplan_columns=testplan_columns,
        branding=branding,
        readiness_summary=resolved_readiness,
        rows=rows,
        additional_sections=additional_sections,
    )


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
    return output_dir / f"EDQ_Report_{test_run.id!s}_{template_key}_{stamp}{extension}"


async def generate_excel_report(
    test_run: Any,
    test_results: list[Any],
    report_config: Any = None,
    template_key: str = "generic",
    enabled_test_ids: Optional[list[str]] = None,
    whitelist_entries: Optional[list[Any]] = None,
    include_synopsis: bool = False,
    branding_settings: Any = None,
    readiness_summary: Optional[dict[str, Any]] = None,
) -> str:
    import asyncio

    report = build_report_document(
        test_run,
        test_results,
        report_config,
        template_key,
        enabled_test_ids,
        whitelist_entries,
        include_synopsis,
        branding_settings,
        readiness_summary,
    )
    path = _output_path(test_run, template_key, ".xlsx")

    if report.template_path.exists() and report.mapping:
        # Build cell updates per sheet — ZIP-level patcher preserves ALL
        # template assets (images, drawings, printer settings, styles, etc.)
        from app.services.xlsx_template_patcher import patch_xlsx

        sheet_updates: dict[str, dict[str, str | None]] = {}

        # TEST SUMMARY metadata cells
        synopsis_sheet = report.mapping["synopsis_sheet"]
        summary_cells: dict[str, str | None] = {}
        for key, cell in report.mapping.get("metadata_cells", {}).items():
            value = _sanitize(report.metadata.get(key, ""))
            summary_cells[cell] = value if value else None
        if summary_cells:
            sheet_updates[synopsis_sheet] = summary_cells

        # TESTPLAN test result + comment cells
        testplan_sheet = report.mapping["testplan_sheet"]
        cols = report.mapping["testplan_columns"]
        start = report.mapping["testplan_start_row"]
        testplan_cells: dict[str, str | None] = {}
        for offset, row in enumerate(report.rows):
            result_val = _sanitize(row.test_result) or None
            comment_val = _sanitize(row.test_comments) or None
            testplan_cells[f"{cols['test_result']}{start + offset}"] = result_val
            testplan_cells[f"{cols['test_comments']}{start + offset}"] = comment_val
        if testplan_cells:
            sheet_updates[testplan_sheet] = testplan_cells

        # ADDITIONAL INFORMATION sections
        additional_sheet = report.mapping.get("additional_sheet")
        add_cells_map = report.mapping.get("additional_cells") or {}
        additional_cells: dict[str, str | None] = {}
        if report.additional_sections and add_cells_map.get("section_1_title") and add_cells_map.get("section_1_body"):
            additional_cells[add_cells_map["section_1_title"]] = report.additional_sections[0].title
            additional_cells[add_cells_map["section_1_body"]] = report.additional_sections[0].body
        if len(report.additional_sections) > 1 and add_cells_map.get("section_2_title") and add_cells_map.get("section_2_body"):
            additional_cells[add_cells_map["section_2_title"]] = report.additional_sections[1].title
            additional_cells[add_cells_map["section_2_body"]] = report.additional_sections[1].body
        if additional_sheet and additional_cells:
            sheet_updates[additional_sheet] = additional_cells

        await asyncio.to_thread(patch_xlsx, report.template_path, path, sheet_updates)
    else:
        # Fallback: no template to preserve — plain openpyxl workbook
        from openpyxl import Workbook

        wb = Workbook()
        wb.active.title = report.summary_section_title
        wb.create_sheet(report.testplan_section_title)
        wb.create_sheet(report.additional_section_title)
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
    branding_settings: Any = None,
    readiness_summary: Optional[dict[str, Any]] = None,
) -> str:
    from docx import Document

    report = build_report_document(
        test_run,
        test_results,
        report_config,
        template_key,
        enabled_test_ids,
        whitelist_entries,
        include_synopsis,
        branding_settings,
        readiness_summary,
    )
    doc = Document()
    if report.branding.company_name:
        doc.sections[0].header.paragraphs[0].text = report.branding.company_name
        doc.add_paragraph(report.branding.company_name)
    if report.branding.footer_text:
        doc.sections[0].footer.paragraphs[0].text = report.branding.footer_text
    doc.add_heading("IP Device Qualification Report", level=0)
    doc.add_paragraph(f"Template Profile: {TEMPLATE_INFO[report.template_key]['name']}")
    doc.add_heading(report.summary_section_title, level=1)
    table = doc.add_table(rows=0, cols=2)
    for key, label in report.summary_fields:
        row = table.add_row()
        row.cells[0].text = label
        row.cells[1].text = str(report.metadata.get(key, ""))
    doc.add_paragraph(f"{report.summary_text_label}: {report.metadata.get('summary_text', '')}")
    doc.add_page_break()
    doc.add_heading(report.testplan_section_title, level=1)
    results_table = doc.add_table(rows=1, cols=len(report.testplan_columns))
    for idx, (_, header) in enumerate(report.testplan_columns):
        results_table.rows[0].cells[idx].text = header
    for item in report.rows:
        row = results_table.add_row()
        for idx, value in enumerate(_report_row_values(item, report.testplan_columns)):
            row.cells[idx].text = value
    doc.add_page_break()
    doc.add_heading(report.additional_section_title, level=1)
    additional_table = doc.add_table(rows=1, cols=2)
    additional_table.rows[0].cells[0].text = "Section"
    additional_table.rows[0].cells[1].text = "Content"
    for section in report.additional_sections:
        row = additional_table.add_row()
        row.cells[0].text = section.title
        row.cells[1].text = section.body
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
    branding_settings: Any = None,
    readiness_summary: Optional[dict[str, Any]] = None,
) -> str:
    from fpdf import FPDF

    report = build_report_document(
        test_run,
        test_results,
        report_config,
        template_key,
        enabled_test_ids,
        whitelist_entries,
        include_synopsis,
        branding_settings,
        readiness_summary,
    )
    pdf = FPDF()
    if hasattr(pdf, "set_compression"):
        pdf.set_compression(False)
    pdf.set_auto_page_break(auto=True, margin=10)
    pdf.add_page()
    if report.branding.company_name:
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 8, report.branding.company_name, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "IP DEVICE QUALIFICATION REPORT", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Template Profile: {TEMPLATE_INFO[report.template_key]['name']}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, report.summary_section_title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    for key, label in report.summary_fields:
        _write_pdf_lines(pdf, f"{label}: {str(report.metadata.get(key, ''))}", line_height=6, wrap_width=120)
    pdf.ln(2)
    _write_pdf_lines(pdf, f"{report.summary_text_label}: {report.metadata.get('summary_text', '')}", line_height=5, wrap_width=140)
    pdf.add_page(orientation="L")
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, report.testplan_section_title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 8)
    _write_pdf_lines(pdf, " | ".join(label for _, label in report.testplan_columns), line_height=5, wrap_width=180)
    pdf.set_font("Helvetica", "", 8)
    for row in report.rows:
        _write_pdf_lines(
            pdf,
            " | ".join(_report_row_values(row, report.testplan_columns)),
            line_height=5,
            wrap_width=180,
        )
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, report.additional_section_title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 10)
    _write_pdf_lines(pdf, "Section | Content", line_height=5, wrap_width=140)
    pdf.set_font("Helvetica", "", 10)
    for section in report.additional_sections:
        _write_pdf_lines(pdf, f"{section.title} | {section.body}", line_height=5, wrap_width=140)
    if report.branding.footer_text:
        _write_pdf_lines(pdf, report.branding.footer_text, line_height=5, wrap_width=140)
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
    branding_settings: Any = None,
    readiness_summary: Optional[dict[str, Any]] = None,
) -> str:
    use_libreoffice = os.getenv("EDQ_USE_LIBREOFFICE", "").lower() in ("1", "true", "yes")

    if use_libreoffice:
        try:
            docx_path = await generate_word_report(
                test_run,
                test_results,
                report_config,
                include_synopsis,
                enabled_test_ids,
                whitelist_entries,
                template_key,
                branding_settings,
                readiness_summary,
            )
            return await _generate_pdf_via_libreoffice(docx_path)
        except Exception:
            logger.warning("LibreOffice PDF conversion failed, falling back to fpdf2")

    return await _generate_pdf_via_fpdf(
        test_run,
        test_results,
        report_config,
        include_synopsis,
        enabled_test_ids,
        whitelist_entries,
        template_key,
        branding_settings,
        readiness_summary,
    )


async def generate_csv_report(
    test_run: Any,
    test_results: list[Any],
    report_config: Any = None,
    include_synopsis: bool = False,
    enabled_test_ids: Optional[list[str]] = None,
    whitelist_entries: Optional[list[Any]] = None,
    template_key: str = "generic",
    branding_settings: Any = None,
    readiness_summary: Optional[dict[str, Any]] = None,
) -> str:
    report = build_report_document(
        test_run,
        test_results,
        report_config,
        template_key,
        enabled_test_ids,
        whitelist_entries,
        include_synopsis,
        branding_settings,
        readiness_summary,
    )
    path = _output_path(test_run, template_key, ".csv")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([report.summary_section_title])
        writer.writerow(["Field", "Value"])
        writer.writerow(["Template Profile", TEMPLATE_INFO[report.template_key]["name"]])
        writer.writerow(["Company Name", report.branding.company_name])
        writer.writerow(
            [
                "Readiness Status",
                f"{report.readiness_summary.get('label', 'Unknown')} ({report.readiness_summary.get('score', 1)}/10)",
            ]
        )
        if report.branding.footer_text:
            writer.writerow(["Footer Text", report.branding.footer_text])
        for key, label in report.summary_fields:
            writer.writerow([label, report.metadata.get(key, "")])
        writer.writerow([report.summary_text_label, report.metadata.get("summary_text", "")])
        writer.writerow([])
        writer.writerow([report.testplan_section_title])
        writer.writerow([label for _, label in report.testplan_columns])
        for row in report.rows:
            writer.writerow(_report_row_values(row, report.testplan_columns))
        writer.writerow([])
        writer.writerow([report.additional_section_title])
        writer.writerow(["Section", "Content"])
        for section in report.additional_sections:
            writer.writerow([section.title, section.body])
    return str(path)
