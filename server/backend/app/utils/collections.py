"""Small collection helpers shared across backend routes."""

from collections.abc import Hashable, Iterable
from typing import TypeVar

T = TypeVar("T", bound=Hashable)


def dedupe_preserving_order(items: Iterable[T]) -> list[T]:
    """Return the first occurrence of each item while preserving input order."""
    return list(dict.fromkeys(items))
