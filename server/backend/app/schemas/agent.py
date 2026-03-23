"""Agent schemas."""

from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime


class AgentRegister(BaseModel):
    name: str = Field(..., max_length=128)
    hostname: Optional[str] = Field(None, max_length=255)
    platform: Optional[str] = Field(None, max_length=32)
    agent_version: Optional[str] = Field(None, max_length=32)
    capabilities: Optional[Any] = None


class AgentResponse(BaseModel):
    id: str
    name: str
    hostname: Optional[str] = None
    api_key_prefix: str
    platform: Optional[str] = None
    agent_version: Optional[str] = None
    ip_address: Optional[str] = None
    status: str
    last_heartbeat: Optional[datetime] = None
    capabilities: Optional[Any] = None
    current_task: Optional[str] = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class AgentRegisterResponse(BaseModel):
    id: str
    name: str
    api_key: str  # Only returned once at registration
    api_key_prefix: str


class AgentHeartbeat(BaseModel):
    status: Optional[str] = None
    current_task: Optional[str] = None
    ip_address: Optional[str] = None
    agent_version: Optional[str] = None
    capabilities: Optional[Any] = None
