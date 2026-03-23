"""JWT authentication via httpOnly cookies, CSRF protection, and role-based authorization."""

from datetime import datetime, timedelta, timezone
from typing import Optional, List
from fastapi import Depends, HTTPException, Request, Response, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import secrets
import hashlib

from app.config import settings
from app.models.database import get_db
from app.models.user import User

SESSION_COOKIE = "edq_session"
CSRF_COOKIE = "edq_csrf"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


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
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.JWT_REFRESH_SECRET, algorithm=settings.JWT_ALGORITHM)


def verify_token(token: str, token_type: str = "access") -> dict:
    secret = settings.JWT_REFRESH_SECRET if token_type == "refresh" else settings.JWT_SECRET
    try:
        payload = jwt.decode(token, secret, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("type") != token_type:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
        return payload
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")


def set_auth_cookies(response: Response, access_token: str, csrf_token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    response.set_cookie(
        key=CSRF_COOKIE,
        value=csrf_token,
        httponly=False,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE, path="/")
    response.delete_cookie(key=CSRF_COOKIE, path="/")


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
