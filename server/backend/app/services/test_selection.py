"""Helpers for validating selected universal test IDs."""

from __future__ import annotations

from app.services.test_library import get_active_tests
from app.utils.collections import ordered_unique


class TestSelectionError(ValueError):
    """Raised when a caller requests unsupported or deprecated tests."""


def get_active_test_id_set() -> set[str]:
    return {test["test_id"] for test in get_active_tests()}


def get_default_test_ids() -> list[str]:
    return [test["test_id"] for test in get_active_tests()]


def validate_active_test_ids(test_ids: list[str] | None, *, allow_empty: bool = False) -> list[str]:
    deduped = ordered_unique(test_ids or [])
    if not deduped and not allow_empty:
        raise TestSelectionError("Select at least one active test")

    active_ids = get_active_test_id_set()
    invalid = [test_id for test_id in deduped if test_id not in active_ids]
    if invalid:
        raise TestSelectionError(
            f"Unsupported or deprecated test id(s): {', '.join(invalid)}"
        )
    return deduped
