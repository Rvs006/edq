"""Branding settings routes — custom report branding configuration."""

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.branding import BrandingSettings
from app.models.database import get_db
from app.models.user import User
from app.security.auth import get_current_active_user, require_role
from app.utils.audit import log_action

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
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["admin"])),
):
    """Update branding settings. Requires admin role."""

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
    await log_action(db, user, "branding.update", "branding", branding.id, {"company_name": branding.company_name}, request)
    return branding


_ALLOWED_LOGO_EXTENSIONS = {".png", ".jpg", ".jpeg"}
_ALLOWED_LOGO_MIME_TYPES = {"image/png", "image/jpeg", "image/jpg"}

@router.post("/branding/logo", response_model=BrandingResponse)
async def upload_branding_logo(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["admin"])),
):
    """Upload a company logo for report branding."""
    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _ALLOWED_LOGO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="File must be PNG or JPEG")

    if not file.content_type or file.content_type not in _ALLOWED_LOGO_MIME_TYPES:
        raise HTTPException(status_code=400, detail="File must be PNG or JPEG")

    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Logo file must be under 5MB")

    upload_dir = os.path.join(settings.UPLOAD_DIR, "branding")
    os.makedirs(upload_dir, exist_ok=True)

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

    branding.logo_path = logo_filename
    await db.flush()
    await db.refresh(branding)
    await log_action(db, user, "branding.logo_upload", "branding", branding.id, {"filename": logo_filename}, request)
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

    # Path traversal protection: ensure logo_path stays inside the upload directory
    upload_dir_real = os.path.realpath(os.path.join(settings.UPLOAD_DIR, "branding"))
    logo_path_real = os.path.realpath(os.path.join(upload_dir_real, branding.logo_path))
    if not logo_path_real.startswith(upload_dir_real + os.sep) and logo_path_real != upload_dir_real:
        raise HTTPException(status_code=403, detail="Invalid logo path")

    if not os.path.isfile(logo_path_real):
        raise HTTPException(status_code=404, detail="Logo file not found on disk")
    return FileResponse(logo_path_real)
