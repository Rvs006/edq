"""Generate report artifacts from a qualification run.

The route layer should only authorize the caller and translate HTTP errors.
This module owns the run context, readiness check, and renderer selection for
report generation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.branding import BrandingSettings
from app.models.protocol_whitelist import ProtocolWhitelist
from app.models.report_config import ReportConfig
from app.models.test_result import TestResult
from app.models.test_run import TestRun
from app.models.test_template import TestTemplate
from app.services.report_generator import generate_excel_report, generate_word_report
from app.services.run_readiness import (
    build_run_readiness_summary,
    get_report_readiness_block_message,
)

ReportType = Literal["excel", "word"]


class ReportContextNotFoundError(LookupError):
    pass


class ReportNotReadyError(RuntimeError):
    def __init__(self, message: str, readiness_summary: dict[str, Any]) -> None:
        super().__init__(message)
        self.readiness_summary = readiness_summary


@dataclass(slots=True)
class ReportContext:
    test_run: TestRun
    test_results: list[TestResult]
    report_config: ReportConfig | None
    enabled_test_ids: list[str] | None
    whitelist_entries: list[dict[str, Any]] | None
    branding_settings: BrandingSettings | None


@dataclass(slots=True)
class ReportArtifact:
    path: str
    filename: str
    report_type: ReportType
    readiness_summary: dict[str, Any]


def normalize_report_type(report_type: str) -> ReportType:
    aliases = {
        "xlsx": "excel",
        "docx": "word",
    }
    normalized = aliases.get(report_type, report_type)
    if normalized not in {"excel", "word"}:
        raise ValueError("Invalid report type. Use 'excel' or 'word'.")
    return normalized  # type: ignore[return-value]


def _json_list(value: Any) -> list[Any] | None:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return None
    return value if isinstance(value, list) else None


async def load_report_context(
    db: AsyncSession,
    *,
    test_run_id: str,
    report_config_id: str | None = None,
) -> ReportContext:
    result = await db.execute(
        select(TestRun)
        .options(selectinload(TestRun.device), selectinload(TestRun.engineer))
        .where(TestRun.id == test_run_id)
    )
    test_run = result.scalar_one_or_none()
    if not test_run:
        raise ReportContextNotFoundError("Test run not found")

    results = await db.execute(
        select(TestResult)
        .where(TestResult.test_run_id == test_run_id)
        .order_by(TestResult.test_id)
    )
    test_results = list(results.scalars().all())

    report_config = None
    if report_config_id:
        config_result = await db.execute(
            select(ReportConfig).where(ReportConfig.id == report_config_id)
        )
        report_config = config_result.scalar_one_or_none()

    enabled_test_ids = None
    whitelist_entries = None
    if test_run.template_id:
        tmpl_result = await db.execute(
            select(TestTemplate).where(TestTemplate.id == test_run.template_id)
        )
        template = tmpl_result.scalar_one_or_none()
        enabled_test_ids = _json_list(template.test_ids) if template and template.test_ids else None

        if template and getattr(template, "whitelist_id", None):
            wl_result = await db.execute(
                select(ProtocolWhitelist).where(ProtocolWhitelist.id == template.whitelist_id)
            )
            whitelist = wl_result.scalar_one_or_none()
            whitelist_entries = (
                _json_list(whitelist.entries)
                if whitelist and whitelist.entries
                else None
            )

    branding_result = await db.execute(select(BrandingSettings).limit(1))
    branding_settings = branding_result.scalar_one_or_none()

    return ReportContext(
        test_run=test_run,
        test_results=test_results,
        report_config=report_config,
        enabled_test_ids=enabled_test_ids,
        whitelist_entries=whitelist_entries,
        branding_settings=branding_settings,
    )


async def generate_report_artifact(
    context: ReportContext,
    *,
    report_type: str,
    template_key: str,
    include_synopsis: bool,
) -> ReportArtifact:
    normalized_type = normalize_report_type(report_type)
    readiness_summary = build_run_readiness_summary(
        context.test_run,
        context.test_results,
    )
    if not readiness_summary["report_ready"]:
        raise ReportNotReadyError(
            get_report_readiness_block_message(readiness_summary),
            readiness_summary,
        )

    if normalized_type == "excel":
        file_path = await generate_excel_report(
            context.test_run,
            context.test_results,
            context.report_config,
            template_key=template_key,
            enabled_test_ids=context.enabled_test_ids,
            whitelist_entries=context.whitelist_entries,
            include_synopsis=include_synopsis,
            branding_settings=context.branding_settings,
            readiness_summary=readiness_summary,
        )
    else:
        file_path = await generate_word_report(
            context.test_run,
            context.test_results,
            context.report_config,
            include_synopsis=include_synopsis,
            enabled_test_ids=context.enabled_test_ids,
            whitelist_entries=context.whitelist_entries,
            template_key=template_key,
            branding_settings=context.branding_settings,
            readiness_summary=readiness_summary,
        )

    return ReportArtifact(
        path=file_path,
        filename=Path(file_path).name,
        report_type=normalized_type,
        readiness_summary=readiness_summary,
    )
