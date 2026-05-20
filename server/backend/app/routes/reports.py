"""Report generation routes."""

import logging
import re
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.database import get_db
from app.models.report_config import ReportConfig
from app.models.test_run import TestRun
from app.models.user import User, UserRole
from app.security.auth import get_current_active_user
from app.middleware.rate_limit import check_rate_limit, check_user_rate_limit
from app.services.report_generator import (
    get_available_templates,
)
from app.services.report_artifacts import (
    ReportContextNotFoundError,
    ReportNotReadyError,
    generate_report_artifact,
    load_report_context,
)
from app.utils.audit import log_action

logger = logging.getLogger("edq.routes.reports")

router = APIRouter()
_REPORT_RUN_ID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)
_REPORT_FILENAME_RE = re.compile(
    r"^EDQ_Report_"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_"
    r"(?:generic|pelco_camera|easyio_controller|sauter_680_as)_"
    r"\d{8}_\d{6}\.(?:xlsx|docx)$",
    re.IGNORECASE,
)


def _resolve_report_download_path(filename: str) -> tuple[Path | None, str]:
    """Return a report path from the trusted report directory plus basename."""
    safe_filename = Path(filename).name
    if safe_filename != filename or not _REPORT_FILENAME_RE.fullmatch(safe_filename):
        raise HTTPException(status_code=400, detail="Invalid filename")

    report_dir = Path(settings.REPORT_DIR).resolve()
    for candidate in report_dir.iterdir():
        if candidate.name == safe_filename and candidate.is_file():
            file_path = candidate.resolve()
            if file_path.is_relative_to(report_dir):
                return file_path, safe_filename
    return None, safe_filename


class ReportRequest(BaseModel):
    test_run_id: str
    report_type: Literal["excel", "xlsx", "word", "docx"] = "excel"
    report_config_id: Optional[str] = None
    include_synopsis: bool = False
    template_key: Literal["generic"] = "generic"


@router.get("/templates")
async def list_report_templates(_: User = Depends(get_current_active_user)):
    """List available Excel report templates and their device categories."""
    return get_available_templates()


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

    try:
        context = await load_report_context(
            db,
            test_run_id=data.test_run_id,
            report_config_id=data.report_config_id,
        )
        artifact = await generate_report_artifact(
            context,
            report_type=data.report_type,
            template_key=data.template_key,
            include_synopsis=data.include_synopsis,
        )
        await log_action(
            db,
            user,
            "report.generate",
            "report",
            data.test_run_id,
            {"type": artifact.report_type, "filename": artifact.filename},
            request,
        )
        return {
            "filename": artifact.filename,
            "report_type": artifact.report_type,
            "template_key": data.template_key,
            "download_url": f"/api/reports/download/{artifact.filename}",
            "readiness_summary": artifact.readiness_summary,
            "message": "Report generated successfully",
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ReportContextNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ReportNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
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
    file_path_resolved, safe_filename = _resolve_report_download_path(filename)
    if file_path_resolved is None:
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

    media_types = {
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    ext = file_path_resolved.suffix.lower()
    media_type = media_types.get(ext, "application/octet-stream")

    return FileResponse(
        # The path is selected from REPORT_DIR after strict report filename validation.
        # codeql[py/path-injection]
        path=file_path_resolved,
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
