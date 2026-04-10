"""Helpers for SQLAlchemy enum persistence."""


def enum_values(enum_cls) -> list[str]:
    """Persist enum members by their public string values instead of member names."""
    return [str(member.value) for member in enum_cls]
