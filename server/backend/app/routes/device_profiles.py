"""Device Profile management routes."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

from app.models.database import get_db
from app.models.device_profile import DeviceProfile
from app.models.user import User
from app.security.auth import get_current_active_user, require_role

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
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


@router.get("/", response_model=List[ProfileResponse])
async def list_profiles(
    manufacturer: Optional[str] = None,
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    query = select(DeviceProfile).where(DeviceProfile.is_active == True)
    if manufacturer:
        query = query.where(DeviceProfile.manufacturer.contains(manufacturer))
    if category:
        query = query.where(DeviceProfile.category == category)
    result = await db.execute(query.order_by(DeviceProfile.name))
    return result.scalars().all()


@router.post("/", response_model=ProfileResponse, status_code=201)
async def create_profile(
    data: ProfileCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["admin"])),
):
    profile = DeviceProfile(**data.model_dump(), created_by=user.id)
    db.add(profile)
    await db.flush()
    await db.refresh(profile)
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
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(["admin"])),
):
    result = await db.execute(select(DeviceProfile).where(DeviceProfile.id == profile_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    await db.flush()
    await db.refresh(profile)
    return profile


@router.delete("/{profile_id}", status_code=204)
async def delete_profile(
    profile_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(["admin"])),
):
    result = await db.execute(select(DeviceProfile).where(DeviceProfile.id == profile_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    profile.is_active = False
