from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

REPORT_VERSION = "1.0.0"
SCHEMA_PATH = "reports/schemas/audit-report.schema.json"
SEVERITY_LEVELS = ("critical", "high", "medium", "low", "info")
CONFIDENCE_LEVELS = ("high", "medium", "low")
CLAIM_STATUSES = ("verified", "inferred", "unverified", "disproven", "not_applicable")
ROUTE_AUTH_CLASSES = ("public", "authenticated", "role_protected", "alternate_auth")
EVIDENCE_METHODS = ("pattern", "ast", "inventory", "manual", "manual_example")
SEVERITY_RANK = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}
REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "scripts" / "audit" / "audit_config.json"


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def normalize_path(value: str | Path) -> str:
    path = Path(value)
    if path.is_absolute():
        try:
            path = path.relative_to(REPO_ROOT)
        except ValueError:
            return str(path).replace("\\", "/")
    return str(path).replace("\\", "/")


def is_relative_repo_path(value: str) -> bool:
    normalized = normalize_path(value)
    return not Path(normalized).is_absolute() and ":" not in normalized[:3]


def is_excluded(rel_path: str, exclusions: list[str]) -> bool:
    rel = normalize_path(rel_path).strip("./")
    parts = [part for part in rel.split("/") if part]
    for raw_rule in exclusions:
        rule = raw_rule.strip("/").replace("\\", "/")
        if not rule:
            continue
        if "/" in rule:
            if rel == rule or rel.startswith(f"{rule}/"):
                return True
            continue
        if rule in parts:
            return True
    return False


def is_test_path(rel_path: str) -> bool:
    rel = normalize_path(rel_path)
    return (
        rel.startswith("server/backend/tests/")
        or "/__tests__/" in rel
        or "/test/" in rel
        or ".test." in rel
        or ".spec." in rel
    )


def is_test_module_path(rel_path: str) -> bool:
    rel = normalize_path(rel_path)
    if rel.startswith("server/backend/tests/"):
        return Path(rel).name.startswith("test_") and rel.endswith(".py")
    return "/__tests__/" in rel or ".test." in rel or ".spec." in rel


def finding_id(rule_id: str, file_path: str, line_start: int, line_end: int) -> str:
    seed = f"{rule_id}:{normalize_path(file_path)}:{line_start}:{line_end}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10].upper()
    return f"AUD-{digest}"


def line_snippet(lines: list[str], line_start: int, line_end: int | None = None, max_lines: int = 3) -> str:
    if line_start <= 0:
        return ""
    final_line = line_end or line_start
    window_end = min(final_line, line_start + max_lines - 1)
    selected = lines[line_start - 1:window_end]
    return "\n".join(selected).rstrip()


def zero_counts(keys: tuple[str, ...] | list[str]) -> dict[str, int]:
    return {key: 0 for key in keys}


def build_summary(
    findings: list[dict[str, Any]],
    manual_review_required: list[dict[str, Any]],
    forbidden_phrases_detected: list[str],
) -> dict[str, Any]:
    by_severity = Counter(finding["severity"] for finding in findings)
    by_confidence = Counter(finding["confidence"] for finding in findings)
    by_claim_status = Counter(finding["claim_status"] for finding in findings)
    by_category = Counter(finding["category"] for finding in findings)
    intentional_pattern_count = sum(1 for finding in findings if finding.get("intentional_pattern"))

    summary = {
        "total_findings": len(findings),
        "by_severity": zero_counts(SEVERITY_LEVELS),
        "by_confidence": zero_counts(CONFIDENCE_LEVELS),
        "by_claim_status": zero_counts(CLAIM_STATUSES),
        "by_category": dict(sorted(by_category.items())),
        "intentional_pattern_count": intentional_pattern_count,
        "manual_review_required_count": len(manual_review_required),
        "verified_fact_count": by_claim_status.get("verified", 0),
        "inferred_risk_count": by_claim_status.get("inferred", 0),
        "unverified_claim_count": by_claim_status.get("unverified", 0),
        "forbidden_phrases_detected": sorted(set(forbidden_phrases_detected)),
    }
    for level in SEVERITY_LEVELS:
        summary["by_severity"][level] = by_severity.get(level, 0)
    for level in CONFIDENCE_LEVELS:
        summary["by_confidence"][level] = by_confidence.get(level, 0)
    for status in CLAIM_STATUSES:
        summary["by_claim_status"][status] = by_claim_status.get(status, 0)
    return summary


def detect_forbidden_phrases(text: str, forbidden_phrases: list[str]) -> list[str]:
    lower_text = text.lower()
    return sorted({phrase for phrase in forbidden_phrases if phrase.lower() in lower_text})


def severity_blocks(severity: str, threshold: str) -> bool:
    return SEVERITY_RANK[severity] >= SEVERITY_RANK[threshold]


