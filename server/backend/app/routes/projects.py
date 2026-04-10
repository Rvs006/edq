"""Project routes — CRUD for project folders."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
from pydantic import BaseModel
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
    name: str
    description: Optional[str] = None
    client_name: Optional[str] = None
    location: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    client_name: Optional[str] = None
    location: Optional[str] = None
    status: Optional[str] = None
    is_archived: Optional[bool] = None


class ProjectResponse(BaseModel):
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

    class Config:
        from_attributes = True


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
        query = query.where(Project.is_archived == False)
    if status:
        query = query.where(Project.status == status)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    result = await db.execute(query.order_by(Project.updated_at.desc()).offset(skip).limit(limit))
    projects = result.scalars().all()

    items = []
    for p in projects:
        dev_count = await db.execute(select(func.count()).where(Device.project_id == p.id))
        run_count = await db.execute(select(func.count()).where(TestRun.project_id == p.id))
        items.append({
            **ProjectResponse.model_validate(p).model_dump(),
            "device_count": dev_count.scalar() or 0,
            "test_run_count": run_count.scalar() or 0,
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
    updates = sanitize_dict(raw, ["name", "description", "client_name", "location"])
    # Preserve non-string fields that sanitize_dict may drop
    if "status" in raw:
        updates["status"] = raw["status"]
    if "is_archived" in raw:
        updates["is_archived"] = raw["is_archived"]
    for field, value in updates.items():
        setattr(project, field, value)

    await db.flush()
    await db.refresh(project)
    await log_action(db, user, "project.update", "project", project.id, data.model_dump(exclude_unset=True), request)
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
    devices = await db.execute(select(Device).where(Device.project_id == project_id))
    for d in devices.scalars().all():
        d.project_id = None
    runs = await db.execute(select(TestRun).where(TestRun.project_id == project_id))
    for r in runs.scalars().all():
        r.project_id = None

    await db.delete(project)
    await log_action(db, user, "project.delete", "project", project_id, {"name": project.name}, request)


@router.post("/{project_id}/devices")
async def add_devices_to_project(
    project_id: str,
    device_ids: list[str],
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
    return {"updated": updated}
