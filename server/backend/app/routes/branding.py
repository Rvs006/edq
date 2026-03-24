"""Branding settings routes — custom report branding configuration."""

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.branding import BrandingSettings
from app.models.database import get_db
from app.models.user import User
from app.security.auth import get_current_active_user

logger = logging.getLogger("edq.routes.branding")

router = APIRouter()


class BrandingResponse(BaseModel):
    id: str
    company_name: Optional[str] = "Electracom"
    logo_path: Optional[str] = None
    primary_color: Optional[str] = "#2563eb"
    footer_text: Optional[str] = ""

    class Config:
        from_attributes = True


class BrandingUpdate(BaseModel):
    company_name: Optional[str] = Field(None, max_length=255)
    primary_color: Optional[str] = Field(None, max_length=7)
    footer_text: Optional[str] = None


@router.get("/branding", response_model=BrandingResponse)
async def get_branding(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """Get current branding settings."""
    result = await db.execute(select(BrandingSettings).limit(1))
    branding = result.scalar_one_or_none()
    if not branding:
        branding = BrandingSettings()
        db.add(branding)
        await db.flush()
        await db.refresh(branding)
    return branding


@router.put("/branding", response_model=BrandingResponse)
async def update_branding(
    data: BrandingUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Update branding settings. Requires admin role."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    result = await db.execute(select(BrandingSettings).limit(1))
    branding = result.scalar_one_or_none()
    if not branding:
        branding = BrandingSettings()
        db.add(branding)
        await db.flush()

    if data.company_name is not None:
        branding.company_name = data.company_name
    if data.primary_color is not None:
        branding.primary_color = data.primary_color
    if data.footer_text is not None:
        branding.footer_text = data.footer_text

    await db.flush()
    await db.refresh(branding)
    return branding


@router.post("/branding/logo", response_model=BrandingResponse)
async def upload_branding_logo(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Upload a company logo for report branding."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image (PNG, JPEG, SVG)")

    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Logo file must be under 5MB")

    upload_dir = os.path.join(settings.UPLOAD_DIR, "branding")
    os.makedirs(upload_dir, exist_ok=True)

    ext = os.path.splitext(file.filename or "logo.png")[1] or ".png"
    logo_filename = f"company_logo{ext}"
    logo_path = os.path.join(upload_dir, logo_filename)

    with open(logo_path, "wb") as f:
        f.write(contents)

    result = await db.execute(select(BrandingSettings).limit(1))
    branding = result.scalar_one_or_none()
    if not branding:
        branding = BrandingSettings()
        db.add(branding)
        await db.flush()

    branding.logo_path = logo_path
    await db.flush()
    await db.refresh(branding)
    return branding


@router.get("/branding/logo")
async def get_branding_logo(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """Serve the uploaded company logo file."""
    result = await db.execute(select(BrandingSettings).limit(1))
    branding = result.scalar_one_or_none()
    if not branding or not branding.logo_path:
        raise HTTPException(status_code=404, detail="No logo uploaded")
    if not os.path.isfile(branding.logo_path):
        raise HTTPException(status_code=404, detail="Logo file not found on disk")
    return FileResponse(branding.logo_path)
