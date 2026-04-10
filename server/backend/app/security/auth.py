"""JWT authentication via httpOnly cookies, CSRF protection, and role-based authorization."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from fastapi import Depends, HTTPException, Request, Response, status
import jwt
from jwt.exceptions import InvalidTokenError as JWTError
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
import secrets
import hashlib

from app.config import settings
from app.models.database import get_db
from app.models.user import User
from app.models.refresh_token import RefreshToken
from app.utils.datetime import ensure_utc_naive, utcnow

SESSION_COOKIE = "edq_session"
CSRF_COOKIE = "edq_csrf"
REFRESH_COOKIE = "edq_refresh"

def _utcnow() -> datetime:
    return utcnow()


def revoke_user_access_tokens(user: User, revoked_at: datetime | None = None) -> None:
    """Invalidate all access tokens issued for the user up to the given time."""
    when = revoked_at or _utcnow()
    if when.tzinfo is not None:
        when = when.astimezone(timezone.utc).replace(tzinfo=None)
    user.access_tokens_revoked_at = when


def _payload_iat_to_utc(payload: dict) -> datetime | None:
    issued_at_us = payload.get("iat_us")
    if isinstance(issued_at_us, (int, float)):
        return datetime.fromtimestamp(float(issued_at_us) / 1_000_000, tz=timezone.utc)
    issued_at = payload.get("iat")
    if issued_at is None:
        return None
    if isinstance(issued_at, datetime):
        if issued_at.tzinfo is None:
            return issued_at.replace(tzinfo=timezone.utc)
        return issued_at.astimezone(timezone.utc)
    if isinstance(issued_at, (int, float)):
        return datetime.fromtimestamp(float(issued_at), tz=timezone.utc)
    return None


def is_access_token_revoked_for_user(user: User, payload: dict) -> bool:
    """Check whether an access token payload predates user-level revocation."""
    if not user.access_tokens_revoked_at:
        return False
    issued_at = _payload_iat_to_utc(payload)
    if issued_at is None:
        return True
    revoked_at = user.access_tokens_revoked_at
    if revoked_at.tzinfo is None:
        revoked_at = revoked_at.replace(tzinfo=timezone.utc)
    else:
        revoked_at = revoked_at.astimezone(timezone.utc)
    return issued_at <= revoked_at

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def generate_api_key() -> str:
    return secrets.token_hex(settings.AGENT_API_KEY_LENGTH // 2)


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


def generate_csrf_token() -> str:
    return secrets.token_hex(32)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    issued_at = _utcnow()
    expire = issued_at + (expires_delta or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({
        "exp": expire,
        "iat": issued_at,
        "iat_us": int(issued_at.timestamp() * 1_000_000),
        "type": "access",
        "jti": uuid.uuid4().hex,
    })
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = _utcnow() + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh", "jti": secrets.token_hex(16)})
    return jwt.encode(to_encode, settings.JWT_REFRESH_SECRET, algorithm=settings.JWT_ALGORITHM)


def hash_token(token: str) -> str:
    """SHA-256 hash of a refresh token for DB storage."""
    return hashlib.sha256(token.encode()).hexdigest()


async def store_refresh_token(db: AsyncSession, user_id: str, token: str, expires_at: datetime) -> None:
    """Persist a hashed refresh token in the database."""
    db.add(RefreshToken(
        token_hash=hash_token(token),
        user_id=user_id,
        expires_at=ensure_utc_naive(expires_at),
    ))
    await db.flush()


async def validate_and_rotate_refresh_token(db: AsyncSession, token: str) -> str:
    """Validate a refresh token is in the DB and not revoked, then revoke it.

    Returns the user_id. Raises 401 if the token is revoked, missing, or expired.
    """
    t_hash = hash_token(token)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == t_hash)
    )
    db_token = result.scalar_one_or_none()

    if not db_token or db_token.revoked:
        # Possible token reuse attack — revoke entire family for this user
        if db_token and db_token.revoked:
            await db.execute(
                update(RefreshToken)
                .where(RefreshToken.user_id == db_token.user_id, RefreshToken.revoked == False)
                .values(revoked=True)
            )
            # Commit the family revocation immediately so it survives the
            # upcoming HTTPException (which triggers a rollback in the
            # dependency cleanup).
            await db.commit()
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if db_token.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        db_token.revoked = True
        await db.commit()
        raise HTTPException(status_code=401, detail="Refresh token expired")

    # Revoke the used token (single-use)
    db_token.revoked = True
    await db.flush()
    return db_token.user_id


async def revoke_user_refresh_tokens(db: AsyncSession, user_id: str) -> None:
    """Revoke all active refresh tokens for a user (logout, password change)."""
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked == False)
        .values(revoked=True)
    )
    await db.flush()


def verify_token(token: str, token_type: str = "access") -> dict:
    secret = settings.JWT_REFRESH_SECRET if token_type == "refresh" else settings.JWT_SECRET
    try:
        payload = jwt.decode(token, secret, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("type") != token_type:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
        return payload
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")


def set_auth_cookies(
    response: Response,
    access_token: str,
    csrf_token: str,
    refresh_token: str | None = None,
) -> None:
    samesite = settings.COOKIE_SAMESITE
    response.set_cookie(
        key=SESSION_COOKIE,
        value=access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=samesite,
        max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    if refresh_token:
        response.set_cookie(
            key=REFRESH_COOKIE,
            value=refresh_token,
            httponly=True,
            secure=settings.COOKIE_SECURE,
            samesite=samesite,
            max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
            path="/api",
        )
    response.set_cookie(
        key=CSRF_COOKIE,
        value=csrf_token,
        httponly=False,
        secure=settings.COOKIE_SECURE,
        samesite=samesite,
        max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE, path="/")
    response.delete_cookie(key=CSRF_COOKIE, path="/")
    response.delete_cookie(key=REFRESH_COOKIE, path="/api")
    response.delete_cookie(key=REFRESH_COOKIE, path="/")


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        return None
    payload = verify_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if payload.get("type") == "access" and is_access_token_revoked_for_user(user, payload):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been revoked")
    return user


async def get_current_active_user(
    user: User = Depends(get_current_user),
) -> User:
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated")
    return user


def require_role(allowed_roles: List[str]):
    async def role_checker(user: User = Depends(get_current_active_user)) -> User:
        if user.role.value not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role.value}' does not have access. Required: {allowed_roles}",
            )
        return user
    return role_checker
