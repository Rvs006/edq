"""User management routes."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List

from app.models.database import get_db
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.user import UserResponse, UserUpdate
from app.security.auth import get_current_active_user, require_role, revoke_user_refresh_tokens
from app.utils.audit import log_security_event

logger = logging.getLogger("edq.routes.users")

router = APIRouter()


@router.get("/", response_model=List[UserResponse])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(["admin"])),
):
    result = await db.execute(
        select(User).order_by(User.created_at.desc()).offset(skip).limit(limit)
    )
    return result.scalars().all()


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    data: UserUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    updates = data.model_dump(exclude_unset=True)
    old_role = user.role.value if hasattr(user.role, "value") else str(user.role)
    if "full_name" in updates:
        user.full_name = updates["full_name"]
    if "email" in updates:
        user.email = updates["email"]
    if "role" in updates:
        user.role = updates["role"]
    if "is_active" in updates:
        user.is_active = updates["is_active"]
    await db.flush()
    await db.refresh(user)

    # Audit role changes and account deactivations
    new_role = user.role.value if hasattr(user.role, "value") else str(user.role)
    if "role" in updates and old_role != new_role:
        await log_security_event(
            db, "auth.role_change", user_id=current_user.id,
            details={"target_user": user_id, "old_role": old_role, "new_role": new_role},
            request=request,
        )
    if "is_active" in updates:
        await log_security_event(
            db, "auth.account_status_change", user_id=current_user.id,
            details={"target_user": user_id, "is_active": user.is_active},
            request=request,
        )

    return user


@router.post("/{user_id}/revoke-sessions")
async def revoke_user_sessions(
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Force-logout a user by revoking all their refresh tokens.

    Existing access tokens remain valid until they expire (up to 60 minutes).
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Count active tokens before revoking
    count_result = await db.execute(
        select(func.count()).select_from(RefreshToken).where(
            RefreshToken.user_id == user_id, RefreshToken.revoked == False
        )
    )
    active_count = count_result.scalar()

    await revoke_user_refresh_tokens(db, user_id)

    await log_security_event(
        db, "auth.sessions_revoked", user_id=current_user.id,
        details={"target_user": user_id, "tokens_revoked": active_count},
        request=request,
    )
    logger.info("Admin %s revoked %d sessions for user %s", current_user.id, active_count, user_id)

    return {
        "message": f"Revoked {active_count} active session(s) for user {user.username}",
        "tokens_revoked": active_count,
    }
