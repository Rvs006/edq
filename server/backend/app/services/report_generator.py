"""Report Generation Engine — Excel and Word report generation.

V1: Synchronous generation using openpyxl and python-docx.
"""

import os
from datetime import datetime, timezone
from typing import List, Optional

from app.config import settings


async def generate_excel_report(test_run, test_results, report_config=None) -> str:
    """Generate an Excel report for a test run.
    
    Uses openpyxl to create a formatted Excel workbook with test results.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    wb = Workbook()

    # --- Summary Sheet ---
    ws_summary = wb.active
    ws_summary.title = "Summary"
    ws_summary.column_dimensions['A'].width = 25
    ws_summary.column_dimensions['B'].width = 40

    header_font = Font(name='Calibri', size=14, bold=True, color='1F4E79')
    label_font = Font(name='Calibri', size=11, bold=True)
    value_font = Font(name='Calibri', size=11)

    ws_summary['A1'] = "EDQ Device Qualification Report"
    ws_summary['A1'].font = Font(name='Calibri', size=18, bold=True, color='1F4E79')

    ws_summary['A3'] = "Test Run ID"
    ws_summary['A3'].font = label_font
    ws_summary['B3'] = test_run.id
    ws_summary['B3'].font = value_font

    ws_summary['A4'] = "Device ID"
    ws_summary['A4'].font = label_font
    ws_summary['B4'] = test_run.device_id

    ws_summary['A5'] = "Overall Verdict"
    ws_summary['A5'].font = label_font
    verdict_str = str(test_run.overall_verdict) if test_run.overall_verdict else "Incomplete"
    ws_summary['B5'] = verdict_str.upper()
    verdict_colors = {"pass": "27AE60", "fail": "E74C3C", "advisory": "F39C12"}
    ws_summary['B5'].font = Font(name='Calibri', size=11, bold=True, color=verdict_colors.get(verdict_str, "000000"))

    ws_summary['A7'] = "Tests Passed"
    ws_summary['B7'] = test_run.passed_tests
    ws_summary['A8'] = "Tests Failed"
    ws_summary['B8'] = test_run.failed_tests
    ws_summary['A9'] = "Advisories"
    ws_summary['B9'] = test_run.advisory_tests
    ws_summary['A10'] = "N/A"
    ws_summary['B10'] = test_run.na_tests
    ws_summary['A11'] = "Total Tests"
    ws_summary['B11'] = test_run.total_tests

    ws_summary['A13'] = "Generated"
    ws_summary['B13'] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # --- Test Results Sheet ---
    ws_results = wb.create_sheet("Test Results")
    headers = ["Test ID", "Test Name", "Tier", "Tool", "Essential", "Verdict", "Comment", "Compliance"]
    ws_results.column_dimensions['A'].width = 10
    ws_results.column_dimensions['B'].width = 35
    ws_results.column_dimensions['C'].width = 15
    ws_results.column_dimensions['D'].width = 12
    ws_results.column_dimensions['E'].width = 10
    ws_results.column_dimensions['F'].width = 12
    ws_results.column_dimensions['G'].width = 50
    ws_results.column_dimensions['H'].width = 30

    header_fill = PatternFill(start_color='1F4E79', end_color='1F4E79', fill_type='solid')
    header_font_white = Font(name='Calibri', size=11, bold=True, color='FFFFFF')

    for col, header in enumerate(headers, 1):
        cell = ws_results.cell(row=1, column=col, value=header)
        cell.font = header_font_white
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center')

    verdict_fills = {
        "pass": PatternFill(start_color='D5F5E3', end_color='D5F5E3', fill_type='solid'),
        "fail": PatternFill(start_color='FADBD8', end_color='FADBD8', fill_type='solid'),
        "advisory": PatternFill(start_color='FEF9E7', end_color='FEF9E7', fill_type='solid'),
        "na": PatternFill(start_color='EAEDED', end_color='EAEDED', fill_type='solid'),
    }

    for row_idx, result in enumerate(test_results, 2):
        verdict_val = result.verdict.value if hasattr(result.verdict, 'value') else str(result.verdict)
        tier_val = result.tier.value if hasattr(result.tier, 'value') else str(result.tier)
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

    # Save
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"EDQ_Report_{test_run.id[:8]}_{timestamp}.xlsx"
    file_path = os.path.join(settings.REPORT_DIR, filename)
    wb.save(file_path)
    return file_path


async def generate_word_report(test_run, test_results, report_config=None, include_synopsis=False) -> str:
    """Generate a Word report for a test run.
    
    Uses python-docx to create a formatted Word document.
    """
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()

    # Title
    title = doc.add_heading('EDQ Device Qualification Report', level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Executive Summary
    doc.add_heading('Executive Summary', level=1)
    verdict_str = str(test_run.overall_verdict) if test_run.overall_verdict else "Incomplete"
    summary = doc.add_paragraph()
    summary.add_run(f"Overall Verdict: ").bold = True
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
    doc.add_paragraph(f"Tests: {test_run.passed_tests} passed, {test_run.failed_tests} failed, {test_run.advisory_tests} advisories out of {test_run.total_tests} total")

    # Synopsis
    if include_synopsis and test_run.synopsis:
        doc.add_heading('Synopsis', level=1)
        doc.add_paragraph(test_run.synopsis)

    # Test Results Table
    doc.add_heading('Test Results', level=1)
    table = doc.add_table(rows=1, cols=5)
    table.style = 'Table Grid'
    headers = ["Test ID", "Test Name", "Essential", "Verdict", "Comment"]
    for i, header in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = header
        for paragraph in cell.paragraphs:
            for run in paragraph.runs:
                run.font.bold = True

    for result in test_results:
        row = table.add_row()
        verdict_val = result.verdict.value if hasattr(result.verdict, 'value') else str(result.verdict)
        row.cells[0].text = result.test_id
        row.cells[1].text = result.test_name
        row.cells[2].text = result.is_essential.upper()
        row.cells[3].text = verdict_val.upper()
        row.cells[4].text = result.comment_override or result.comment or ""

    # Compliance
    doc.add_heading('Compliance Mapping', level=1)
    doc.add_paragraph("This report maps test results to the following compliance frameworks:")
    doc.add_paragraph("• ISO 27001 — Information Security Management")
    doc.add_paragraph("• Cyber Essentials — UK Government Cyber Security Standard")
    doc.add_paragraph("• SOC2 — Service Organization Control 2")

    # Footer
    doc.add_paragraph()
    footer = doc.add_paragraph()
    footer.add_run(f"Report generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}").italic = True

    # Save
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"EDQ_Report_{test_run.id[:8]}_{timestamp}.docx"
    file_path = os.path.join(settings.REPORT_DIR, filename)
    doc.save(file_path)
    return file_path
