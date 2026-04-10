"""CVE vulnerability lookup routes."""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.database import get_db
from app.models.device import Device
from app.models.user import User
from app.security.auth import get_current_active_user
from app.services.cve_lookup import lookup_cves_for_services, lookup_cves_by_keyword
from app.services.cve_correlator import correlate_device_cves

logger = logging.getLogger("edq.routes.cve")

router = APIRouter()


class CVELookupRequest(BaseModel):
    keyword: Optional[str] = None
    device_id: Optional[str] = None
    max_results: int = Field(5, ge=1, le=20)


class CVEResult(BaseModel):
    id: str
    description: str = ""
    severity: str = "UNKNOWN"
    cvss_score: Optional[float] = None
    url: str = ""


class ServiceCVEResult(BaseModel):
    port: int
    service: str
    version: str
    cves: List[CVEResult]


class CVELookupResponse(BaseModel):
    status: str
    query: str
    total_cves: int
    results: List[ServiceCVEResult] = []
    keyword_results: List[CVEResult] = []


class CorrelationQuery(BaseModel):
    product: str
    version: str = ""
    source: str = ""


class CorrelationItem(BaseModel):
    query: CorrelationQuery
    device_id: str


class CVECorrelationResponse(BaseModel):
    device_id: str
    total_queries: int
    correlations: List[CorrelationItem]


@router.post("/lookup", response_model=CVELookupResponse)
async def lookup_cves(
    data: CVELookupRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Look up CVEs for a device's detected services or by keyword.

    If device_id is provided, uses the device's open_ports data from nmap scans.
    If keyword is provided, does a direct NVD keyword search.
    """
    if data.device_id:
        result = await db.execute(select(Device).where(Device.id == data.device_id))
        device = result.scalar_one_or_none()
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")

        open_ports = device.open_ports or []
        if not open_ports:
            return CVELookupResponse(
                status="complete",
                query=f"device:{device.ip_address}",
                total_cves=0,
                results=[],
            )

        service_results = await lookup_cves_for_services(
            open_ports, max_results_per_service=data.max_results
        )

        total = sum(len(r["cves"]) for r in service_results)
        return CVELookupResponse(
            status="complete",
            query=f"device:{device.ip_address}",
            total_cves=total,
            results=[
                ServiceCVEResult(
                    port=r["port"],
                    service=r["service"],
                    version=r["version"],
                    cves=[CVEResult(**c) for c in r["cves"]],
                )
                for r in service_results
            ],
        )

    elif data.keyword:
        cves = await lookup_cves_by_keyword(data.keyword, data.max_results)
        return CVELookupResponse(
            status="complete",
            query=data.keyword,
            total_cves=len(cves),
            keyword_results=[CVEResult(**c) for c in cves],
        )

    else:
        raise HTTPException(
            status_code=400,
            detail="Provide either device_id or keyword",
        )


@router.get("/correlate/{device_id}", response_model=CVECorrelationResponse)
async def correlate_cves(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Auto-correlate CVEs for a device based on its discovered services.

    Returns a list of search queries derived from the device's open ports,
    OS fingerprint, and manufacturer/model data.  The frontend can feed
    these queries into ``POST /api/v1/cve/lookup`` to fetch actual CVE
    results from the NVD.
    """
    correlations = await correlate_device_cves(device_id, db)
    if not correlations:
        # Check whether the device exists at all
        result = await db.execute(select(Device).where(Device.id == device_id))
        device = result.scalar_one_or_none()
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")

    return CVECorrelationResponse(
        device_id=device_id,
        total_queries=len(correlations),
        correlations=[
            CorrelationItem(
                query=CorrelationQuery(**c["query"]),
                device_id=c["device_id"],
            )
            for c in correlations
        ],
    )
