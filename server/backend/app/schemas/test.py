"""Test-related schemas: templates, runs, results."""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Any
from datetime import datetime
import json


# --- Test Template ---
class TestTemplateCreate(BaseModel):
    name: str = Field(..., max_length=128)
    description: Optional[str] = Field(None, max_length=2000)
    test_ids: List[str] = Field(..., max_length=500)
    whitelist_id: Optional[str] = None
    cell_mappings: Optional[Any] = None
    report_config: Optional[Any] = None
    branding: Optional[Any] = None
    is_default: bool = False


class TestTemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=128)
    description: Optional[str] = None
    test_ids: Optional[List[str]] = None
    whitelist_id: Optional[str] = None
    cell_mappings: Optional[Any] = None
    report_config: Optional[Any] = None
    branding: Optional[Any] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None


class TestTemplateResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    version: str
    test_ids: List[str]
    whitelist_id: Optional[str] = None
    cell_mappings: Optional[Any] = None
    report_config: Optional[Any] = None
    branding: Optional[Any] = None
    is_default: bool
    is_active: bool
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    @field_validator("test_ids", mode="before")
    @classmethod
    def parse_test_ids(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return json.loads(v)
        return v  # type: ignore[return-value]

    class Config:
        from_attributes = True


# --- Test Run ---
class TestRunCreate(BaseModel):
    device_id: str = Field(..., max_length=36)
    template_id: str = Field(..., max_length=36)
    agent_id: Optional[str] = Field(None, max_length=36)
    connection_scenario: str = Field("direct", max_length=32)
    metadata: Optional[Any] = None


class TestRunUpdate(BaseModel):
    status: Optional[str] = None
    overall_verdict: Optional[str] = None
    progress_pct: Optional[float] = None
    completed_tests: Optional[int] = None
    passed_tests: Optional[int] = None
    failed_tests: Optional[int] = None
    advisory_tests: Optional[int] = None
    na_tests: Optional[int] = None
    synopsis: Optional[str] = None
    synopsis_status: Optional[str] = None


class TestRunResponse(BaseModel):
    id: str
    device_id: str
    device_name: Optional[str] = None
    device_ip: Optional[str] = None
    template_id: str
    template_name: Optional[str] = None
    engineer_id: str
    agent_id: Optional[str] = None
    connection_scenario: str = "direct"
    status: str
    overall_verdict: Optional[str] = None
    progress_pct: float
    total_tests: int
    completed_tests: int
    passed_tests: int
    failed_tests: int
    advisory_tests: int
    na_tests: int
    synopsis: Optional[str] = None
    synopsis_status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    run_metadata: Optional[Any] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# --- Test Result ---
class TestResultCreate(BaseModel):
    test_run_id: str = Field(..., max_length=36)
    test_id: str = Field(..., max_length=64)
    test_name: str = Field(..., max_length=256)
    tier: str = Field(..., max_length=32)
    tool: Optional[str] = Field(None, max_length=64)
    verdict: str = Field("pending", max_length=32)
    is_essential: str = Field("no", max_length=8)
    comment: Optional[str] = Field(None, max_length=4000)
    raw_output: Optional[str] = None
    parsed_data: Optional[Any] = None
    findings: Optional[List[Any]] = None
    compliance_map: Optional[List[str]] = None
    duration_seconds: Optional[float] = None


class TestResultUpdate(BaseModel):
    verdict: Optional[str] = None
    comment: Optional[str] = None
    comment_override: Optional[str] = None
    engineer_notes: Optional[str] = None
    raw_output: Optional[str] = None
    parsed_data: Optional[Any] = None
    findings: Optional[List[Any]] = None
    evidence_files: Optional[List[str]] = None
    duration_seconds: Optional[float] = None


class TestResultResponse(BaseModel):
    id: str
    test_run_id: str
    test_id: str
    test_name: str
    tier: str
    tool: Optional[str] = None
    verdict: str
    is_essential: str
    comment: Optional[str] = None
    comment_override: Optional[str] = None
    engineer_notes: Optional[str] = None
    parsed_data: Optional[Any] = None
    findings: Optional[List[Any]] = None
    evidence_files: Optional[List[str]] = None
    compliance_map: Optional[List[str]] = None
    duration_seconds: Optional[float] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
