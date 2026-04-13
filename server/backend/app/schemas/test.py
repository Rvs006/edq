"""Test-related schemas: templates, runs, results."""

from pydantic import BaseModel, ConfigDict, Field, field_validator
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
    model_config = ConfigDict(from_attributes=True)

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

# --- Test Run ---
class TestRunCreate(BaseModel):
    device_id: str = Field(..., max_length=36)
    template_id: str = Field(..., max_length=36)
    agent_id: Optional[str] = Field(None, max_length=36)
    connection_scenario: str = Field("direct", max_length=32)
    metadata: Optional[Any] = None


class TestRunUpdate(BaseModel):
    connection_scenario: Optional[str] = Field(None, max_length=32)
    synopsis: Optional[str] = None
    synopsis_status: Optional[str] = None


class ReadinessSummaryResponse(BaseModel):
    score: int = Field(..., ge=1, le=10)
    level: str
    label: str
    report_ready: bool
    operational_ready: bool
    blocking_issue_count: int
    pending_manual_count: int
    release_blocking_failure_count: int
    review_required_issue_count: int
    manual_evidence_pending_count: int
    advisory_count: int
    override_count: int
    failed_test_count: int
    completed_result_count: int
    total_result_count: int
    trust_tier_counts: dict[str, int]
    reasons: List[str]
    next_step: str
    summary: str


class TestRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    device_id: str
    device_name: Optional[str] = None
    device_ip: Optional[str] = None
    device_mac_address: Optional[str] = None
    device_manufacturer: Optional[str] = None
    device_model: Optional[str] = None
    device_category: Optional[str] = None
    template_id: str
    template_name: Optional[str] = None
    engineer_id: str
    engineer_name: Optional[str] = None
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
    confidence: int = 1
    readiness_summary: Optional[ReadinessSummaryResponse] = None
    created_at: datetime
    updated_at: datetime

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
    findings: Optional[Any] = None
    compliance_map: Optional[List[str]] = None
    duration_seconds: Optional[float] = None


class TestResultUpdate(BaseModel):
    verdict: Optional[str] = None
    comment: Optional[str] = None
    comment_override: Optional[str] = None
    engineer_notes: Optional[str] = None
    raw_output: Optional[str] = None
    parsed_data: Optional[Any] = None
    findings: Optional[Any] = None
    evidence_files: Optional[List[str]] = None
    duration_seconds: Optional[float] = None


class TestResultOverrideRequest(BaseModel):
    verdict: str = Field(..., min_length=2, max_length=32)
    override_reason: str = Field(..., min_length=3, max_length=4000)
    comment: Optional[str] = Field(None, max_length=4000)


class TestResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    raw_output: Optional[str] = None
    parsed_data: Optional[Any] = None
    findings: Optional[Any] = None
    is_overridden: bool = False
    override_reason: Optional[str] = None
    override_verdict: Optional[str] = None
    overridden_by_user_id: Optional[str] = None
    overridden_by_username: Optional[str] = None
    overridden_at: Optional[datetime] = None
    evidence_files: Optional[List[str]] = None
    compliance_map: Optional[List[str]] = None
    duration_seconds: Optional[float] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
