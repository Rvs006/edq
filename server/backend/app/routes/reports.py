"""Report generation routes."""

import os
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.database import get_db
from app.models.report_config import ReportConfig
from app.models.test_result import TestResult
from app.models.test_run import TestRun
from app.models.user import User
from app.security.auth import get_current_active_user
from app.services.report_generator import (
    generate_excel_report,
    generate_word_report,
    get_available_templates,
)

router = APIRouter()


class ReportRequest(BaseModel):
    test_run_id: str
    report_type: str = "excel"
    report_config_id: Optional[str] = None
    include_synopsis: bool = False
    template_key: Literal["generic", "pelco_camera", "easyio_controller"] = "generic"


@router.get("/templates")
async def list_report_templates(_: User = Depends(get_current_active_user)):
    """List available Excel report templates and their device categories."""
    return get_available_templates()


@router.post("/generate")
async def generate_report(
    data: ReportRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Generate a report for a test run."""
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

    try:
        if data.report_type == "excel":
            file_path = await generate_excel_report(
                test_run,
                test_results,
                report_config,
                template_key=data.template_key,
            )
        elif data.report_type == "word":
            file_path = await generate_word_report(
                test_run, test_results, report_config, data.include_synopsis
            )
        else:
            raise HTTPException(
                status_code=400, detail="Invalid report type. Use 'excel' or 'word'."
            )

        filename = os.path.basename(file_path)
        return {
            "filename": filename,
            "file_path": file_path,
            "report_type": data.report_type,
            "template_key": data.template_key if data.report_type == "excel" else None,
            "download_url": f"/api/reports/download/{filename}",
            "message": "Report generated successfully",
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Report generation failed: {str(e)}"
        )


@router.get("/download/{filename}")
async def download_report(filename: str, _: User = Depends(get_current_active_user)):
    """Download a generated report file."""
    safe_filename = os.path.basename(filename)
    file_path = os.path.join(settings.REPORT_DIR, safe_filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Report file not found")

    media_types = {
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pdf": "application/pdf",
    }
    ext = os.path.splitext(safe_filename)[1].lower()
    media_type = media_types.get(ext, "application/octet-stream")

    return FileResponse(
        path=file_path,
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
