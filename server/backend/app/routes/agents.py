"""Agent management routes."""

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from datetime import datetime, timezone

from app.models.database import get_db
from app.models.agent import Agent
from app.models.user import User
from app.schemas.agent import AgentRegister, AgentResponse, AgentRegisterResponse, AgentHeartbeat
from app.security.auth import get_current_active_user, require_role, generate_api_key, hash_api_key

router = APIRouter()


@router.get("/", response_model=List[AgentResponse])
async def list_agents(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    result = await db.execute(select(Agent).where(Agent.is_active == True).order_by(Agent.name))
    return result.scalars().all()


@router.post("/register", response_model=AgentRegisterResponse, status_code=201)
async def register_agent(
    data: AgentRegister,
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
    return AgentRegisterResponse(
        id=agent.id,
        name=agent.name,
        api_key=api_key,
        api_key_prefix=agent.api_key_prefix,
    )


@router.post("/heartbeat")
async def agent_heartbeat(
    data: AgentHeartbeat,
    x_agent_key: str = Header(..., alias="X-Agent-Key"),
    db: AsyncSession = Depends(get_db),
):
    """Agent heartbeat — updates status and last seen."""
    key_hash = hash_api_key(x_agent_key)
    result = await db.execute(select(Agent).where(Agent.api_key_hash == key_hash))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=401, detail="Invalid agent key")

    agent.last_heartbeat = datetime.now(timezone.utc)
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

    return {"status": "ok", "agent_id": agent.id}


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
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(["admin"])),
):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent.is_active = False
