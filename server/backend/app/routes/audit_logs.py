"""Audit Log routes — compliance tracking."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from app.models.database import get_db
from app.models.audit_log import AuditLog
from app.models.user import User
from app.security.auth import get_current_active_user, require_role

router = APIRouter()


class AuditLogResponse(BaseModel):
    id: str
    user_id: Optional[str] = None
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    details: Optional[dict] = None
    ip_address: Optional[str] = None
    compliance_refs: Optional[list] = None
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("/", response_model=List[AuditLogResponse])
async def list_audit_logs(
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    user_id: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(["admin", "reviewer"])),
):
    query = select(AuditLog)
    if action:
        query = query.where(AuditLog.action == action)
    if resource_type:
        query = query.where(AuditLog.resource_type == resource_type)
    if user_id:
        query = query.where(AuditLog.user_id == user_id)
    result = await db.execute(query.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit))
    return result.scalars().all()


@router.get("/compliance-summary")
async def compliance_summary(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(["admin", "reviewer"])),
):
    """Get compliance framework coverage summary."""
    return {
        "frameworks": {
            "ISO 27001": {
                "description": "Information Security Management",
                "controls_mapped": 15,
                "tests_covered": ["U01", "U02", "U04", "U05", "U06", "U09", "U10", "U11", "U12", "U13", "U14", "U15", "U16", "U17", "U18", "U19", "U20", "U21", "U22", "U23", "U24", "U25", "U26", "U27", "U28", "U29", "U30"],
            },
            "Cyber Essentials": {
                "description": "UK Government Cyber Security Standard",
                "controls_mapped": 6,
                "tests_covered": ["U06", "U09", "U10", "U15", "U16", "U17", "U21", "U27", "U30"],
            },
            "SOC2": {
                "description": "Service Organization Control 2",
                "controls_mapped": 4,
                "tests_covered": ["U06", "U09", "U10", "U16", "U21", "U30"],
            },
        }
    }
