"""User management routes."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from typing import List, Optional

from app.models.database import get_db
from app.models.refresh_token import RefreshToken
from app.models.user import User, UserRole
from app.schemas.user import UserResponse, UserUpdate
from app.security.auth import (
    get_current_active_user,
    require_role,
    revoke_user_access_tokens,
    revoke_user_refresh_tokens,
    hash_password,
)
from app.utils.audit import log_security_event
from app.utils.sanitize import sanitize_dict

logger = logging.getLogger("edq.routes.users")

router = APIRouter()


async def _find_casefold_user_conflict(
    db: AsyncSession,
    *,
    username: str | None = None,
    email: str | None = None,
    exclude_user_id: str | None = None,
) -> User | None:
    clauses = []
    if username:
        clauses.append(func.lower(User.username) == username.casefold())
    if email:
        clauses.append(func.lower(User.email) == email.casefold())
    if not clauses:
        return None
    query = select(User).where(*clauses[:1])
    if len(clauses) > 1:
        query = select(User).where(clauses[0] | clauses[1])
    if exclude_user_id:
        query = query.where(User.id != exclude_user_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


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


class AdminCreateUser(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: Optional[str] = Field(None, max_length=128)
    role: Optional[str] = "engineer"

    @field_validator("password")
    @classmethod
    def check_password_strength(cls, v: str) -> str:
        from app.schemas.auth import _validate_password_strength
        return _validate_password_strength(v)


@router.post("/", response_model=UserResponse, status_code=201)
async def admin_create_user(
    data: AdminCreateUser,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Admin-only endpoint to create a user (bypasses ALLOW_REGISTRATION)."""
    normalized_email = data.email.strip()
    if await _find_casefold_user_conflict(
        db,
        username=data.username.strip(),
        email=normalized_email,
    ):
        raise HTTPException(status_code=400, detail="Email or username already registered")

    try:
        role = UserRole(data.role) if data.role else UserRole.ENGINEER
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid role: {data.role}")

    clean = sanitize_dict(data.model_dump(), ["full_name", "username"])
    user = User(
        email=normalized_email,
        username=(clean["username"] or "").strip(),
        password_hash=hash_password(data.password),
        full_name=clean.get("full_name"),
        role=role,
    )
    db.add(user)
    try:
        await db.flush()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Email or username already registered")

    await log_security_event(
        db, "auth.admin_create_user", user_id=current_user.id,
        details={"new_user_id": user.id, "username": user.username, "role": role.value},
        request=request,
    )
    return user


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    # Engineers can only view their own profile; admins and reviewers can view any
    if current_user.role == UserRole.ENGINEER and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
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
    updates = sanitize_dict(updates, ["full_name", "email"])
    old_role = user.role.value if hasattr(user.role, "value") else str(user.role)
    if "full_name" in updates:
        user.full_name = updates["full_name"]
    if "email" in updates:
        normalized_email = updates["email"].strip()
        conflict = await _find_casefold_user_conflict(
            db,
            email=normalized_email,
            exclude_user_id=user_id,
        )
        if conflict:
            raise HTTPException(status_code=400, detail="Email already registered")
        user.email = normalized_email
    if "role" in updates:
        try:
            user.role = UserRole(updates["role"])
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid role: {updates['role']}. Must be one of: admin, reviewer, engineer",
            )
    if "is_active" in updates:
        user.is_active = updates["is_active"]
        # Revoke sessions when deactivating a user
        if not updates["is_active"]:
            revoke_user_access_tokens(user)
            await revoke_user_refresh_tokens(db, user_id)
    try:
        await db.flush()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Email already registered")

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
    """Force-logout a user by revoking refresh tokens and active access tokens."""
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

    revoke_user_access_tokens(user)
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
