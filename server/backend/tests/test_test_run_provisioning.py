import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.models.test_result import TestResult, TestTier, TestVerdict
from app.models.test_template import TestTemplate
from app.services.test_run_provisioning import (
    provision_test_run,
    resolve_test_run_selection,
)
from app.services.test_selection import TestSelectionError


@pytest.mark.asyncio
async def test_provision_test_run_creates_run_results_and_selection_metadata(
    db_session: AsyncSession,
):
    device = Device(ip_address="192.168.77.10", category="unknown", status="discovered")
    template = TestTemplate(
        name="Provisioning Template",
        test_ids=["U01", "U02", "U03"],
        version="1.0",
    )
    db_session.add_all([device, template])
    await db_session.flush()

    provisioned = await provision_test_run(
        db_session,
        device=device,
        template=template,
        engineer_id="engineer-1",
        selected_test_ids=["U03", "U01", "U03"],
        metadata={"source": "unit"},
        selection_source="explicit",
        require_selected_within_template=True,
    )

    assert provisioned.test_ids == ["U03", "U01"]
    assert provisioned.selection_source == "explicit"
    assert provisioned.run.total_tests == 2
    assert provisioned.run.run_metadata == {
        "source": "unit",
        "selected_test_ids": ["U03", "U01"],
        "selection_source": "explicit",
        "selected_test_count": 2,
    }

    result = await db_session.execute(
        select(TestResult).where(TestResult.test_run_id == provisioned.run.id)
    )
    results = {row.test_id: row for row in result.scalars().all()}
    assert set(results) == {"U01", "U03"}
    assert all(row.verdict == TestVerdict.PENDING for row in results.values())
    assert results["U03"].tier == TestTier.AUTOMATIC


def test_resolve_test_run_selection_rejects_ids_outside_template():
    template = TestTemplate(
        name="Small Template",
        test_ids=["U01"],
        version="1.0",
    )

    with pytest.raises(TestSelectionError, match="not part of the chosen template"):
        resolve_test_run_selection(
            template,
            ["U01", "U02"],
            require_selected_within_template=True,
        )


def test_resolve_test_run_selection_filters_deprecated_template_ids():
    template = TestTemplate(
        name="Legacy Template",
        test_ids=["U01", "U07", "U31", "U34"],
        version="1.0",
    )

    selected = resolve_test_run_selection(template)

    assert [test_id for test_id, _ in selected] == ["U01"]


def test_resolve_test_run_selection_rejects_explicit_deprecated_ids():
    template = TestTemplate(
        name="Legacy Template",
        test_ids=["U01", "U07", "U31", "U34"],
        version="1.0",
    )

    with pytest.raises(TestSelectionError, match="Unsupported or deprecated"):
        resolve_test_run_selection(template, ["U07", "U31", "U34"])
