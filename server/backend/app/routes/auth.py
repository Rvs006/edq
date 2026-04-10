"""Authentication routes — login, register, refresh, change password (httpOnly cookies)."""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
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
    REFRESH_COOKIE,
    clear_auth_cookies,
    create_access_token,
    create_refresh_token,
    generate_csrf_token,
    hash_password,
    revoke_user_access_tokens,
    set_auth_cookies,
    store_refresh_token,
    validate_and_rotate_refresh_token,
    revoke_user_refresh_tokens,
    verify_password,
    verify_token,
    get_current_active_user,
)

from app.utils.audit import log_security_event
from app.utils.sanitize import sanitize_dict

logger = logging.getLogger("edq.routes.auth")


def _utcnow() -> datetime:
    """Return current UTC time as a naive datetime (matches SQLite storage)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(data: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    if not settings.ALLOW_REGISTRATION:
        raise HTTPException(status_code=403, detail="Public registration is disabled")
    check_rate_limit(request, max_requests=3, window_seconds=60, action="register")

    clean = sanitize_dict(data.model_dump(), ["full_name", "username"])
    username = (clean["username"] or "").strip()
    if len(username) < 3:
        raise HTTPException(status_code=422, detail="Username must be at least 3 characters")

    email = data.email.strip()
    normalized_username = username.casefold()
    normalized_email = email.casefold()

    result = await db.execute(
        select(User).where(
            (func.lower(User.email) == normalized_email)
            | (func.lower(User.username) == normalized_username)
        )
    )
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Email or username already registered")

    user = User(
        email=email,
        username=username,
        password_hash=hash_password(data.password),
        full_name=clean.get("full_name"),
        role=UserRole.ENGINEER,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    await log_security_event(db, "auth.register", user_id=user.id,
                             details={"username": user.username}, request=request)
    return user


@router.post("/login")
async def login(data: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    check_rate_limit(request, max_requests=settings.LOGIN_RATE_LIMIT_PER_MINUTE, window_seconds=60, action="login")

    identity = data.username.strip()
    normalized_identity = identity.casefold()
    result = await db.execute(
        select(User).where(
            (func.lower(User.username) == normalized_identity)
            | (func.lower(User.email) == normalized_identity)
        )
    )
    matches = result.scalars().all()
    if len(matches) > 1:
        logger.warning("Ambiguous login identity for %s due to duplicate normalized credentials", identity)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user = matches[0] if matches else None

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Check account lockout — return 401 (not 403) to avoid leaking whether the account exists
    if user.locked_until and user.locked_until > _utcnow():
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
        )

    # Reset failed attempts after lockout period expires, giving a fresh window
    if user.locked_until and user.locked_until <= _utcnow():
        user.failed_login_attempts = 0
        user.locked_until = None

    if not verify_password(data.password, user.password_hash):
        # Track failed attempts for account lockout and commit before raising
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        if user.failed_login_attempts >= settings.ACCOUNT_LOCKOUT_ATTEMPTS:
            user.locked_until = _utcnow() + timedelta(minutes=settings.ACCOUNT_LOCKOUT_MINUTES)
            logger.warning("Account locked for user %s after %d failed attempts", identity, user.failed_login_attempts)
        await log_security_event(db, "auth.login_failed", user_id=user.id,
                                 details={"username": identity}, request=request)
        await db.commit()
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    # Enforce 2FA if enabled on the account
    if user.totp_secret:
        if not data.totp_code:
            # Signal the frontend that 2FA is required
            return {"requires_2fa": True, "detail": "Additional verification required"}
        from app.routes.two_factor import verify_totp_for_user
        if not verify_totp_for_user(user, data.totp_code):
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            await log_security_event(db, "auth.2fa_failed", user_id=user.id,
                                     details={"username": identity}, request=request)
            await db.commit()
            raise HTTPException(status_code=401, detail="Invalid two-factor authentication code")

    # Reset failed attempts on successful login
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login = _utcnow()

    access_token = create_access_token({"sub": user.id, "role": user.role.value})
    refresh_token = create_refresh_token({"sub": user.id})
    csrf_token = generate_csrf_token()

    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    await store_refresh_token(db, user.id, refresh_token, expires_at)

    set_auth_cookies(response, access_token, csrf_token, refresh_token)
    await log_security_event(db, "auth.login", user_id=user.id,
                             details={"username": user.username}, request=request)

    return {
        "message": "Login successful",
        "csrf_token": csrf_token,
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
async def logout(
    request: Request,
    response: Response,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    revoke_user_access_tokens(user)
    await revoke_user_refresh_tokens(db, user.id)
    await log_security_event(db, "auth.logout", user_id=user.id, request=request)
    clear_auth_cookies(response)
    return {"message": "Logged out successfully"}


@router.post("/refresh")
async def refresh(
    request: Request,
    response: Response,
    data: RefreshRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    check_rate_limit(request, max_requests=settings.LOGIN_RATE_LIMIT_PER_MINUTE, window_seconds=60, action="refresh")
    refresh_token_input = (
        data.refresh_token if data and data.refresh_token else request.cookies.get(REFRESH_COOKIE)
    )
    if not refresh_token_input:
        raise HTTPException(status_code=401, detail="Refresh token missing")

    # Verify JWT signature/expiry first
    verify_token(refresh_token_input, token_type="refresh")

    # Validate against DB — revokes the old token (single-use rotation)
    user_id = await validate_and_rotate_refresh_token(db, refresh_token_input)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        await db.commit()
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    access_token = create_access_token({"sub": user.id, "role": user.role.value})
    refresh_token = create_refresh_token({"sub": user.id})
    csrf_token = generate_csrf_token()

    # Store the new refresh token
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    await store_refresh_token(db, user.id, refresh_token, expires_at)

    set_auth_cookies(response, access_token, csrf_token, refresh_token)
    await log_security_event(db, "auth.token_refresh", user_id=user.id, request=request)

    return {
        "message": "Token refreshed",
        "csrf_token": csrf_token,
        "expires_in": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_active_user)):
    return user


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(None, max_length=128)
    email: EmailStr | None = None


@router.patch("/me", response_model=UserResponse)
async def update_profile(
    data: ProfileUpdate,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    updates = data.model_dump(exclude_unset=True)
    updates = sanitize_dict(updates, ["full_name"])
    if "full_name" in updates:
        user.full_name = updates["full_name"]
    if "email" in updates:
        # Check email uniqueness
        normalized_email = updates["email"].strip()
        if normalized_email.casefold() != user.email.casefold():
            existing = await db.execute(
                select(User).where(
                    func.lower(User.email) == normalized_email.casefold(),
                    User.id != user.id,
                )
            )
            if existing.scalars().first():
                raise HTTPException(status_code=400, detail="Email already in use")
        user.email = normalized_email
    await db.flush()
    await db.refresh(user)
    return user


@router.post("/change-password")
async def change_password(
    data: ChangePasswordRequest,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    check_rate_limit(request, max_requests=3, window_seconds=60, action="change_password")

    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.password_hash = hash_password(data.new_password)

    revoke_user_access_tokens(user)
    await revoke_user_refresh_tokens(db, user.id)
    await log_security_event(db, "auth.password_change", user_id=user.id, request=request)
    return {"message": "Password changed successfully"}
