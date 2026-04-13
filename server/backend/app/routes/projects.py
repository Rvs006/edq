"""Project routes — CRUD for project folders."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime

from app.models.database import get_db
from app.models.project import Project
from app.models.device import Device
from app.models.test_run import TestRun
from app.models.user import User
from app.security.auth import get_current_active_user
from app.utils.audit import log_action
from app.utils.sanitize import sanitize_dict
import uuid


router = APIRouter()


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=4000)
    client_name: Optional[str] = Field(None, max_length=255)
    location: Optional[str] = Field(None, max_length=255)


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=4000)
    client_name: Optional[str] = Field(None, max_length=255)
    location: Optional[str] = Field(None, max_length=255)
    status: Optional[Literal["active", "archived", "completed"]] = None
    is_archived: Optional[bool] = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: Optional[str] = None
    status: str
    created_by: str
    client_name: Optional[str] = None
    location: Optional[str] = None
    device_count: int = 0
    test_run_count: int = 0
    created_at: datetime
    updated_at: datetime
    is_archived: bool

@router.get("/")
async def list_projects(
    status: Optional[str] = None,
    include_archived: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    query = select(Project)
    if not include_archived:
        query = query.where(Project.is_archived.is_(False))
    if status:
        query = query.where(Project.status == status)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    device_count_sq = (
        select(Device.project_id.label("project_id"), func.count().label("device_count"))
        .group_by(Device.project_id)
        .subquery()
    )
    run_count_sq = (
        select(TestRun.project_id.label("project_id"), func.count().label("test_run_count"))
        .group_by(TestRun.project_id)
        .subquery()
    )

    project_query = (
        select(
            Project,
            func.coalesce(device_count_sq.c.device_count, 0).label("device_count"),
            func.coalesce(run_count_sq.c.test_run_count, 0).label("test_run_count"),
        )
        .select_from(Project)
        .outerjoin(device_count_sq, device_count_sq.c.project_id == Project.id)
        .outerjoin(run_count_sq, run_count_sq.c.project_id == Project.id)
    )

    if not include_archived:
        project_query = project_query.where(Project.is_archived.is_(False))
    if status:
        project_query = project_query.where(Project.status == status)

    project_query = project_query.order_by(Project.updated_at.desc()).offset(skip).limit(limit)

    result = await db.execute(project_query)
    items = []
    for project, device_count, test_run_count in result.all():
        items.append({
            **ProjectResponse.model_validate(project).model_dump(),
            "device_count": device_count,
            "test_run_count": test_run_count,
        })

    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.post("/", status_code=201)
async def create_project(
    data: ProjectCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    clean = sanitize_dict(data.model_dump(), ["name", "description", "client_name", "location"])
    project = Project(
        id=str(uuid.uuid4()),
        name=clean["name"],
        description=clean.get("description"),
        client_name=clean.get("client_name"),
        location=clean.get("location"),
        created_by=user.id,
    )
    db.add(project)
    await db.flush()
    await db.refresh(project)
    await log_action(db, user, "project.create", "project", project.id, {"name": data.name}, request)
    await db.commit()
    return ProjectResponse.model_validate(project)


@router.get("/{project_id}")
async def get_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    dev_count = await db.execute(select(func.count()).where(Device.project_id == project_id))
    run_count = await db.execute(select(func.count()).where(TestRun.project_id == project_id))

    return {
        **ProjectResponse.model_validate(project).model_dump(),
        "device_count": dev_count.scalar() or 0,
        "test_run_count": run_count.scalar() or 0,
    }


@router.patch("/{project_id}")
async def update_project(
    project_id: str,
    data: ProjectUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    raw = data.model_dump(exclude_unset=True)
    updates = sanitize_dict(raw, ["name", "description", "client_name", "location", "status"])
    # Preserve non-string fields that sanitize_dict may drop
    if "is_archived" in raw:
        updates["is_archived"] = raw["is_archived"]
    for field, value in updates.items():
        setattr(project, field, value)

    await db.flush()
    await db.refresh(project)
    await log_action(db, user, "project.update", "project", project.id, data.model_dump(exclude_unset=True), request)
    await db.commit()
    return ProjectResponse.model_validate(project)


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Unlink devices and test runs (don't delete them)
    await db.execute(
        update(Device)
        .where(Device.project_id == project_id)
        .values(project_id=None)
    )
    await db.execute(
        update(TestRun)
        .where(TestRun.project_id == project_id)
        .values(project_id=None)
    )

    await db.delete(project)
    await log_action(db, user, "project.delete", "project", project_id, {"name": project.name}, request)
    await db.commit()


@router.post("/{project_id}/devices")
async def add_devices_to_project(
    project_id: str,
    device_ids: list[str],
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    updated = 0
    for did in device_ids:
        dev_result = await db.execute(select(Device).where(Device.id == did))
        device = dev_result.scalar_one_or_none()
        if device:
            device.project_id = project_id
            updated += 1

    await db.flush()
    await log_action(
        db,
        user,
        "project.devices_added",
        "project",
        project_id,
        {"device_ids": device_ids, "updated": updated},
        request,
    )
    await db.commit()
    return {"updated": updated}
