"""Report generation routes."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from pydantic import BaseModel

from app.models.database import get_db
from app.models.test_run import TestRun
from app.models.test_result import TestResult
from app.models.report_config import ReportConfig
from app.models.user import User
from app.security.auth import get_current_active_user
from app.services.report_generator import generate_excel_report, generate_word_report

router = APIRouter()


class ReportRequest(BaseModel):
    test_run_id: str
    report_type: str = "excel"  # excel, word
    report_config_id: Optional[str] = None
    include_synopsis: bool = False


@router.post("/generate")
async def generate_report(
    data: ReportRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Generate a report for a test run."""
    # Get test run
    result = await db.execute(select(TestRun).where(TestRun.id == data.test_run_id))
    test_run = result.scalar_one_or_none()
    if not test_run:
        raise HTTPException(status_code=404, detail="Test run not found")

    # Get test results
    results = await db.execute(
        select(TestResult).where(TestResult.test_run_id == data.test_run_id).order_by(TestResult.test_id)
    )
    test_results = results.scalars().all()

    # Get report config if specified
    report_config = None
    if data.report_config_id:
        config_result = await db.execute(select(ReportConfig).where(ReportConfig.id == data.report_config_id))
        report_config = config_result.scalar_one_or_none()

    try:
        if data.report_type == "excel":
            file_path = await generate_excel_report(test_run, test_results, report_config)
        elif data.report_type == "word":
            file_path = await generate_word_report(test_run, test_results, report_config, data.include_synopsis)
        else:
            raise HTTPException(status_code=400, detail="Invalid report type. Use 'excel' or 'word'.")

        return {"file_path": file_path, "report_type": data.report_type, "message": "Report generated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Report generation failed: {str(e)}")


@router.get("/download/{filename}")
async def download_report(filename: str, _: User = Depends(get_current_active_user)):
    """Download a generated report."""
    import os
    from app.config import settings
    file_path = os.path.join(settings.REPORT_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Report file not found")
    return FileResponse(file_path, filename=filename)


@router.get("/configs")
async def list_report_configs(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    result = await db.execute(select(ReportConfig).where(ReportConfig.is_active == True))
    return result.scalars().all()
