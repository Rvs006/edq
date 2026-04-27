"""Report generation routes."""

import json
import logging
import os
import re
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.database import get_db
from app.models.branding import BrandingSettings
from app.models.test_result import TestTier, TestVerdict
from app.models.protocol_whitelist import ProtocolWhitelist
from app.models.report_config import ReportConfig
from app.models.test_result import TestResult
from app.models.test_run import TestRun
from app.models.test_template import TestTemplate
from app.models.user import User, UserRole
from app.security.auth import get_current_active_user
from app.middleware.rate_limit import check_rate_limit, check_user_rate_limit
from app.services.report_generator import (
    generate_csv_report,
    generate_excel_report,
    generate_pdf_report,
    generate_word_report,
    get_available_templates,
)
from app.services.run_readiness import (
    build_run_readiness_summary,
    get_report_readiness_block_message,
)
from app.utils.audit import log_action

logger = logging.getLogger("edq.routes.reports")

router = APIRouter()
_REPORT_RUN_ID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)


class ReportRequest(BaseModel):
    test_run_id: str
    report_type: Literal["excel", "word", "pdf", "csv"] = "excel"
    report_config_id: Optional[str] = None
    include_synopsis: bool = False
    template_key: Literal["generic", "pelco_camera", "easyio_controller", "sauter_680_as"] = "generic"


@router.get("/templates")
async def list_report_templates(_: User = Depends(get_current_active_user)):
    """List available Excel report templates and their device categories."""
    return get_available_templates()


async def _load_run_context(data: ReportRequest, db: AsyncSession):
    result = await db.execute(
        select(TestRun)
        .options(selectinload(TestRun.device), selectinload(TestRun.engineer))
        .where(TestRun.id == data.test_run_id)
    )
    test_run = result.scalar_one_or_none()
    if not test_run:
        raise HTTPException(status_code=404, detail="Test run not found")

    results = await db.execute(
        select(TestResult)
        .where(TestResult.test_run_id == data.test_run_id)
        .order_by(TestResult.test_id)
    )
    test_results = results.scalars().all()

    report_config = None
    if data.report_config_id:
        config_result = await db.execute(
            select(ReportConfig).where(ReportConfig.id == data.report_config_id)
        )
        report_config = config_result.scalar_one_or_none()

    enabled_test_ids = None
    template = None
    if test_run.template_id:
        tmpl_result = await db.execute(
            select(TestTemplate).where(TestTemplate.id == test_run.template_id)
        )
        template = tmpl_result.scalar_one_or_none()
        if template and template.test_ids:
            raw_ids = template.test_ids
            if isinstance(raw_ids, str):
                try:
                    raw_ids = json.loads(raw_ids)
                except (json.JSONDecodeError, TypeError):
                    raw_ids = None
            if isinstance(raw_ids, list):
                enabled_test_ids = raw_ids

    whitelist_entries = None
    if template and getattr(template, "whitelist_id", None):
        wl_result = await db.execute(
            select(ProtocolWhitelist).where(ProtocolWhitelist.id == template.whitelist_id)
        )
        wl = wl_result.scalar_one_or_none()
        if wl and wl.entries:
            entries = wl.entries
            if isinstance(entries, str):
                try:
                    entries = json.loads(entries)
                except (json.JSONDecodeError, TypeError):
                    entries = None
            whitelist_entries = entries

    branding_result = await db.execute(select(BrandingSettings).limit(1))
    branding_settings = branding_result.scalar_one_or_none()

    return (
        test_run,
        test_results,
        report_config,
        enabled_test_ids,
        whitelist_entries,
        branding_settings,
    )


def _extract_report_run_id(filename: str) -> str | None:
    match = _REPORT_RUN_ID_RE.search(filename)
    if not match:
        return None
    return match.group(0)


