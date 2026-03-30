"""AI Synopsis Generator routes."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional

from app.models.database import get_db
from app.models.test_run import TestRun
from app.models.test_result import TestResult
from app.models.user import User
from app.security.auth import get_current_active_user, require_role
from app.models.user import UserRole
from app.middleware.rate_limit import check_rate_limit
from app.config import settings
from app.utils.audit import log_action

logger = logging.getLogger("edq.routes.synopsis")

router = APIRouter()


class SynopsisRequest(BaseModel):
    test_run_id: str
    custom_context: Optional[str] = None


class SynopsisApproval(BaseModel):
    test_run_id: str
    edited_text: str


@router.post("/generate")
async def generate_synopsis(
    data: SynopsisRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Generate an AI draft synopsis for a test run."""
    check_rate_limit(request, max_requests=3, window_seconds=60, action="synopsis_generate")

    if not settings.AI_API_KEY:
        raise HTTPException(status_code=503, detail="AI synopsis feature is not configured. Set AI_API_KEY in environment.")

    # Get test run and verify ownership
    run_result = await db.execute(select(TestRun).where(TestRun.id == data.test_run_id))
    test_run = run_result.scalar_one_or_none()
    if not test_run:
        raise HTTPException(status_code=404, detail="Test run not found")
    if user.role == UserRole.ENGINEER and test_run.engineer_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    results = await db.execute(
        select(TestResult).where(TestResult.test_run_id == data.test_run_id).order_by(TestResult.test_id)
    )
    test_results = results.scalars().all()

    # Build anonymised prompt
    prompt = _build_synopsis_prompt(test_run, test_results, data.custom_context)

    try:
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.post(
                settings.AI_API_URL,
                headers={
                    "Authorization": f"Bearer {settings.AI_API_KEY}",
                    "content-type": "application/json",
                },
                json={
                    "model": settings.AI_MODEL,
                    "max_tokens": 2000,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=60.0,
            )
            response.raise_for_status()
            ai_response = response.json()
            synopsis_text = ai_response["content"][0]["text"]
    except Exception:
        logger.exception("AI synopsis generation failed for run %s", data.test_run_id)
        raise HTTPException(status_code=500, detail="AI synopsis generation failed")

    # Update test run with draft
    test_run.synopsis = f"[AI-DRAFTED] {synopsis_text}"
    test_run.synopsis_status = "ai_draft"

    await log_action(db, user, "synopsis.generate", "synopsis", data.test_run_id, {"status": "ai_draft"}, request)
    return {
        "synopsis": synopsis_text,
        "status": "ai_draft",
        "message": "AI draft generated. Requires human review and approval before inclusion in reports.",
    }


@router.post("/approve")
async def approve_synopsis(
    data: SynopsisApproval,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["reviewer", "admin"])),
):
    """Approve (and optionally edit) an AI-drafted synopsis."""
    run_result = await db.execute(select(TestRun).where(TestRun.id == data.test_run_id))
    test_run = run_result.scalar_one_or_none()
    if not test_run:
        raise HTTPException(status_code=404, detail="Test run not found")

    test_run.synopsis = data.edited_text
    test_run.synopsis_status = "human_approved"

    await log_action(db, user, "synopsis.approve", "synopsis", data.test_run_id, {"status": "human_approved"}, request)
    return {"message": "Synopsis approved and saved.", "status": "human_approved"}


def _build_synopsis_prompt(test_run, test_results, custom_context=None) -> str:
    """Build an anonymised prompt for AI synopsis generation."""
    results_summary = []
    for r in test_results:
        results_summary.append(f"- {r.test_id} ({r.test_name}): {r.verdict.value if hasattr(r.verdict, 'value') else r.verdict}")

    prompt = f"""You are a network security engineer writing a technical synopsis for a device qualification report.

Based on the following test results, write a professional narrative summary (3-5 paragraphs) that:
1. Summarises the overall security posture of the device
2. Highlights critical findings (failures and advisories)
3. Notes positive security features (passes)
4. Provides actionable recommendations
5. Uses professional, technical language suitable for enterprise clients

Test Results:
{chr(10).join(results_summary)}

Overall Verdict: {test_run.overall_verdict or 'incomplete'}
Tests Passed: {test_run.passed_tests}/{test_run.total_tests}
Tests Failed: {test_run.failed_tests}
Advisories: {test_run.advisory_tests}

{f'Additional Context: {custom_context}' if custom_context else ''}

Write the synopsis now. Do not include any client names, IP addresses, or identifying information."""

    return prompt
