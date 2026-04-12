from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Emit compact GitHub job summary from audit report")
    parser.add_argument("--report", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    summary = report["summary"]
    route_surface = report["inventories"]["route_surface"]
    tests = report["inventories"]["tests"]

    print("# Audit summary")
    print("")
    print("| Item | Value |")
    print("| --- | --- |")
    print(f"| Total findings | {summary['total_findings']} |")
    print(f"| Verified facts | {summary['verified_fact_count']} |")
    print(f"| Manual review required | {summary['manual_review_required_count']} |")
    print(f"| High-confidence high+ findings | {summary['by_severity'].get('high', 0) + summary['by_severity'].get('critical', 0)} |")
    print(f"| Route inventory size | {route_surface['backend_route_count']} |")
    print(f"| Backend test modules | {tests['backend_test_count']} |")
    print(f"| Frontend test modules | {tests['frontend_test_count']} |")
    print("")
    print("## By severity")
    print("")
    for severity, count in summary["by_severity"].items():
        print(f"- `{severity}`: {count}")
    print("")
    print("## Verified vs inferred")
    print("")
    print(f"- `verified`: {summary['by_claim_status'].get('verified', 0)}")
    print(f"- `inferred`: {summary['by_claim_status'].get('inferred', 0)}")
    print(f"- `unverified`: {summary['by_claim_status'].get('unverified', 0)}")
    print("")
    print("## Route auth inventory")
    print("")
    for auth_class, count in route_surface["counts_by_auth"].items():
        print(f"- `{auth_class}`: {count}")
    print("")
    if summary["forbidden_phrases_detected"]:
        print("## Forbidden phrases detected")
        print("")
        for phrase in summary["forbidden_phrases_detected"]:
            print(f"- `{phrase}`")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())