@router.post("/generate")
async def generate_report(
    data: ReportRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Generate a report for a test run."""
    check_rate_limit(request, max_requests=120, window_seconds=60, action="report_generate")
    check_user_rate_limit(
        request,
        str(user.id),
        max_requests=60,
        window_seconds=60,
        action="report_generate",
    )

    # IDOR check: verify the user has access to this test run
    tr_result = await db.execute(select(TestRun).where(TestRun.id == data.test_run_id))
    tr = tr_result.scalar_one_or_none()
    if not tr:
        raise HTTPException(status_code=404, detail="Test run not found")
    if user.role == UserRole.ENGINEER and tr.engineer_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    test_run, test_results, report_config, enabled_test_ids, whitelist_entries, branding_settings = (
        await _load_run_context(data, db)
    )
    readiness_summary = build_run_readiness_summary(test_run, test_results)
    if not readiness_summary["report_ready"]:
        raise HTTPException(
            status_code=409,
            detail=get_report_readiness_block_message(readiness_summary),
        )

    try:
        if data.report_type == "excel":
            file_path = await generate_excel_report(
                test_run,
                test_results,
                report_config,
                template_key=data.template_key,
                enabled_test_ids=enabled_test_ids,
                whitelist_entries=whitelist_entries,
                include_synopsis=data.include_synopsis,
                branding_settings=branding_settings,
                readiness_summary=readiness_summary,
            )
        elif data.report_type == "word":
            file_path = await generate_word_report(
                test_run,
                test_results,
                report_config,
                include_synopsis=data.include_synopsis,
                enabled_test_ids=enabled_test_ids,
                whitelist_entries=whitelist_entries,
                template_key=data.template_key,
                branding_settings=branding_settings,
                readiness_summary=readiness_summary,
            )
        elif data.report_type == "pdf":
            file_path = await generate_pdf_report(
                test_run,
                test_results,
                report_config,
                include_synopsis=data.include_synopsis,
                enabled_test_ids=enabled_test_ids,
                whitelist_entries=whitelist_entries,
                template_key=data.template_key,
                branding_settings=branding_settings,
                readiness_summary=readiness_summary,
            )
        elif data.report_type == "csv":
            file_path = await generate_csv_report(
                test_run,
                test_results,
                report_config,
                include_synopsis=data.include_synopsis,
                enabled_test_ids=enabled_test_ids,
                whitelist_entries=whitelist_entries,
                template_key=data.template_key,
                branding_settings=branding_settings,
                readiness_summary=readiness_summary,
            )
        else:
            raise HTTPException(
                status_code=400, detail="Invalid report type. Use 'excel', 'word', 'pdf', or 'csv'."
            )

        filename = os.path.basename(file_path)
        await log_action(db, user, "report.generate", "report", data.test_run_id, {"type": data.report_type, "filename": filename}, request)
        return {
            "filename": filename,
            "report_type": data.report_type,
            "template_key": data.template_key,
            "download_url": f"/api/reports/download/{filename}",
            "readiness_summary": readiness_summary,
            "message": "Report generated successfully",
        }
    except RuntimeError as exc:
        logger.exception("Report generation failed for run %s", data.test_run_id)
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        logger.exception("Report generation failed for run %s", data.test_run_id)
        raise HTTPException(
            status_code=500, detail=f"Report generation failed: {type(exc).__name__}"
        )


@router.get("/download/{filename}")
async def download_report(
    filename: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Download a generated report file."""
    safe_filename = os.path.basename(filename)
    safe_filename = safe_filename.replace('"', '').replace(';', '').replace('\n', '').replace('\r', '')
    report_dir = Path(settings.REPORT_DIR).resolve()
    file_path_resolved = (report_dir / safe_filename).resolve()
    # Prevent path traversal — works correctly on case-insensitive Windows paths
    if not file_path_resolved.is_relative_to(report_dir):
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not file_path_resolved.exists():
        raise HTTPException(status_code=404, detail="Report file not found")

    run_id = _extract_report_run_id(safe_filename)
    if run_id is None:
        raise HTTPException(status_code=400, detail="Report filename is missing a run identifier")

    tr_result = await db.execute(select(TestRun).where(TestRun.id == run_id))
    tr = tr_result.scalar_one_or_none()
    if tr is None:
        raise HTTPException(status_code=404, detail="Associated test run not found")
    if user.role == UserRole.ENGINEER and tr.engineer_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    file_path_real = str(file_path_resolved)

    media_types = {
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pdf": "application/pdf",
        ".csv": "text/csv",
    }
    ext = os.path.splitext(safe_filename)[1].lower()
    media_type = media_types.get(ext, "application/octet-stream")

    return FileResponse(
        path=file_path_real,
        filename=safe_filename,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{safe_filename}"'},
    )


@router.get("/configs")
async def list_report_configs(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    result = await db.execute(select(ReportConfig).where(ReportConfig.is_active.is_(True)))
    return result.scalars().all()
