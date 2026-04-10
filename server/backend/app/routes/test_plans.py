"""Test Plan management routes — custom test configurations."""

import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.database import get_db
from app.models.test_plan import TestPlan
from app.models.test_template import TestTemplate
from app.models.user import User
from app.security.auth import get_current_active_user, require_role
from app.utils.audit import log_action
from app.utils.sanitize import sanitize_dict

logger = logging.getLogger("edq.routes.test_plans")

router = APIRouter()


class TestConfigItem(BaseModel):
    test_id: str
    enabled: bool = True
    tier_override: Optional[str] = None
    custom: Optional[dict] = None


class TestPlanCreate(BaseModel):
    name: str = Field(..., max_length=128)
    description: Optional[str] = None
    base_template_id: Optional[str] = None
    test_configs: List[TestConfigItem]


class TestPlanUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=128)
    description: Optional[str] = None
    base_template_id: Optional[str] = None
    test_configs: Optional[List[TestConfigItem]] = None


class TestPlanResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    base_template_id: Optional[str] = None
    test_configs: list
    created_by: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


@router.get("/", response_model=List[TestPlanResponse])
async def list_test_plans(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(TestPlan).order_by(TestPlan.created_at.desc()).offset(skip).limit(limit)
    )
    return result.scalars().all()


@router.post("/", response_model=TestPlanResponse, status_code=201)
async def create_test_plan(
    data: TestPlanCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["admin", "engineer"])),
):
    if data.base_template_id:
        t_result = await db.execute(
            select(TestTemplate).where(TestTemplate.id == data.base_template_id)
        )
        if not t_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Base template not found")

    clean = sanitize_dict(data.model_dump(), ["name", "description"])
    plan = TestPlan(
        name=clean["name"],
        description=clean.get("description"),
        base_template_id=data.base_template_id,
        test_configs=[c.model_dump() for c in data.test_configs],
        created_by=user.id,
    )
    db.add(plan)
    await db.flush()
    await db.refresh(plan)
    await log_action(db, user, "test_plan.create", "test_plan", plan.id, {"name": plan.name}, request)
    return plan


@router.get("/{plan_id}", response_model=TestPlanResponse)
async def get_test_plan(
    plan_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    result = await db.execute(select(TestPlan).where(TestPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Test plan not found")
    return plan


@router.put("/{plan_id}", response_model=TestPlanResponse)
async def update_test_plan(
    plan_id: str,
    data: TestPlanUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["admin", "engineer"])),
):
    result = await db.execute(select(TestPlan).where(TestPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Test plan not found")

    clean = sanitize_dict(data.model_dump(exclude_unset=True), ["name", "description"])
    updated_fields = []
    if data.name is not None:
        plan.name = clean["name"]
        updated_fields.append("name")
    if data.description is not None:
        plan.description = clean["description"]
        updated_fields.append("description")
    if data.base_template_id is not None:
        plan.base_template_id = data.base_template_id
        updated_fields.append("base_template_id")
    if data.test_configs is not None:
        plan.test_configs = [c.model_dump() for c in data.test_configs]
        updated_fields.append("test_configs")

    await db.flush()
    await db.refresh(plan)
    await log_action(db, user, "test_plan.update", "test_plan", plan_id, {"fields": updated_fields}, request)
    return plan


@router.delete("/{plan_id}", status_code=204)
async def delete_test_plan(
    plan_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["admin"])),
):
    result = await db.execute(select(TestPlan).where(TestPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Test plan not found")
    await log_action(db, user, "test_plan.delete", "test_plan", plan_id, {"name": plan.name}, request)
    await db.delete(plan)


@router.post("/{plan_id}/clone", response_model=TestPlanResponse, status_code=201)
async def clone_test_plan(
    plan_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    result = await db.execute(select(TestPlan).where(TestPlan.id == plan_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Test plan not found")

    clone = TestPlan(
        name=f"{source.name} (Copy)",
        description=source.description,
        base_template_id=source.base_template_id,
        test_configs=source.test_configs,
        created_by=user.id,
    )
    db.add(clone)
    await db.flush()
    await db.refresh(clone)
    await log_action(db, user, "test_plan.clone", "test_plan", clone.id, {"source_id": plan_id}, request)
    return clone
