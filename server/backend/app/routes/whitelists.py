"""Protocol Whitelist management routes."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
import uuid

from app.models.database import get_db
from app.models.protocol_whitelist import ProtocolWhitelist
from app.models.user import User
from app.schemas.whitelist import WhitelistCreate, WhitelistUpdate, WhitelistResponse
from app.security.auth import get_current_active_user, require_role
from app.utils.sanitize import sanitize_dict
from app.utils.audit import log_action

router = APIRouter()


@router.get("/", response_model=List[WhitelistResponse])
async def list_whitelists(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(ProtocolWhitelist).order_by(ProtocolWhitelist.name).offset(skip).limit(limit)
    )
    return result.scalars().all()


@router.post("/", response_model=WhitelistResponse, status_code=201)
async def create_whitelist(
    data: WhitelistCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["admin"])),
):
    clean = sanitize_dict(data.model_dump(mode="json"), ["name", "description"])
    whitelist = ProtocolWhitelist(
        **clean,
        created_by=user.id,
    )
    db.add(whitelist)
    await db.flush()
    await db.refresh(whitelist)
    await log_action(db, user, "create", "whitelist", whitelist.id, {"name": whitelist.name}, request)
    return whitelist


@router.get("/{whitelist_id}", response_model=WhitelistResponse)
async def get_whitelist(
    whitelist_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    result = await db.execute(select(ProtocolWhitelist).where(ProtocolWhitelist.id == whitelist_id))
    whitelist = result.scalar_one_or_none()
    if not whitelist:
        raise HTTPException(status_code=404, detail="Whitelist not found")
    return whitelist


@router.put("/{whitelist_id}", response_model=WhitelistResponse)
async def update_whitelist(
    whitelist_id: str,
    data: WhitelistUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["admin"])),
):
    result = await db.execute(select(ProtocolWhitelist).where(ProtocolWhitelist.id == whitelist_id))
    whitelist = result.scalar_one_or_none()
    if not whitelist:
        raise HTTPException(status_code=404, detail="Whitelist not found")
    updates = sanitize_dict(data.model_dump(exclude_unset=True, mode="json"), ["name", "description"])
    if "name" in updates:
        whitelist.name = updates["name"]
    if "description" in updates:
        whitelist.description = updates["description"]
    if "is_default" in updates:
        whitelist.is_default = updates["is_default"]
    if "entries" in updates:
        whitelist.entries = updates["entries"]
    await db.flush()
    await db.refresh(whitelist)
    await log_action(db, user, "update", "whitelist", whitelist_id, {"fields": list(updates.keys())}, request)
    return whitelist


@router.delete("/{whitelist_id}", status_code=204)
async def delete_whitelist(
    whitelist_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["admin"])),
):
    result = await db.execute(select(ProtocolWhitelist).where(ProtocolWhitelist.id == whitelist_id))
    whitelist = result.scalar_one_or_none()
    if not whitelist:
        raise HTTPException(status_code=404, detail="Whitelist not found")
    await log_action(db, user, "delete", "whitelist", whitelist_id, {"name": whitelist.name}, request)
    await db.delete(whitelist)


@router.post("/{whitelist_id}/duplicate", response_model=WhitelistResponse)
async def duplicate_whitelist(
    whitelist_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["admin"])),
):
    """Clone an existing whitelist for customisation."""
    result = await db.execute(select(ProtocolWhitelist).where(ProtocolWhitelist.id == whitelist_id))
    original = result.scalar_one_or_none()
    if not original:
        raise HTTPException(status_code=404, detail="Whitelist not found")

    clone = ProtocolWhitelist(
        name=f"{original.name} (Copy)",
        description=original.description,
        is_default=False,
        entries=original.entries,
        created_by=user.id,
    )
    db.add(clone)
    await db.flush()
    await db.refresh(clone)
    await log_action(db, user, "duplicate", "whitelist", clone.id, {"source_id": whitelist_id}, request)
    return clone
