"""Device Profile management routes."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

from app.models.database import get_db
from app.models.device_profile import DeviceProfile
from app.models.test_run import TestRun
from app.models.user import User, UserRole
from app.models.protocol_whitelist import ProtocolWhitelist
from app.security.auth import get_current_active_user, require_role
from app.services.device_fingerprinter import fingerprinter
from app.utils.sanitize import sanitize_dict
from app.utils.audit import log_action

router = APIRouter()


class ProfileCreate(BaseModel):
    name: str = Field(..., max_length=128)
    manufacturer: str = Field(..., max_length=128)
    model_pattern: Optional[str] = None
    category: str = "unknown"
    description: Optional[str] = None
    default_whitelist_id: Optional[str] = None
    additional_tests: Optional[list] = None
    safe_mode: Optional[dict] = None
    fingerprint_rules: Optional[dict] = None


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    manufacturer: Optional[str] = None
    model_pattern: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    default_whitelist_id: Optional[str] = None
    additional_tests: Optional[list] = None
    safe_mode: Optional[dict] = None
    fingerprint_rules: Optional[dict] = None
    is_active: Optional[bool] = None


class ProfileResponse(BaseModel):
    id: str
    name: str
    manufacturer: str
    model_pattern: Optional[str] = None
    category: str
    description: Optional[str] = None
    default_whitelist_id: Optional[str] = None
    additional_tests: Optional[list] = None
    safe_mode: Optional[dict] = None
    fingerprint_rules: Optional[dict] = None
    auto_generated: bool = False
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


@router.get("/", response_model=List[ProfileResponse])
async def list_profiles(
    manufacturer: Optional[str] = None,
    category: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    query = select(DeviceProfile).where(DeviceProfile.is_active == True)
    if manufacturer:
        query = query.where(DeviceProfile.manufacturer.contains(manufacturer))
    if category:
        query = query.where(DeviceProfile.category == category)
    result = await db.execute(query.order_by(DeviceProfile.name).offset(skip).limit(limit))
    return result.scalars().all()


@router.post("/", response_model=ProfileResponse, status_code=201)
async def create_profile(
    data: ProfileCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["admin"])),
):
    clean = sanitize_dict(data.model_dump(), ["name", "manufacturer", "model_pattern", "category", "description"])
    profile = DeviceProfile(**clean, created_by=user.id)
    db.add(profile)
    await db.flush()
    await db.refresh(profile)
    await log_action(db, user, "create", "device_profile", profile.id, {"name": profile.name}, request)
    return profile


@router.get("/{profile_id}", response_model=ProfileResponse)
async def get_profile(
    profile_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    result = await db.execute(select(DeviceProfile).where(DeviceProfile.id == profile_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.patch("/{profile_id}", response_model=ProfileResponse)
async def update_profile(
    profile_id: str,
    data: ProfileUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["admin"])),
):
    result = await db.execute(select(DeviceProfile).where(DeviceProfile.id == profile_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    updates = sanitize_dict(data.model_dump(exclude_unset=True), ["name", "manufacturer", "model_pattern", "category", "description"])
    if "name" in updates:
        profile.name = updates["name"]
    if "manufacturer" in updates:
        profile.manufacturer = updates["manufacturer"]
    if "model_pattern" in updates:
        profile.model_pattern = updates["model_pattern"]
    if "category" in updates:
        profile.category = updates["category"]
    if "description" in updates:
        profile.description = updates["description"]
    if "default_whitelist_id" in updates:
        profile.default_whitelist_id = updates["default_whitelist_id"]
    if "default_whitelist_id" in updates and updates["default_whitelist_id"]:
        wl = await db.execute(select(ProtocolWhitelist).where(ProtocolWhitelist.id == updates["default_whitelist_id"]))
        if not wl.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Referenced whitelist not found")
    if "additional_tests" in updates:
        profile.additional_tests = updates["additional_tests"]
    if "safe_mode" in updates:
        profile.safe_mode = updates["safe_mode"]
    if "fingerprint_rules" in updates:
        profile.fingerprint_rules = updates["fingerprint_rules"]
    if "is_active" in updates:
        profile.is_active = updates["is_active"]
    await db.flush()
    await db.refresh(profile)
    await log_action(db, user, "update", "device_profile", profile_id, {"fields": list(updates.keys())}, request)
    return profile


@router.delete("/{profile_id}", status_code=204)
async def delete_profile(
    profile_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["admin"])),
):
    result = await db.execute(select(DeviceProfile).where(DeviceProfile.id == profile_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    profile.is_active = False
    await db.flush()
    await log_action(db, user, "delete", "device_profile", profile_id, {"name": profile.name}, request)
    await db.flush()


class AutoLearnRequest(BaseModel):
    test_run_id: str


class AutoLearnResponse(BaseModel):
    created: bool
    profile: Optional[ProfileResponse] = None
    message: str


@router.post("/auto-learn", response_model=AutoLearnResponse)
async def auto_learn_profile(
    data: AutoLearnRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["admin", "engineer"])),
):
    """Create a DeviceProfile from a completed test run's fingerprint data."""
    run_result = await db.execute(select(TestRun).where(TestRun.id == data.test_run_id))
    run = run_result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Test run not found")

    if user.role != UserRole.ADMIN and run.engineer_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    if not run.run_metadata or not run.run_metadata.get("fingerprint"):
        raise HTTPException(status_code=400, detail="No fingerprint data for this run")

    profile = await fingerprinter.learn_from_run(db, run.device_id, run.run_metadata)
    if not profile:
        return AutoLearnResponse(created=False, message="Profile already exists or insufficient data")

    await db.flush()
    await db.refresh(profile)
    await log_action(db, user, "create", "device_profile", profile.id, {"auto_learn": True, "run_id": data.test_run_id}, request)

    return AutoLearnResponse(
        created=True,
        profile=ProfileResponse.model_validate(profile),
        message=f"Created profile '{profile.name}'",
    )
