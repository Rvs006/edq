"""Protocol Whitelist management routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
import uuid

from app.models.database import get_db
from app.models.protocol_whitelist import ProtocolWhitelist
from app.models.user import User
from app.schemas.whitelist import WhitelistCreate, WhitelistUpdate, WhitelistResponse
from app.security.auth import get_current_active_user, require_role

router = APIRouter()


@router.get("/", response_model=List[WhitelistResponse])
async def list_whitelists(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    result = await db.execute(select(ProtocolWhitelist).order_by(ProtocolWhitelist.name))
    return result.scalars().all()


@router.post("/", response_model=WhitelistResponse, status_code=201)
async def create_whitelist(
    data: WhitelistCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["admin"])),
):
    whitelist = ProtocolWhitelist(
        **data.model_dump(mode="json"),
        created_by=user.id,
    )
    db.add(whitelist)
    await db.flush()
    await db.refresh(whitelist)
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
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(["admin"])),
):
    result = await db.execute(select(ProtocolWhitelist).where(ProtocolWhitelist.id == whitelist_id))
    whitelist = result.scalar_one_or_none()
    if not whitelist:
        raise HTTPException(status_code=404, detail="Whitelist not found")
    updates = data.model_dump(exclude_unset=True, mode="json")
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
    return whitelist


@router.delete("/{whitelist_id}", status_code=204)
async def delete_whitelist(
    whitelist_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(["admin"])),
):
    result = await db.execute(select(ProtocolWhitelist).where(ProtocolWhitelist.id == whitelist_id))
    whitelist = result.scalar_one_or_none()
    if not whitelist:
        raise HTTPException(status_code=404, detail="Whitelist not found")
    await db.delete(whitelist)


@router.post("/{whitelist_id}/duplicate", response_model=WhitelistResponse)
async def duplicate_whitelist(
    whitelist_id: str,
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
    return clone
