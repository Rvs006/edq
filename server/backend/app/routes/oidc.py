"""OIDC / OAuth2 authentication with verified ID token handling."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
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
from app.utils.datetime import utcnow_naive
from app.utils.audit import log_security_event

logger = logging.getLogger("edq.routes.oidc")

router = APIRouter()

_DISCOVERY_URLS = {
    "google": "https://accounts.google.com/.well-known/openid-configuration",
    "microsoft": "https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration",
}


class OIDCTokenRequest(BaseModel):
    """Frontend sends the authorization code after the OIDC redirect."""

    code: str = Field(..., min_length=1)
    redirect_uri: str = Field(..., min_length=1)
    nonce: str = Field(..., min_length=8, max_length=255)
    provider: Optional[str] = Field(None, min_length=1, max_length=64)
    code_verifier: Optional[str] = Field(None, min_length=43, max_length=255)


class OIDCConfigResponse(BaseModel):
    enabled: bool
    provider: Optional[str] = None
    client_id: Optional[str] = None
    authorization_endpoint: Optional[str] = None
    scopes: str = "openid email profile"


def _resolve_provider(requested_provider: Optional[str]) -> str:
    configured_provider = settings.OIDC_PROVIDER.strip()
    if configured_provider:
        if requested_provider and requested_provider != configured_provider:
            raise HTTPException(status_code=400, detail="OIDC provider mismatch")
        return configured_provider
    if requested_provider:
        return requested_provider
    raise HTTPException(status_code=400, detail="OIDC provider is not configured")


async def _http_get_json(url: str) -> dict:
    import httpx

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


async def _get_oidc_discovery(provider: str) -> dict:
    disc_url = _DISCOVERY_URLS.get(provider, settings.OIDC_DISCOVERY_URL)
    if not disc_url:
        raise HTTPException(status_code=500, detail="OIDC discovery URL not configured")
    if not disc_url.startswith("https://") and not settings.DEBUG:
        raise HTTPException(status_code=400, detail="OIDC discovery endpoint must use HTTPS")
    return await _http_get_json(disc_url)


async def _exchange_code_for_tokens(
    code: str,
    redirect_uri: str,
    token_endpoint: str,
    code_verifier: Optional[str],
) -> dict:
    import httpx

    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": settings.OIDC_CLIENT_ID,
        "client_secret": settings.OIDC_CLIENT_SECRET,
    }
    if code_verifier:
        payload["code_verifier"] = code_verifier

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(token_endpoint, data=payload)
        if resp.status_code != 200:
            logger.warning("OIDC token exchange failed: %s %s", resp.status_code, resp.text[:200])
            raise HTTPException(status_code=401, detail="OIDC authentication failed")
        return resp.json()


async def _validate_id_token(id_token: str, discovery: dict, expected_nonce: str) -> dict:
    import jwt as jose_jwt
    from jwt.exceptions import InvalidTokenError as JWTError

    jwks_uri = discovery.get("jwks_uri")
    issuer = discovery.get("issuer")
    if not jwks_uri or not issuer:
        raise HTTPException(status_code=500, detail="OIDC discovery metadata is incomplete")

    unverified_header = jose_jwt.get_unverified_header(id_token)
    alg = unverified_header.get("alg")
    kid = unverified_header.get("kid")
    if not alg or alg not in ("RS256", "ES256"):
        raise HTTPException(status_code=401, detail="OIDC token uses an unsupported signing algorithm")

    jwks = await _http_get_json(jwks_uri)
    keys = jwks.get("keys", [])
    key = None
    if kid:
        key = next((candidate for candidate in keys if candidate.get("kid") == kid), None)
    elif len(keys) == 1:
        key = keys[0]

    if not key:
        raise HTTPException(status_code=401, detail="OIDC signing key not found")

    try:
        claims = jose_jwt.decode(
            id_token,
            key,
            algorithms=["RS256", "ES256"],
            audience=settings.OIDC_CLIENT_ID,
            issuer=issuer,
        )
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="OIDC token validation failed") from exc

    token_nonce = claims.get("nonce")
    if not token_nonce or token_nonce != expected_nonce:
        raise HTTPException(status_code=401, detail="OIDC nonce validation failed")

    return claims


@router.get("/config", response_model=OIDCConfigResponse)
async def oidc_config():
    """Return OIDC config for the frontend login page."""
    if not settings.OIDC_CLIENT_ID or not settings.OIDC_PROVIDER:
        return OIDCConfigResponse(enabled=False)

    try:
        discovery = await _get_oidc_discovery(settings.OIDC_PROVIDER)
    except (HTTPException, ValueError) as exc:
        logger.warning("OIDC config error: %s", exc)
        raise
    except Exception as exc:
        logger.error("Unexpected OIDC error: %s", exc)
        raise HTTPException(status_code=500, detail="OIDC configuration error")

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

    provider = _resolve_provider(data.provider)
    discovery = await _get_oidc_discovery(provider)
    token_endpoint = discovery.get("token_endpoint")
    if not token_endpoint:
        raise HTTPException(status_code=500, detail="OIDC discovery metadata is incomplete")

    tokens = await _exchange_code_for_tokens(
        data.code,
        data.redirect_uri,
        token_endpoint,
        data.code_verifier,
    )
    id_token = tokens.get("id_token")
    if not id_token:
        raise HTTPException(status_code=401, detail="No id_token in OIDC response")

    claims = await _validate_id_token(id_token, discovery, data.nonce)
    email = claims.get("email")
    # OIDC `sub` is only the identity provider's stable user identifier for
    # EDQ SSO account linking. It is unrelated to synopsis generation or any
    # server-side AI provider credentials.
    sub = claims.get("sub")
    name = claims.get("name")

    if not email or not sub:
        raise HTTPException(status_code=401, detail="OIDC response missing email or subject")

    if settings.OIDC_ALLOWED_DOMAINS:
        if not email or "@" not in email or email.count("@") != 1:
            raise HTTPException(status_code=400, detail="Invalid email format from identity provider")
        allowed = [domain.strip().lower() for domain in settings.OIDC_ALLOWED_DOMAINS.split(",") if domain.strip()]
        domain = email.split("@")[1].lower()
        if domain not in allowed:
            raise HTTPException(status_code=403, detail=f"Email domain '{domain}' is not allowed")
    else:
        if not email or "@" not in email or email.count("@") != 1:
            raise HTTPException(status_code=400, detail="Invalid email format from identity provider")

    query = select(User).where(
        or_(
            (User.oidc_subject == sub) & (User.oidc_provider == provider),
            User.email == email,
        )
    )
    results = (await db.execute(query)).scalars().all()
    if len(results) > 1:
        logger.warning("Multiple users found for OIDC email: %s", email)
        raise HTTPException(status_code=409, detail="Multiple accounts found for this email")
    user = results[0] if results else None

    email_verified = claims.get("email_verified", False)
    if user and not email_verified:
        raise HTTPException(status_code=403, detail="Email not verified by identity provider")

    if user:
        if not user.oidc_subject:
            user.oidc_provider = provider
            user.oidc_subject = sub
            user.oidc_email = email
        if name and not user.full_name:
            user.full_name = name
        user.last_login = utcnow_naive()
    else:
        import uuid
        local_part = email.split("@")[0][:64]
        existing_username = await db.execute(select(User).where(User.username == local_part))
        if existing_username.scalar_one_or_none():
            suffix = uuid.uuid4().hex[:8]
            username = f"{local_part}_{suffix}"
        else:
            username = local_part

        import secrets as _secrets
        from app.security.auth import hash_password

        user = User(
            email=email,
            username=username,
            password_hash=hash_password(_secrets.token_urlsafe(48)),
            full_name=name,
            role=UserRole.ENGINEER,
            oidc_provider=provider,
            oidc_subject=sub,
            oidc_email=email,
            last_login=utcnow_naive(),
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)
        logger.info("Auto-provisioned OIDC user: %s (%s via %s)", username, email, provider)

    access_token = create_access_token({"sub": user.id, "role": user.role.value})
    refresh_token = create_refresh_token({"sub": user.id})
    csrf_token = generate_csrf_token()

    expires_at = utcnow_naive() + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    await store_refresh_token(db, user.id, refresh_token, expires_at)

    set_auth_cookies(response, access_token, csrf_token, refresh_token)
    await log_security_event(
        db,
        "auth.oidc_login",
        user_id=user.id,
        details={"provider": provider, "email": email},
        request=request,
    )

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
