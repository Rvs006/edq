"""Provision test runs and their initial result rows.

This module is the boundary for turning a template/selection into a concrete
qualification run. Route handlers and schedulers should not duplicate the
TestRun/TestResult construction rules.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.models.test_result import TestResult, TestTier, TestVerdict
from app.models.test_run import TestRun, TestRunStatus
from app.models.test_template import TestTemplate
from app.services.scenario_routing import (
    get_manual_routing_note,
    get_scenario_routing_decision,
    normalize_connection_scenario,
)
from app.services.test_library import get_test_by_id
from app.services.test_selection import TestSelectionError, validate_active_test_ids
from app.utils.collections import ordered_unique


@dataclass(slots=True)
class ProvisionedTestRun:
    run: TestRun
    test_ids: list[str]
    selection_source: str


def template_test_ids(template: TestTemplate | None) -> list[str]:
    """Return de-duplicated test ids from a template, accepting legacy JSON."""
    if template is None:
        return []
    raw_ids = template.test_ids
    if isinstance(raw_ids, str):
        raw_ids = json.loads(raw_ids)
    return ordered_unique(raw_ids or [])


def resolve_test_run_selection(
    template: TestTemplate | None,
    selected_test_ids: list[str] | None = None,
    *,
    require_selected_within_template: bool = False,
) -> list[tuple[str, dict[str, Any]]]:
    """Resolve active test definitions for a run.

    The returned order follows the caller's selected ids, or the template when
    no explicit selection is provided.
    """
    template_ids = template_test_ids(template)
    if selected_test_ids is not None:
        active_ids = validate_active_test_ids(selected_test_ids)
    else:
        active_ids = [
            test_id
            for test_id in template_ids
            if (test_def := get_test_by_id(test_id)) and not test_def.get("deprecated")
        ]

    if selected_test_ids is not None and require_selected_within_template:
        template_active_ids = {
            test_id
            for test_id in template_ids
            if (test_def := get_test_by_id(test_id)) and not test_def.get("deprecated")
        }
        outside_template = [test_id for test_id in active_ids if test_id not in template_active_ids]
        if outside_template:
            raise TestSelectionError(
                "Selected test id(s) are not part of the chosen template: "
                f"{', '.join(outside_template)}"
            )

    test_defs = [
        (test_id, test_def)
        for test_id in active_ids
        if (test_def := get_test_by_id(test_id)) and not test_def.get("deprecated")
    ]
    if not test_defs:
        raise TestSelectionError("Select at least one active test")
    return test_defs


def _metadata_dict(metadata: Any) -> dict[str, Any]:
    if isinstance(metadata, dict):
        return dict(metadata)
    if metadata is None:
        return {}
    return {"request_metadata": metadata}


def _add_selection_metadata(
    metadata: dict[str, Any],
    *,
    test_ids: Iterable[str],
    selected_test_ids: list[str] | None,
    selection_source: str,
) -> dict[str, Any]:
    merged = dict(metadata)
    test_id_list = list(test_ids)
    if selected_test_ids is not None:
        merged["selected_test_ids"] = test_id_list
        merged["selection_source"] = selection_source
    merged["selected_test_count"] = len(test_id_list)
    return merged


async def provision_test_run(
    db: AsyncSession,
    *,
    device: Device,
    template: TestTemplate,
    engineer_id: str,
    connection_scenario: str = "direct",
    selected_test_ids: list[str] | None = None,
    metadata: Any = None,
    selection_source: str = "template",
    agent_id: str | None = None,
    status: TestRunStatus = TestRunStatus.PENDING,
    include_selection_metadata: bool = True,
    apply_scenario_routing: bool = True,
    require_selected_within_template: bool = False,
) -> ProvisionedTestRun:
    """Create a TestRun and pending TestResult rows in the current session."""
    normalized_scenario = normalize_connection_scenario(connection_scenario)
    test_defs = resolve_test_run_selection(
        template,
        selected_test_ids,
        require_selected_within_template=require_selected_within_template,
    )
    test_ids = [test_id for test_id, _ in test_defs]
    run_metadata = _metadata_dict(metadata)
    effective_selection_source = selection_source if selected_test_ids is not None else "template"
    if include_selection_metadata:
        run_metadata = _add_selection_metadata(
            run_metadata,
            test_ids=test_ids,
            selected_test_ids=selected_test_ids,
            selection_source=effective_selection_source,
        )

    test_run = TestRun(
        device_id=device.id,
        template_id=template.id,
        engineer_id=engineer_id,
        project_id=device.project_id,
        agent_id=agent_id,
        connection_scenario=normalized_scenario,
        total_tests=len(test_defs),
        status=status,
        run_metadata=run_metadata or None,
    )
    db.add(test_run)
    await db.flush()

    for test_id, test_def in test_defs:
        tier = test_def["tier"]
        if apply_scenario_routing:
            tier = get_scenario_routing_decision(
                test_id,
                tier,
                normalized_scenario,
            ).tier

        result = TestResult(
            test_run_id=test_run.id,
            test_id=test_id,
            test_name=test_def["name"],
            tier=TestTier(tier),
            tool=test_def.get("tool"),
            verdict=TestVerdict.PENDING,
            is_essential="yes" if test_def.get("is_essential") else "no",
            compliance_map=test_def.get("compliance_map", []),
        )
        manual_note = (
            get_manual_routing_note(test_id, normalized_scenario)
            if apply_scenario_routing
            else None
        )
        if manual_note:
            result.comment = manual_note
        db.add(result)

    await db.flush()
    return ProvisionedTestRun(
        run=test_run,
        test_ids=test_ids,
        selection_source=effective_selection_source,
    )