def validate_report_data(report: dict[str, Any], forbidden_phrases: list[str]) -> list[str]:
    errors: list[str] = []
    top_level_required = [
        "$schema",
        "report_version",
        "metadata",
        "summary",
        "inventories",
        "limitations",
        "manual_review_required",
        "findings",
    ]
    for key in top_level_required:
        if key not in report:
            errors.append(f"Missing top-level key: {key}")

    if report.get("$schema") != SCHEMA_PATH:
        errors.append(f"Unexpected $schema value: {report.get('$schema')}")
    if report.get("report_version") != REPORT_VERSION:
        errors.append(f"Unexpected report_version: {report.get('report_version')}")

    metadata = report.get("metadata", {})
    metadata_required = [
        "repository_name",
        "generated_at",
        "scan_scope",
        "excluded_paths",
        "generator",
        "commands",
    ]
    for key in metadata_required:
        if key not in metadata:
            errors.append(f"Missing metadata key: {key}")
    if metadata.get("scan_scope") not in {"full", "changed", "example"}:
        errors.append(f"Invalid metadata.scan_scope: {metadata.get('scan_scope')}")

    findings = report.get("findings", [])
    if not isinstance(findings, list):
        errors.append("findings must be a list")
        findings = []

    finding_required = [
        "id",
        "rule_id",
        "category",
        "severity",
        "confidence",
        "claim_status",
        "title",
        "description",
        "intentional_pattern",
        "evidence",
        "verification_steps",
        "false_positive_notes",
        "remediation",
    ]
    evidence_required = [
        "file_path",
        "line_start",
        "line_end",
        "snippet",
        "collection_method",
    ]
    for finding in findings:
        for key in finding_required:
            if key not in finding:
                errors.append(f"Finding {finding.get('id', '<missing-id>')} missing key: {key}")
        if finding.get("severity") not in SEVERITY_LEVELS:
            errors.append(f"Finding {finding.get('id', '<missing-id>')} invalid severity")
        if finding.get("confidence") not in CONFIDENCE_LEVELS:
            errors.append(f"Finding {finding.get('id', '<missing-id>')} invalid confidence")
        if finding.get("claim_status") not in CLAIM_STATUSES:
            errors.append(f"Finding {finding.get('id', '<missing-id>')} invalid claim_status")
        evidence = finding.get("evidence", [])
        if not evidence:
            errors.append(f"Finding {finding.get('id', '<missing-id>')} has no evidence")
        for item in evidence:
            for key in evidence_required:
                if key not in item:
                    errors.append(f"Finding {finding.get('id', '<missing-id>')} evidence missing key: {key}")
            file_path = item.get("file_path", "")
            if not is_relative_repo_path(file_path):
                errors.append(f"Finding {finding.get('id', '<missing-id>')} evidence path must be repo-relative: {file_path}")
            if item.get("collection_method") not in EVIDENCE_METHODS:
                errors.append(
                    f"Finding {finding.get('id', '<missing-id>')} invalid evidence collection_method: {item.get('collection_method')}"
                )

    manual_review_required = report.get("manual_review_required", [])
    if not isinstance(manual_review_required, list):
        errors.append("manual_review_required must be a list")
        manual_review_required = []
    manual_review_keys = ["id", "topic", "reason", "recommended_verification"]
    for item in manual_review_required:
        for key in manual_review_keys:
            if key not in item:
                errors.append(f"manual_review_required item missing key: {key}")

    summary = report.get("summary", {})
    recomputed = build_summary(
        findings=findings,
        manual_review_required=manual_review_required,
        forbidden_phrases_detected=summary.get("forbidden_phrases_detected", []),
    )
    summary_scalar_keys = [
        "total_findings",
        "intentional_pattern_count",
        "manual_review_required_count",
        "verified_fact_count",
        "inferred_risk_count",
        "unverified_claim_count",
    ]
    for key in summary_scalar_keys:
        if summary.get(key) != recomputed.get(key):
            errors.append(f"summary.{key} mismatch: expected {recomputed.get(key)}, got {summary.get(key)}")
    for key in ("by_severity", "by_confidence", "by_claim_status", "by_category"):
        if summary.get(key) != recomputed.get(key):
            errors.append(f"summary.{key} mismatch")

    forbidden_detected = summary.get("forbidden_phrases_detected", [])
    if not isinstance(forbidden_detected, list):
        errors.append("summary.forbidden_phrases_detected must be a list")
    for phrase in forbidden_detected:
        if phrase not in forbidden_phrases:
            errors.append(f"summary.forbidden_phrases_detected contains unknown phrase: {phrase}")

    limitations = report.get("limitations", [])
    if not isinstance(limitations, list) or not all(isinstance(item, str) for item in limitations):
        errors.append("limitations must be a list of strings")

    inventories = report.get("inventories", {})
    for key in ("route_surface", "tests", "logging", "scan_stats"):
        if key not in inventories:
            errors.append(f"Missing inventories.{key}")

    return errors