"""Tests for shared collection helpers."""

from app.utils.collections import ordered_unique


def test_ordered_unique_collapses_duplicates_in_first_seen_order():
    assert ordered_unique(["U03", "U01", "U03", "U02", "U01", "U02"]) == [
        "U03",
        "U01",
        "U02",
    ]
