"""Two-Factor Authentication routes — TOTP setup, verification, and enforcement."""

import io
import base64
import logging
from typing import Optional

import pyotp
import qrcode
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from app.models.user import User
from app.security.auth import get_current_active_user
from app.utils.audit import log_action

logger = logging.getLogger("edq.routes.two_factor")

router = APIRouter()


class TwoFactorSetupResponse(BaseModel):
    secret: str
    otpauth_url: str
    qr_code_base64: str


class TwoFactorVerifyRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)


class TwoFactorDisableRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)
    password: str = Field(..., min_length=1)


@router.get("/status")
async def two_factor_status(user: User = Depends(get_current_active_user)):
    """Check if 2FA is enabled for the current user."""
    return {
        "enabled": bool(user.totp_secret),
        "enforced": bool(user.totp_secret),
    }


@router.post("/setup", response_model=TwoFactorSetupResponse)
async def two_factor_setup(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a TOTP secret and QR code. Does NOT enable 2FA until verified."""
    if user.totp_secret:
        raise HTTPException(status_code=400, detail="2FA is already enabled. Disable it first to reconfigure.")

    secret = pyotp.random_base32()

    # Store provisionally — will be confirmed on verify
    user.totp_provisional_secret = secret
    await db.flush()

    totp = pyotp.TOTP(secret)
    otpauth_url = totp.provisioning_uri(name=user.username, issuer_name="EDQ")

    # Generate QR code as base64 PNG
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(otpauth_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    return TwoFactorSetupResponse(
        secret=secret,
        otpauth_url=otpauth_url,
        qr_code_base64=qr_b64,
    )


@router.post("/verify")
async def two_factor_verify(
    data: TwoFactorVerifyRequest,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Verify a TOTP code to confirm 2FA setup. This activates 2FA on the account."""
    secret = user.totp_provisional_secret
    if not secret:
        raise HTTPException(status_code=400, detail="No 2FA setup in progress. Call /setup first.")

    totp = pyotp.TOTP(secret)
    if not totp.verify(data.code, valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid code. Please try again.")

    # Activate 2FA
    user.totp_secret = secret
    user.totp_provisional_secret = None
    await db.flush()

    await log_action(db, user, "two_factor.enable", "user", user.id, request=request)

    return {"message": "Two-factor authentication enabled successfully"}


@router.post("/disable")
async def two_factor_disable(
    data: TwoFactorDisableRequest,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Disable 2FA. Requires current TOTP code AND password for safety."""
    if not user.totp_secret:
        raise HTTPException(status_code=400, detail="2FA is not enabled")

    from app.security.auth import verify_password
    if not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Invalid password")

    totp = pyotp.TOTP(user.totp_secret)
    if not totp.verify(data.code, valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid 2FA code")

    user.totp_secret = None
    user.totp_provisional_secret = None
    await db.flush()

    await log_action(db, user, "two_factor.disable", "user", user.id, request=request)

    return {"message": "Two-factor authentication disabled"}


def verify_totp_for_user(user: User, code: Optional[str]) -> bool:
    """Verify a TOTP code for a user during login. Returns True if valid or 2FA not enabled."""
    if not user.totp_secret:
        return True
    if not code:
        return False
    totp = pyotp.TOTP(user.totp_secret)
    return totp.verify(code, valid_window=1)
