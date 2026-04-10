"""One-shot data migration from a legacy SQLite database into PostgreSQL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sqlalchemy import MetaData, create_engine, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql.sqltypes import JSON

from app.config import settings
from app.models.database import Base, _import_all_models
from app.models.device import AddressingMode, DeviceCategory, DeviceStatus
from app.models.network_scan import NetworkScanStatus
from app.models.scan_schedule import ScheduleFrequency
from app.models.test_result import TestTier, TestVerdict
from app.models.test_run import LEGACY_TEST_RUN_STATUS_ALIASES, TestRunStatus, TestRunVerdict
from app.models.user import UserRole

_ENUM_ALIASES: dict[object, dict[str, str]] = {
    AddressingMode: {},
    DeviceCategory: {},
    DeviceStatus: {},
    NetworkScanStatus: {},
    ScheduleFrequency: {},
    TestRunStatus: LEGACY_TEST_RUN_STATUS_ALIASES,
    TestRunVerdict: {},
    TestTier: {},
    TestVerdict: {},
    UserRole: {},
}


def _to_sync_url(url: str) -> str:
    return url.replace("+aiosqlite", "").replace("+asyncpg", "")


def _coerce_value(column, value: Any) -> Any:
    if value is None:
        return None

    enum_class = getattr(column.type, "enum_class", None)
    if enum_class is not None and isinstance(value, str):
        aliases = _ENUM_ALIASES.get(enum_class, {})
        if value in aliases:
            return aliases[value]
        for member in enum_class:
            if value == member.name or value == member.value:
                return member.value

    if isinstance(column.type, (JSON, JSONB)) and isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    return value


def _truncate_target(connection) -> None:
    for table in reversed(Base.metadata.sorted_tables):
        connection.execute(text(f'TRUNCATE TABLE "{table.name}" RESTART IDENTITY CASCADE'))


def migrate(source_url: str, target_url: str, *, truncate_target: bool = True) -> dict[str, int]:
    _import_all_models()

    source_engine = create_engine(source_url)
    target_engine = create_engine(target_url)
    source_metadata = MetaData()
    source_metadata.reflect(bind=source_engine)
    counts: dict[str, int] = {}

    try:
        with source_engine.connect() as source_connection, target_engine.begin() as target_connection:
            if truncate_target:
                _truncate_target(target_connection)

            for table in Base.metadata.sorted_tables:
                source_table = source_metadata.tables.get(table.name)
                if source_table is None:
                    counts[table.name] = 0
                    continue

                rows = source_connection.execute(select(source_table)).mappings().all()
                if not rows:
                    counts[table.name] = 0
                    continue

                payload: list[dict[str, Any]] = []
                target_columns = {column.name: column for column in table.columns}
                for row in rows:
                    item: dict[str, Any] = {}
                    for column_name, column in target_columns.items():
                        if column_name not in row:
                            continue
                        item[column_name] = _coerce_value(column, row[column_name])
                    payload.append(item)

                target_connection.execute(table.insert(), payload)
                counts[table.name] = len(payload)

        return counts
    finally:
        source_engine.dispose()
        target_engine.dispose()


def main() -> int:
    default_source = Path("data/edq.db").resolve()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-url",
        default=f"sqlite:///{default_source.as_posix()}",
        help="SQLAlchemy URL for the legacy SQLite database",
    )
    parser.add_argument(
        "--target-url",
        default=_to_sync_url(settings.DATABASE_URL),
        help="SQLAlchemy URL for the target PostgreSQL database",
    )
    parser.add_argument(
        "--no-truncate-target",
        action="store_true",
        help="Append into the target database instead of truncating it first",
    )
    args = parser.parse_args()

    counts = migrate(
        args.source_url,
        args.target_url,
        truncate_target=not args.no_truncate_target,
    )
    total_rows = sum(counts.values())
    print(f"Migrated {total_rows} rows from {args.source_url} to {args.target_url}")
    for table_name, count in counts.items():
        print(f"  {table_name}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
