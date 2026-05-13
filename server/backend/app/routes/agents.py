"""Agent management routes."""

import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.database import get_db
from app.models.agent import Agent
from app.models.user import User
from app.schemas.agent import AgentRegister, AgentResponse, AgentRegisterResponse, AgentHeartbeat
from app.security.auth import get_current_active_user, require_role, generate_api_key, hash_api_key
from app.routes.websocket_routes import manager
from app.utils.audit import log_action
from app.utils.datetime import utcnow_naive

router = APIRouter()
compat_router = APIRouter()
_VERSION_PART_RE = re.compile(r"\d+")


def _parse_version_tuple(raw: str | None) -> tuple[int, ...] | None:
    text = str(raw or "").strip()
    if not text:
        return None
    main = text.split("+", 1)[0].split("-", 1)[0]
    parts = _VERSION_PART_RE.findall(main)
    if not parts:
        return None
    return tuple(int(part) for part in parts[:4])


def _compare_version_tuples(left: tuple[int, ...], right: tuple[int, ...]) -> int:
    width = max(len(left), len(right))
    left_padded = left + (0,) * (width - len(left))
    right_padded = right + (0,) * (width - len(right))
    if left_padded < right_padded:
        return -1
    if left_padded > right_padded:
        return 1
    return 0


def _resolve_agent_version_status(agent_version: str | None) -> str:
    parsed_agent = _parse_version_tuple(agent_version)
    if parsed_agent is None:
        return "compatible"

    parsed_min = _parse_version_tuple(settings.MIN_AGENT_VERSION) or _parse_version_tuple(settings.APP_VERSION)
    parsed_current = _parse_version_tuple(settings.APP_VERSION)

    if parsed_min is not None and _compare_version_tuples(parsed_agent, parsed_min) < 0:
        return "incompatible"
    if parsed_current is not None and _compare_version_tuples(parsed_agent, parsed_current) < 0:
        return "deprecated"
    return "compatible"


def _extract_agent_key(x_agent_key: str | None, authorization: str | None) -> str:
    if x_agent_key and x_agent_key.strip():
        return x_agent_key.strip()

    auth_value = str(authorization or "").strip()
    if not auth_value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Agent authentication required",
        )

    scheme, _, token = auth_value.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid agent authorization header",
        )
    return token.strip()


@router.get("/", response_model=List[AgentResponse])
async def list_agents(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    result = await db.execute(select(Agent).where(Agent.is_active == True).order_by(Agent.name))
    return result.scalars().all()


@compat_router.post("/register", response_model=AgentRegisterResponse, status_code=201, include_in_schema=False)
@router.post("/register", response_model=AgentRegisterResponse, status_code=201)
async def register_agent(
    data: AgentRegister,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["admin"])),
):
    """Register a new agent. Returns API key (shown only once)."""
    api_key = generate_api_key()
    agent = Agent(
        name=data.name,
        hostname=data.hostname,
        platform=data.platform,
        agent_version=data.agent_version,
        capabilities=data.capabilities,
        api_key_hash=hash_api_key(api_key),
        api_key_prefix=api_key[:8],
        registered_by=user.id,
    )
    db.add(agent)
    await db.flush()
    await db.refresh(agent)
    await log_action(db, user, "agent.create", "agent", agent.id, {"name": agent.name}, request)
    return AgentRegisterResponse(
        id=agent.id,
        name=agent.name,
        api_key=api_key,
        api_key_prefix=agent.api_key_prefix,
    )


@compat_router.post("/heartbeat", include_in_schema=False)
@router.post("/heartbeat")
async def agent_heartbeat(
    data: AgentHeartbeat,
    x_agent_key: Optional[str] = Header(None, alias="X-Agent-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Agent heartbeat — updates status and last seen."""
    agent_key = _extract_agent_key(x_agent_key, authorization)
    key_hash = hash_api_key(agent_key)
    result = await db.execute(select(Agent).where(Agent.api_key_hash == key_hash))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=401, detail="Invalid agent key")

    agent.last_heartbeat = utcnow_naive()
    if data.status:
        agent.status = data.status
    if data.current_task:
        agent.current_task = data.current_task
    if data.ip_address:
        agent.ip_address = data.ip_address
    if data.agent_version:
        agent.agent_version = data.agent_version
    if data.capabilities:
        agent.capabilities = data.capabilities

    # Broadcast heartbeat update to connected WebSocket clients
    await manager.broadcast("agents", {
        "type": "heartbeat",
        "agent_id": agent.id,
        "status": agent.status,
        "timestamp": agent.last_heartbeat.isoformat(),
    })

    return {
        "status": "ok",
        "agent_id": agent.id,
        "version_status": _resolve_agent_version_status(agent.agent_version),
        "min_agent_version": settings.MIN_AGENT_VERSION,
        "server_version": settings.APP_VERSION,
    }


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.delete("/{agent_id}", status_code=204)
async def deactivate_agent(
    agent_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(["admin"])),
):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent.is_active = False
    await log_action(db, user, "agent.deactivate", "agent", agent_id, {"name": agent.name}, request)
