"""Report generation routes."""

import json
import logging
import os
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.database import get_db
from app.models.protocol_whitelist import ProtocolWhitelist
from app.models.report_config import ReportConfig
from app.models.test_result import TestResult
from app.models.test_run import TestRun
from app.models.test_template import TestTemplate
from app.models.user import User
from app.security.auth import get_current_active_user
from app.models.user import UserRole
from app.middleware.rate_limit import check_rate_limit
from app.utils.audit import log_action
from app.services.report_generator import (
    generate_excel_report,
    generate_pdf_report,
    generate_word_report,
    get_available_templates,
)

logger = logging.getLogger("edq.routes.reports")

router = APIRouter()


class ReportRequest(BaseModel):
    test_run_id: str
    report_type: Literal["excel", "word", "pdf"] = "excel"
    report_config_id: Optional[str] = None
    include_synopsis: bool = False
    template_key: Literal["generic", "pelco_camera", "easyio_controller"] = "generic"


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

    return test_run, test_results, report_config, enabled_test_ids, whitelist_entries


@router.post("/generate")
async def generate_report(
    data: ReportRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Generate a report for a test run."""
    check_rate_limit(request, max_requests=5, window_seconds=60, action="report_generate")

    # IDOR check: verify the user has access to this test run
    tr_result = await db.execute(select(TestRun).where(TestRun.id == data.test_run_id))
    tr = tr_result.scalar_one_or_none()
    if not tr:
        raise HTTPException(status_code=404, detail="Test run not found")
    if user.role == UserRole.ENGINEER and tr.engineer_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    test_run, test_results, report_config, enabled_test_ids, whitelist_entries = (
        await _load_run_context(data, db)
    )

    try:
        if data.report_type == "excel":
            file_path = await generate_excel_report(
                test_run,
                test_results,
                report_config,
                template_key=data.template_key,
                enabled_test_ids=enabled_test_ids,
            )
        elif data.report_type == "word":
            file_path = await generate_word_report(
                test_run,
                test_results,
                report_config,
                include_synopsis=data.include_synopsis,
                enabled_test_ids=enabled_test_ids,
                whitelist_entries=whitelist_entries,
            )
        elif data.report_type == "pdf":
            file_path = await generate_pdf_report(
                test_run,
                test_results,
                report_config,
                include_synopsis=data.include_synopsis,
                enabled_test_ids=enabled_test_ids,
                whitelist_entries=whitelist_entries,
            )
        else:
            raise HTTPException(
                status_code=400, detail="Invalid report type. Use 'excel', 'word', or 'pdf'."
            )

        filename = os.path.basename(file_path)
        await log_action(db, user, "report.generate", "report", data.test_run_id, {"type": data.report_type, "filename": filename}, request)
        return {
            "filename": filename,
            "file_path": file_path,
            "report_type": data.report_type,
            "template_key": data.template_key if data.report_type == "excel" else None,
            "download_url": f"/api/reports/download/{filename}",
            "message": "Report generated successfully",
        }
    except Exception:
        logger.exception("Report generation failed for run %s", data.test_run_id)
        raise HTTPException(
            status_code=500, detail="Report generation failed"
        )


@router.get("/download/{filename}")
async def download_report(filename: str, _: User = Depends(get_current_active_user)):
    """Download a generated report file."""
    safe_filename = os.path.basename(filename)
    file_path = os.path.join(settings.REPORT_DIR, safe_filename)
    # Prevent path traversal by verifying the resolved path stays inside REPORT_DIR
    report_dir_real = os.path.realpath(settings.REPORT_DIR)
    file_path_real = os.path.realpath(file_path)
    if not file_path_real.startswith(report_dir_real + os.sep):
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not os.path.exists(file_path_real):
        raise HTTPException(status_code=404, detail="Report file not found")

    media_types = {
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pdf": "application/pdf",
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
    result = await db.execute(select(ReportConfig).where(ReportConfig.is_active == True))
    return result.scalars().all()
