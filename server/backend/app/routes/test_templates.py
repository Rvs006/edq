"""Test Template management routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.models.database import get_db
from app.models.test_template import TestTemplate
from app.models.user import User
from app.schemas.test import TestTemplateCreate, TestTemplateUpdate, TestTemplateResponse
from app.security.auth import get_current_active_user, require_role
from app.services.test_library import UNIVERSAL_TESTS

router = APIRouter()


@router.get("/library")
async def get_test_library(_: User = Depends(get_current_active_user)):
    """Return the full universal test library (all 30 tests)."""
    return UNIVERSAL_TESTS


@router.get("/", response_model=List[TestTemplateResponse])
async def list_templates(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(TestTemplate).where(TestTemplate.is_active == True).order_by(TestTemplate.name)
    )
    return result.scalars().all()


@router.post("/", response_model=TestTemplateResponse, status_code=201)
async def create_template(
    data: TestTemplateCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["admin"])),
):
    template = TestTemplate(**data.model_dump(), created_by=user.id)
    db.add(template)
    await db.flush()
    await db.refresh(template)
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
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(["admin"])),
):
    result = await db.execute(select(TestTemplate).where(TestTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    updates = data.model_dump(exclude_unset=True)
    if "name" in updates:
        template.name = updates["name"]
    if "description" in updates:
        template.description = updates["description"]
    if "test_ids" in updates:
        template.test_ids = updates["test_ids"]
    if "device_category" in updates:
        template.device_category = updates["device_category"]
    if "is_default" in updates:
        template.is_default = updates["is_default"]
    await db.flush()
    await db.refresh(template)
    return template


@router.delete("/{template_id}", status_code=204)
async def delete_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(["admin"])),
):
    result = await db.execute(select(TestTemplate).where(TestTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    template.is_active = False
