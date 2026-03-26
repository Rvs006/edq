"""User management routes."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.models.database import get_db
from app.models.user import User
from app.schemas.user import UserResponse, UserUpdate
from app.security.auth import get_current_active_user, require_role
from app.utils.audit import log_security_event

router = APIRouter()


@router.get("/", response_model=List[UserResponse])
async def list_users(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(["admin", "reviewer"])),
):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
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
