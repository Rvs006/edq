"""Authentication schemas."""

from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional


def _validate_password_strength(password: str) -> str:
    """Enforce password complexity: uppercase, lowercase, digit required."""
    if not any(c.isupper() for c in password):
        raise ValueError("Password must contain at least one uppercase letter")
    if not any(c.islower() for c in password):
        raise ValueError("Password must contain at least one lowercase letter")
    if not any(c.isdigit() for c in password):
        raise ValueError("Password must contain at least one digit")
    return password


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=320)
    password: str = Field(..., min_length=8, max_length=128)
    totp_code: Optional[str] = Field(None, min_length=6, max_length=6)

    @field_validator("username")
    @classmethod
    def normalize_login_identifier(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Username or email must be at least 3 characters")
        return value


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=8, max_length=128)
    full_name: Optional[str] = Field(None, max_length=128)

    @field_validator("password")
    @classmethod
    def check_password_strength(cls, v: str) -> str:
        return _validate_password_strength(v)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def check_password_strength(cls, v: str) -> str:
        return _validate_password_strength(v)
