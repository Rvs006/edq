"""Collection helpers shared across backend modules."""

from collections.abc import Iterable
from typing import Hashable, TypeVar

T = TypeVar("T", bound=Hashable)


def ordered_unique(values: Iterable[T] | None) -> list[T]:
    """Return unique values in first-seen order."""
    seen: set[T] = set()
    ordered: list[T] = []
    for value in values or []:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered
