from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from common import CONFIG_PATH, REPO_ROOT, detect_forbidden_phrases, load_config, normalize_path, validate_report_data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate evidence audit report structure")
    parser.add_argument("--report", required=True)
    parser.add_argument("--markdown")
    parser.add_argument("--schema", default="reports/schemas/audit-report.schema.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config()
    schema_path = REPO_ROOT / normalize_path(args.schema)
    if not schema_path.exists():
        print(f"ERROR: schema file not found: {schema_path}", file=sys.stderr)
        return 1

    report_path = REPO_ROOT / normalize_path(args.report)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    errors = validate_report_data(report, config["forbidden_summary_phrases"])

    if args.markdown:
        markdown_path = REPO_ROOT / normalize_path(args.markdown)
        markdown = markdown_path.read_text(encoding="utf-8")
        forbidden = detect_forbidden_phrases(markdown, config["forbidden_summary_phrases"])
        errors.extend(f"Markdown contains forbidden phrase: {phrase}" for phrase in forbidden)

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "report": normalize_path(report_path.relative_to(REPO_ROOT)),
                "schema": normalize_path(schema_path.relative_to(REPO_ROOT)),
                "status": "valid",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())