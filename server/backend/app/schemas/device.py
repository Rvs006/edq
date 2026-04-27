"""Device schemas."""

import ipaddress
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import Optional, List, Any
from datetime import datetime

from app.models.device import AddressingMode, DeviceCategory, DeviceStatus

_MAC_RE = re.compile(
    r"^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$"
)

_ADDRESSING_MODES = {mode.value for mode in AddressingMode}
_DEVICE_CATEGORIES = {category.value for category in DeviceCategory}
_DEVICE_STATUSES = {status.value for status in DeviceStatus}


class DeviceCreate(BaseModel):
    ip_address: Optional[str] = Field(None, max_length=45)
    mac_address: Optional[str] = Field(None, max_length=17)
    addressing_mode: Optional[str] = Field("static", max_length=16)

    @field_validator("ip_address")
    @classmethod
    def validate_ip(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                ipaddress.IPv4Address(v)
            except ValueError as exc:
                raise ValueError("Invalid IPv4 address") from exc
        return v

    @field_validator("mac_address")
    @classmethod
    def validate_mac(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not _MAC_RE.match(v):
            raise ValueError("Invalid MAC address format (expected AA:BB:CC:DD:EE:FF)")
        return v

    @field_validator("addressing_mode")
    @classmethod
    def validate_addressing_mode(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip().lower()
        if v is not None and v not in _ADDRESSING_MODES:
            raise ValueError("addressing_mode must be 'static', 'dhcp', or 'unknown'")
        return v
    hostname: Optional[str] = Field(None, max_length=255)
    manufacturer: Optional[str] = Field(None, max_length=128)
    model: Optional[str] = Field(None, max_length=128)
    firmware_version: Optional[str] = Field(None, max_length=64)
    serial_number: Optional[str] = Field(None, max_length=128)
    category: str = Field("unknown", max_length=64)
    location: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = Field(None, max_length=2000)
    profile_id: Optional[str] = Field(None, max_length=36)
    project_id: Optional[str] = Field(None, max_length=36)

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        normalized = v.strip().lower()
        if normalized not in _DEVICE_CATEGORIES:
            raise ValueError(f"category must be one of: {', '.join(sorted(_DEVICE_CATEGORIES))}")
        return normalized


class DeviceUpdate(BaseModel):
    ip_address: Optional[str] = Field(None, max_length=45)
    mac_address: Optional[str] = Field(None, max_length=17)
    hostname: Optional[str] = Field(None, max_length=255)
    manufacturer: Optional[str] = Field(None, max_length=128)
    model: Optional[str] = Field(None, max_length=128)
    firmware_version: Optional[str] = Field(None, max_length=64)
    serial_number: Optional[str] = Field(None, max_length=128)
    category: Optional[str] = Field(None, max_length=64)
    status: Optional[str] = Field(None, max_length=32)
    addressing_mode: Optional[str] = Field(None, max_length=16)
    location: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = Field(None, max_length=2000)
    profile_id: Optional[str] = Field(None, max_length=36)
    open_ports: Optional[List[Any]] = None
    discovery_data: Optional[Any] = None

    @field_validator("ip_address")
    @classmethod
    def validate_ip(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                ipaddress.IPv4Address(v)
            except ValueError as exc:
                raise ValueError("Invalid IPv4 address") from exc
        return v

    @field_validator("mac_address")
    @classmethod
    def validate_mac(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not _MAC_RE.match(v):
            raise ValueError("Invalid MAC address format (expected AA:BB:CC:DD:EE:FF)")
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        normalized = v.strip().lower()
        if normalized not in _DEVICE_CATEGORIES:
            raise ValueError(f"category must be one of: {', '.join(sorted(_DEVICE_CATEGORIES))}")
        return normalized

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        normalized = v.strip().lower()
        if normalized not in _DEVICE_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(sorted(_DEVICE_STATUSES))}")
        return normalized

    @field_validator("addressing_mode")
    @classmethod
    def validate_addressing_mode(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        normalized = v.strip().lower()
        if normalized not in _ADDRESSING_MODES:
            raise ValueError("addressing_mode must be 'static', 'dhcp', or 'unknown'")
        return normalized


class DeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    ip_address: Optional[str] = None
    mac_address: Optional[str] = None
    addressing_mode: Optional[str] = "static"
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
    location: Optional[str] = None
    serial_number: Optional[str] = None
    last_seen_at: Optional[datetime] = None
    last_tested: Optional[datetime] = None
    last_verdict: Optional[str] = None
    project_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class DeviceCreateResponse(DeviceResponse):
    reachability_verified: bool = False


class DiscoveryRequest(BaseModel):
    subnet: Optional[str] = Field(None, max_length=43)  # e.g. "192.168.1.0/24"
    ip_address: Optional[str] = Field(None, max_length=45)
    interface: Optional[str] = Field(None, max_length=64)
    agent_id: Optional[str] = Field(None, max_length=36)
    project_id: Optional[str] = Field(None, max_length=36)

    @field_validator("subnet")
    @classmethod
    def validate_subnet(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        try:
            network = ipaddress.ip_network(v, strict=False)
        except ValueError as exc:
            raise ValueError("Invalid CIDR subnet (e.g. 192.168.1.0/24)") from exc
        if network.version != 4:
            raise ValueError("Discovery subnet must be IPv4")
        if network.prefixlen < 16 or network.prefixlen > 32:
            raise ValueError("CIDR prefix must be between /16 and /32")
        return str(network)

    @model_validator(mode="after")
    def validate_single_target(self) -> "DiscoveryRequest":
        if self.ip_address and self.subnet:
            raise ValueError("Provide either ip_address or subnet, not both")
        if not self.ip_address and not self.subnet:
            raise ValueError("Provide either ip_address or subnet")
        return self

    @field_validator("ip_address")
    @classmethod
    def validate_discovery_ip(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                ipaddress.IPv4Address(v)
            except ValueError as exc:
                raise ValueError("Invalid IPv4 address") from exc
        return v
