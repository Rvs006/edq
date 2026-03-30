"""OIDC / OAuth2 authentication — supports Google, Microsoft, and generic OIDC providers.

Configuration via environment variables:
  OIDC_PROVIDER=google|microsoft|custom
  OIDC_CLIENT_ID=...
  OIDC_CLIENT_SECRET=...
  OIDC_DISCOVERY_URL=... (auto-set for google/microsoft, required for custom)
  OIDC_ALLOWED_DOMAINS=electracom.com,example.com (optional — restrict by email domain)
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.database import get_db
from app.models.user import User, UserRole
from app.security.auth import (
    create_access_token,
    create_refresh_token,
    generate_csrf_token,
    set_auth_cookies,
    store_refresh_token,
)
from app.utils.audit import log_security_event

logger = logging.getLogger("edq.routes.oidc")

router = APIRouter()

# Well-known discovery URLs for common providers
_DISCOVERY_URLS = {
    "google": "https://accounts.google.com/.well-known/openid-configuration",
    "microsoft": "https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration",
}


class OIDCTokenRequest(BaseModel):
    """Frontend sends the authorization code after the OIDC redirect."""
    code: str = Field(..., min_length=1)
    redirect_uri: str = Field(..., min_length=1)
    provider: str = Field(..., min_length=1, max_length=64)


class OIDCConfigResponse(BaseModel):
    enabled: bool
    provider: Optional[str] = None
    client_id: Optional[str] = None
    authorization_endpoint: Optional[str] = None
    scopes: str = "openid email profile"


async def _get_oidc_discovery(provider: str) -> dict:
    """Fetch and cache the OIDC discovery document."""
    import httpx

    disc_url = _DISCOVERY_URLS.get(provider, settings.OIDC_DISCOVERY_URL)
    if not disc_url:
        raise HTTPException(status_code=500, detail="OIDC discovery URL not configured")

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(disc_url)
        resp.raise_for_status()
        return resp.json()


async def _exchange_code_for_tokens(
    code: str, redirect_uri: str, token_endpoint: str
) -> dict:
    """Exchange an authorization code for tokens at the IdP."""
    import httpx

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": settings.OIDC_CLIENT_ID,
                "client_secret": settings.OIDC_CLIENT_SECRET,
            },
        )
        if resp.status_code != 200:
            logger.warning("OIDC token exchange failed: %s %s", resp.status_code, resp.text[:200])
            raise HTTPException(status_code=401, detail="OIDC authentication failed")
        return resp.json()


def _decode_id_token(id_token: str) -> dict:
    """Decode an OIDC id_token (signature already verified by IdP during code exchange)."""
    from jose import jwt as jose_jwt
    # We trust the token because we just received it directly from the IdP
    # via a server-to-server HTTPS call. Skip signature verification.
    return jose_jwt.get_unverified_claims(id_token)


@router.get("/config", response_model=OIDCConfigResponse)
async def oidc_config():
    """Return OIDC config for the frontend login page."""
    if not settings.OIDC_CLIENT_ID or not settings.OIDC_PROVIDER:
        return OIDCConfigResponse(enabled=False)

    try:
        discovery = await _get_oidc_discovery(settings.OIDC_PROVIDER)
    except Exception:
        return OIDCConfigResponse(enabled=False)

    return OIDCConfigResponse(
        enabled=True,
        provider=settings.OIDC_PROVIDER,
        client_id=settings.OIDC_CLIENT_ID,
        authorization_endpoint=discovery.get("authorization_endpoint"),
    )


@router.post("/callback")
async def oidc_callback(
    data: OIDCTokenRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Exchange OIDC code for tokens, create/link user, and issue EDQ session."""
    if not settings.OIDC_CLIENT_ID:
        raise HTTPException(status_code=400, detail="OIDC is not configured")

    # Get IdP endpoints
    discovery = await _get_oidc_discovery(data.provider)
    token_endpoint = discovery["token_endpoint"]

    # Exchange authorization code
    tokens = await _exchange_code_for_tokens(data.code, data.redirect_uri, token_endpoint)
    id_token = tokens.get("id_token")
    if not id_token:
        raise HTTPException(status_code=401, detail="No id_token in OIDC response")

    # Decode claims
    claims = _decode_id_token(id_token)
    email = claims.get("email")
    sub = claims.get("sub")
    name = claims.get("name")

    if not email or not sub:
        raise HTTPException(status_code=401, detail="OIDC response missing email or subject")

    # Domain restriction
    if settings.OIDC_ALLOWED_DOMAINS:
        allowed = [d.strip().lower() for d in settings.OIDC_ALLOWED_DOMAINS.split(",")]
        domain = email.split("@")[1].lower()
        if domain not in allowed:
            raise HTTPException(status_code=403, detail=f"Email domain '{domain}' is not allowed")

    # Find existing user by OIDC subject or email
    result = await db.execute(
        select(User).where(
            or_(
                (User.oidc_subject == sub) & (User.oidc_provider == data.provider),
                User.email == email,
            )
        )
    )
    user = result.scalar_one_or_none()

    if user:
        # Link OIDC if not already linked
        if not user.oidc_subject:
            user.oidc_provider = data.provider
            user.oidc_subject = sub
            user.oidc_email = email
        if name and not user.full_name:
            user.full_name = name
        user.last_login = datetime.now(timezone.utc)
    else:
        # Auto-provision new user with engineer role
        username = email.split("@")[0][:64]
        # Ensure unique username
        existing_username = await db.execute(select(User).where(User.username == username))
        if existing_username.scalar_one_or_none():
            import uuid
            username = f"{username}_{uuid.uuid4().hex[:4]}"

        user = User(
            email=email,
            username=username,
            password_hash="OIDC_NO_PASSWORD",  # Can't login with password
            full_name=name,
            role=UserRole.ENGINEER,
            oidc_provider=data.provider,
            oidc_subject=sub,
            oidc_email=email,
            last_login=datetime.now(timezone.utc),
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)
        logger.info("Auto-provisioned OIDC user: %s (%s via %s)", username, email, data.provider)

    # Issue EDQ session tokens
    access_token = create_access_token({"sub": user.id, "role": user.role.value})
    refresh_token = create_refresh_token({"sub": user.id})
    csrf_token = generate_csrf_token()

    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    await store_refresh_token(db, user.id, refresh_token, expires_at)

    set_auth_cookies(response, access_token, csrf_token)
    await log_security_event(
        db, "auth.oidc_login", user_id=user.id,
        details={"provider": data.provider, "email": email}, request=request,
    )

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
