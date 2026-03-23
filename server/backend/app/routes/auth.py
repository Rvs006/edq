"""Authentication routes — login, register, refresh, change password (httpOnly cookies)."""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.middleware.rate_limit import check_rate_limit
from app.models.database import get_db
from app.models.user import User, UserRole
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
)
from app.schemas.user import UserResponse
from app.security.auth import (
    clear_auth_cookies,
    create_access_token,
    create_refresh_token,
    generate_csrf_token,
    hash_password,
    set_auth_cookies,
    verify_password,
    verify_token,
    get_current_active_user,
)

logger = logging.getLogger("edq.routes.auth")

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(data: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    check_rate_limit(request, max_requests=3, window_seconds=60)

    result = await db.execute(select(User).where((User.email == data.email) | (User.username == data.username)))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email or username already registered")

    user = User(
        email=data.email,
        username=data.username,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        role=UserRole(data.role) if data.role in [r.value for r in UserRole] else UserRole.ENGINEER,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@router.post("/login")
async def login(data: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    check_rate_limit(request, max_requests=settings.LOGIN_RATE_LIMIT_PER_MINUTE, window_seconds=60)

    result = await db.execute(select(User).where(User.username == data.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.password_hash):
        # Track failed attempts for account lockout
        if user:
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= settings.ACCOUNT_LOCKOUT_ATTEMPTS:
                user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCOUNT_LOCKOUT_MINUTES)
                logger.warning("Account locked for user %s after %d failed attempts", data.username, user.failed_login_attempts)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    # Check account lockout
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        remaining = int((user.locked_until - datetime.now(timezone.utc)).total_seconds() / 60) + 1
        raise HTTPException(
            status_code=403,
            detail=f"Account is temporarily locked. Try again in {remaining} minute(s).",
        )

    # Reset failed attempts on successful login
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login = datetime.now(timezone.utc)

    access_token = create_access_token({"sub": user.id, "role": user.role.value})
    refresh_token = create_refresh_token({"sub": user.id})
    csrf_token = generate_csrf_token()

    set_auth_cookies(response, access_token, csrf_token)

    return {
        "message": "Login successful",
        "csrf_token": csrf_token,
        "refresh_token": refresh_token,
        "expires_in": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role.value,
        },
    }


@router.post("/logout")
async def logout(response: Response):
    clear_auth_cookies(response)
    return {"message": "Logged out successfully"}


@router.post("/refresh")
async def refresh(data: RefreshRequest, response: Response, db: AsyncSession = Depends(get_db)):
    payload = verify_token(data.refresh_token, token_type="refresh")
    user_id = payload.get("sub")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    access_token = create_access_token({"sub": user.id, "role": user.role.value})
    refresh_token = create_refresh_token({"sub": user.id})
    csrf_token = generate_csrf_token()

    set_auth_cookies(response, access_token, csrf_token)

    return {
        "message": "Token refreshed",
        "csrf_token": csrf_token,
        "refresh_token": refresh_token,
        "expires_in": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_active_user)):
    return user


@router.post("/change-password")
async def change_password(
    data: ChangePasswordRequest,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.password_hash = hash_password(data.new_password)
    return {"message": "Password changed successfully"}
