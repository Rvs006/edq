"""Protocol observer settings routes."""

from __future__ import annotations

import ipaddress
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from app.models.protocol_observer_settings import ProtocolObserverSettings
from app.models.user import User
from app.security.auth import get_current_active_user, require_role
from app.services.protocol_observer import (
    apply_protocol_observer_settings,
    current_protocol_observer_settings,
)
from app.utils.audit import log_action

router = APIRouter()


class ProtocolObserverSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    enabled: bool = True
    bind_host: str = "0.0.0.0"
    timeout_seconds: int = 20
    dns_port: int = 53
    ntp_port: int = 123
    dhcp_port: int = 67
    dhcp_offer_ip: str = ""
    dhcp_subnet_mask: str = ""
    dhcp_router_ip: str = ""
    dhcp_dns_server: str = ""
    dhcp_lease_seconds: int = 300


class ProtocolObserverSettingsUpdate(BaseModel):
    enabled: Optional[bool] = None
    bind_host: Optional[str] = Field(None, max_length=64)
    timeout_seconds: Optional[int] = Field(None, ge=1, le=300)
    dns_port: Optional[int] = Field(None, ge=1, le=65535)
    ntp_port: Optional[int] = Field(None, ge=1, le=65535)
    dhcp_port: Optional[int] = Field(None, ge=1, le=65535)
    dhcp_offer_ip: Optional[str] = Field(None, max_length=64)
    dhcp_subnet_mask: Optional[str] = Field(None, max_length=64)
    dhcp_router_ip: Optional[str] = Field(None, max_length=64)
    dhcp_dns_server: Optional[str] = Field(None, max_length=64)
    dhcp_lease_seconds: Optional[int] = Field(None, ge=60, le=86400)

    @field_validator(
        "dhcp_offer_ip",
        "dhcp_subnet_mask",
        "dhcp_router_ip",
        "dhcp_dns_server",
        mode="before",
    )
    @classmethod
    def normalize_ip_like_values(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = str(value).strip()
        if stripped == "":
            return stripped
        try:
            ipaddress.IPv4Address(stripped)
        except (ipaddress.AddressValueError, ValueError) as exc:
            raise ValueError(f"Invalid IPv4 address: {stripped}") from exc
        return stripped


async def _get_or_create_settings(db: AsyncSession) -> ProtocolObserverSettings:
    """Get or create the singleton ProtocolObserverSettings row.

    Uses dialect-specific insert().on_conflict_do_nothing() to safely handle concurrent
    requests without race-condition duplicate rows. Falls back to IntegrityError handling
    for unsupported dialects.
    """
    dialect_name = db.bind.dialect.name if db.bind is not None else ""
    if dialect_name == "postgresql":
        insert_fn = pg_insert
    elif dialect_name == "sqlite":
        insert_fn = sqlite_insert
    else:
        insert_fn = None

    try:
        if insert_fn is not None:
            stmt = insert_fn(ProtocolObserverSettings).values(
                singleton_key="_",
                **current_protocol_observer_settings(),
            ).on_conflict_do_nothing()
            await db.execute(stmt)
            await db.flush()
    except IntegrityError:
        # Another request inserted simultaneously; roll back and proceed to SELECT
        await db.rollback()
    
    # Query the (now-existing) singleton row
    result = await db.execute(select(ProtocolObserverSettings).limit(1))
    item = result.scalar_one_or_none()
    if item:
        return item
    
    # Fallback: if still not found, create directly (should not happen under normal operation)
    item = ProtocolObserverSettings(singleton_key="_", **current_protocol_observer_settings())
    db.add(item)
    await db.flush()
    await db.refresh(item)
    return item


@router.get("/protocol-observer", response_model=ProtocolObserverSettingsResponse)
async def get_protocol_observer_settings(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    item = await _get_or_create_settings(db)
    return item


@router.put("/protocol-observer", response_model=ProtocolObserverSettingsResponse)
async def update_protocol_observer_settings(
    data: ProtocolObserverSettingsUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["admin"])),
):
    item = await _get_or_create_settings(db)
    updates = data.model_dump(exclude_unset=True)

    for field, value in updates.items():
        setattr(item, field, value)

    apply_protocol_observer_settings(updates)
    await db.flush()
    await db.refresh(item)
    await log_action(
        db,
        user,
        "protocol_observer_settings.update",
        "protocol_observer_settings",
        item.id,
        updates,
        request,
    )
    return item
