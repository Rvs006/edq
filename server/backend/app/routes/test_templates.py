"""Test Template management routes."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.models.database import get_db
from app.models.test_template import TestTemplate
from app.models.user import User
from app.schemas.test import TestTemplateCreate, TestTemplateUpdate, TestTemplateResponse
from app.security.auth import get_current_active_user, require_role
from app.services.test_library import UNIVERSAL_TESTS
from app.utils.sanitize import sanitize_dict
from app.utils.audit import log_action

router = APIRouter()


@router.get("/library")
async def get_test_library(_: User = Depends(get_current_active_user)):
    """Return the full universal test library (all 30 tests)."""
    return UNIVERSAL_TESTS


@router.get("/", response_model=List[TestTemplateResponse])
async def list_templates(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(TestTemplate).where(TestTemplate.is_active == True)
        .order_by(TestTemplate.name).offset(skip).limit(limit)
    )
    return result.scalars().all()


@router.post("/", response_model=TestTemplateResponse, status_code=201)
async def create_template(
    data: TestTemplateCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["admin"])),
):
    clean = sanitize_dict(data.model_dump(), ["name", "description"])
    # Deduplicate test_ids while preserving order
    if "test_ids" in clean and clean["test_ids"]:
        seen: set[str] = set()
        clean["test_ids"] = [t for t in clean["test_ids"] if t not in seen and not seen.add(t)]  # type: ignore[func-returns-value]
    template = TestTemplate(**clean, created_by=user.id)
    db.add(template)
    await db.flush()
    await db.refresh(template)
    await log_action(db, user, "create", "template", template.id, {"name": template.name}, request)
    return template


@router.get("/{template_id}", response_model=TestTemplateResponse)
async def get_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    result = await db.execute(select(TestTemplate).where(TestTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@router.patch("/{template_id}", response_model=TestTemplateResponse)
async def update_template(
    template_id: str,
    data: TestTemplateUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["admin"])),
):
    result = await db.execute(select(TestTemplate).where(TestTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    updates = sanitize_dict(data.model_dump(exclude_unset=True), ["name", "description"])
    if "name" in updates:
        template.name = updates["name"]
    if "description" in updates:
        template.description = updates["description"]
    if "test_ids" in updates:
        # Deduplicate while preserving order
        seen: set[str] = set()
        template.test_ids = [t for t in updates["test_ids"] if t not in seen and not seen.add(t)]  # type: ignore[func-returns-value]
    if "whitelist_id" in updates:
        template.whitelist_id = updates["whitelist_id"]
    if "cell_mappings" in updates:
        template.cell_mappings = updates["cell_mappings"]
    if "report_config" in updates:
        template.report_config = updates["report_config"]
    if "branding" in updates:
        template.branding = updates["branding"]
    if "is_default" in updates:
        template.is_default = updates["is_default"]
    if "is_active" in updates:
        template.is_active = updates["is_active"]
    await db.flush()
    await db.refresh(template)
    await log_action(db, user, "update", "template", template_id, {"fields": list(updates.keys())}, request)
    return template


@router.delete("/{template_id}", status_code=204)
async def delete_template(
    template_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["admin"])),
):
    result = await db.execute(select(TestTemplate).where(TestTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    template.is_active = False
    await log_action(db, user, "delete", "template", template_id, {"name": template.name}, request)
