"""Protocol Whitelist schemas."""

from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime


class WhitelistEntry(BaseModel):
    port: int
    protocol: str  # TCP, UDP, TCP/UDP
    service: str
    required_version: Optional[str] = None


class WhitelistCreate(BaseModel):
    name: str = Field(..., max_length=128)
    description: Optional[str] = None
    is_default: bool = False
    entries: List[WhitelistEntry]


class WhitelistUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=128)
    description: Optional[str] = None
    is_default: Optional[bool] = None
    entries: Optional[List[WhitelistEntry]] = None


class WhitelistResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    is_default: bool
    entries: List[Any]
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
