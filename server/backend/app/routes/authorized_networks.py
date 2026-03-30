"""Authorized Networks routes — admin-managed scan scope."""

import ipaddress
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.authorized_network import AuthorizedNetwork
from app.models.database import get_db
from app.models.user import User
from app.security.auth import get_current_active_user, require_role
from app.utils.audit import log_action

logger = logging.getLogger("edq.routes.authorized_networks")

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class NetworkCreate(BaseModel):
    cidr: str = Field(..., max_length=43)
    label: Optional[str] = Field(None, max_length=128)
    description: Optional[str] = None

    @field_validator("cidr")
    @classmethod
    def validate_cidr(cls, v: str) -> str:
        try:
            net = ipaddress.ip_network(v, strict=False)
        except ValueError:
            raise ValueError(f"Invalid CIDR notation: {v}")
        prefix = net.prefixlen
        if prefix < 8 or prefix > 30:
            raise ValueError("Prefix must be between /8 and /30")
        return str(net)


class NetworkUpdate(BaseModel):
    label: Optional[str] = Field(None, max_length=128)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class NetworkResponse(BaseModel):
    id: str
    cidr: str
    label: Optional[str] = None
    description: Optional[str] = None
    is_active: bool
    created_by: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Helper: check if an IP or CIDR is within any authorized network
# ---------------------------------------------------------------------------

async def get_active_networks(db: AsyncSession) -> List[AuthorizedNetwork]:
    result = await db.execute(
        select(AuthorizedNetwork).where(AuthorizedNetwork.is_active == True)
    )
    return list(result.scalars().all())


def is_target_authorized(target_cidr: str, authorized: List[AuthorizedNetwork]) -> bool:
    """Return True if the target CIDR falls entirely within at least one authorized network."""
    if not authorized:
        return False
    try:
        target_net = ipaddress.ip_network(target_cidr, strict=False)
    except ValueError:
        return False
    for auth_net in authorized:
        try:
            allowed = ipaddress.ip_network(auth_net.cidr, strict=False)
            if target_net.subnet_of(allowed):
                return True
        except ValueError:
            continue
    return False


def is_ip_authorized(ip_str: str, authorized: List[AuthorizedNetwork]) -> bool:
    """Return True if a single IP falls within at least one authorized network."""
    if not authorized:
        return False
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    for auth_net in authorized:
        try:
            allowed = ipaddress.ip_network(auth_net.cidr, strict=False)
            if addr in allowed:
                return True
        except ValueError:
            continue
    return False


# ---------------------------------------------------------------------------
# CRUD endpoints — admin only
# ---------------------------------------------------------------------------

@router.get("/", response_model=List[NetworkResponse])
async def list_authorized_networks(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    active_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    q = select(AuthorizedNetwork).order_by(AuthorizedNetwork.created_at.desc())
    if active_only:
        q = q.where(AuthorizedNetwork.is_active == True)
    q = q.offset(skip).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/", response_model=NetworkResponse, status_code=201)
async def create_authorized_network(
    data: NetworkCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["admin"])),
):
    existing = await db.execute(
        select(AuthorizedNetwork).where(AuthorizedNetwork.cidr == data.cidr)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Network {data.cidr} is already authorized")

    network = AuthorizedNetwork(
        cidr=data.cidr,
        label=data.label,
        description=data.description,
        created_by=user.id,
    )
    db.add(network)
    await db.flush()
    await db.refresh(network)

    await log_action(db, user, "authorized_network.create", "authorized_network", network.id,
                     {"cidr": data.cidr, "label": data.label}, request)

    return network


@router.get("/{network_id}", response_model=NetworkResponse)
async def get_authorized_network(
    network_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(AuthorizedNetwork).where(AuthorizedNetwork.id == network_id)
    )
    network = result.scalar_one_or_none()
    if not network:
        raise HTTPException(status_code=404, detail="Authorized network not found")
    return network


@router.patch("/{network_id}", response_model=NetworkResponse)
async def update_authorized_network(
    network_id: str,
    data: NetworkUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["admin"])),
):
    result = await db.execute(
        select(AuthorizedNetwork).where(AuthorizedNetwork.id == network_id)
    )
    network = result.scalar_one_or_none()
    if not network:
        raise HTTPException(status_code=404, detail="Authorized network not found")

    updates = data.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(network, key, value)
    network.updated_at = datetime.now(timezone.utc)

    await db.flush()
    await db.refresh(network)

    await log_action(db, user, "authorized_network.update", "authorized_network", network.id,
                     updates, request)

    return network


@router.delete("/{network_id}", status_code=204)
async def delete_authorized_network(
    network_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["admin"])),
):
    result = await db.execute(
        select(AuthorizedNetwork).where(AuthorizedNetwork.id == network_id)
    )
    network = result.scalar_one_or_none()
    if not network:
        raise HTTPException(status_code=404, detail="Authorized network not found")

    await log_action(db, user, "authorized_network.delete", "authorized_network", network.id,
                     {"cidr": network.cidr}, request)

    await db.delete(network)
    await db.flush()
