"""Audit Log routes — compliance tracking."""

import csv
import io
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
from pydantic import BaseModel
from datetime import datetime, timedelta

from app.models.database import get_db
from app.models.audit_log import AuditLog
from app.models.user import User
from app.security.auth import require_role

router = APIRouter()


class AuditLogResponse(BaseModel):
    id: str
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    details: Optional[dict] = None
    ip_address: Optional[str] = None
    compliance_refs: Optional[list] = None
    created_at: datetime

    class Config:
        from_attributes = True


def _build_audit_query(
    action: Optional[str],
    resource_type: Optional[str],
    user_id: Optional[str],
    date_from: Optional[datetime],
    date_to: Optional[datetime],
):
    """Build a filtered query for audit logs."""
    query = select(AuditLog)
    if action:
        query = query.where(AuditLog.action == action)
    if resource_type:
        query = query.where(AuditLog.resource_type == resource_type)
    if user_id:
        query = query.where(AuditLog.user_id == user_id)
    if date_from:
        query = query.where(AuditLog.created_at >= date_from)
    if date_to:
        query = query.where(AuditLog.created_at < date_to + timedelta(days=1))
    return query


@router.get("/")
async def list_audit_logs(
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    user_id: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(["admin", "reviewer"])),
):
    query = _build_audit_query(action, resource_type, user_id, date_from, date_to)

    # Get total count for pagination
    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        query.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit)
    )
    logs = result.scalars().all()

    # Resolve user IDs to usernames
    user_ids = {log.user_id for log in logs if log.user_id}
    user_map: dict[str, str] = {}
    if user_ids:
        users_result = await db.execute(
            select(User.id, User.username).where(User.id.in_(user_ids))
        )
        user_map = {row[0]: row[1] for row in users_result.all()}

    return {
        "items": [
            {
                **AuditLogResponse.model_validate(log).model_dump(),
                "user_name": user_map.get(log.user_id) if log.user_id else None,
            }
            for log in logs
        ],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get("/export")
async def export_audit_logs(
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    user_id: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(["admin", "reviewer"])),
):
    """Export audit logs as CSV."""
    query = _build_audit_query(action, resource_type, user_id, date_from, date_to)
    result = await db.execute(query.order_by(AuditLog.created_at.desc()).limit(5000))
    logs = result.scalars().all()

    # Resolve usernames
    user_ids = {log.user_id for log in logs if log.user_id}
    user_map: dict[str, str] = {}
    if user_ids:
        users_result = await db.execute(
            select(User.id, User.username).where(User.id.in_(user_ids))
        )
        user_map = {row[0]: row[1] for row in users_result.all()}

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Timestamp", "User", "Action", "Resource Type", "Resource ID", "Details", "IP Address"])
    for log in logs:
        writer.writerow([
            log.created_at.isoformat() if log.created_at else "",
            user_map.get(log.user_id, log.user_id or "") if log.user_id else "",
            log.action,
            log.resource_type,
            log.resource_id or "",
            str(log.details) if log.details else "",
            log.ip_address or "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_logs.csv"},
    )


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
