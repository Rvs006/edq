"""Device schemas."""

import re
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Any
from datetime import datetime

_IP_RE = re.compile(
    r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$"
)
_MAC_RE = re.compile(
    r"^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$"
)


class DeviceCreate(BaseModel):
    ip_address: str = Field(..., max_length=45)
    mac_address: Optional[str] = Field(None, max_length=17)

    @field_validator("ip_address")
    @classmethod
    def validate_ip(cls, v: str) -> str:
        if not _IP_RE.match(v):
            raise ValueError("Invalid IPv4 address")
        return v

    @field_validator("mac_address")
    @classmethod
    def validate_mac(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not _MAC_RE.match(v):
            raise ValueError("Invalid MAC address format (expected AA:BB:CC:DD:EE:FF)")
        return v
    hostname: Optional[str] = Field(None, max_length=255)
    manufacturer: Optional[str] = Field(None, max_length=128)
    model: Optional[str] = Field(None, max_length=128)
    firmware_version: Optional[str] = Field(None, max_length=64)
    category: str = "unknown"
    notes: Optional[str] = None
    profile_id: Optional[str] = None


class DeviceUpdate(BaseModel):
    ip_address: Optional[str] = Field(None, max_length=45)
    mac_address: Optional[str] = Field(None, max_length=17)
    hostname: Optional[str] = Field(None, max_length=255)
    manufacturer: Optional[str] = Field(None, max_length=128)
    model: Optional[str] = Field(None, max_length=128)
    firmware_version: Optional[str] = Field(None, max_length=64)
    category: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    profile_id: Optional[str] = None
    open_ports: Optional[List[Any]] = None
    discovery_data: Optional[Any] = None


class DeviceResponse(BaseModel):
    id: str
    ip_address: str
    mac_address: Optional[str] = None
    hostname: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    firmware_version: Optional[str] = None
    category: str
    status: str
    oui_vendor: Optional[str] = None
    os_fingerprint: Optional[str] = None
    open_ports: Optional[List[Any]] = None
    discovery_data: Optional[Any] = None
    notes: Optional[str] = None
    profile_id: Optional[str] = None
    discovered_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DiscoveryRequest(BaseModel):
    subnet: Optional[str] = None  # e.g. "192.168.1.0/24"
    ip_address: Optional[str] = None  # Single IP
    interface: Optional[str] = None  # Network interface name
    agent_id: Optional[str] = None
