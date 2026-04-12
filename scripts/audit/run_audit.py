from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from common import (
    REPO_ROOT,
    REPORT_VERSION,
    ROUTE_AUTH_CLASSES,
    SCHEMA_PATH,
    SEVERITY_LEVELS,
    build_summary,
    detect_forbidden_phrases,
    finding_id,
    is_excluded,
    is_test_module_path,
    is_test_path,
    line_snippet,
    load_config,
    normalize_path,
    severity_blocks,
    validate_report_data,
)

SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx"}
ROUTE_METHODS = {"get", "post", "put", "delete", "patch", "options", "head"}
SEVERITY_ORDER = {name: index for index, name in enumerate(SEVERITY_LEVELS)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run evidence-based repo audit")
    parser.add_argument("--scope", choices=("full", "changed"), default="full")
    parser.add_argument("--base-ref", default="HEAD~1")
    parser.add_argument("--output-dir", default="reports/audit/latest")
    parser.add_argument("--format", choices=("json", "markdown", "both"), default="both")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--strict-fail-on-severity", choices=SEVERITY_LEVELS, default="high")
    return parser.parse_args()


def repo_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def git_output(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def discover_files(config: dict[str, Any], suffixes: set[str]) -> list[str]:
    discovered: list[str] = []
    for root, dirnames, filenames in os.walk(REPO_ROOT):
        rel_root = normalize_path(Path(root).relative_to(REPO_ROOT))
        dirnames[:] = [
            dirname
            for dirname in dirnames
            if not is_excluded(
                normalize_path(Path(rel_root) / dirname if rel_root != "." else Path(dirname)),
                config["excluded_paths"],
            )
        ]
        for filename in filenames:
            rel_path = normalize_path(Path(rel_root) / filename if rel_root != "." else Path(filename))
            if is_excluded(rel_path, config["excluded_paths"]):
                continue
            if Path(filename).suffix.lower() not in suffixes:
                continue
            discovered.append(rel_path)
    return sorted(discovered)


def changed_files(config: dict[str, Any], base_ref: str) -> list[str]:
    candidates = [
        ["diff", "--name-only", f"{base_ref}...HEAD"],
        ["diff", "--name-only", base_ref],
    ]
    for command in candidates:
        output = git_output(*command)
        if output is None:
            continue
        files: list[str] = []
        for line in output.splitlines():
            rel_path = normalize_path(line)
            if not rel_path or is_excluded(rel_path, config["excluded_paths"]):
                continue
            if Path(rel_path).suffix.lower() in SOURCE_SUFFIXES:
                files.append(rel_path)
        return sorted(set(files))
    return []


def build_finding(
    *,
    rule_id: str,
    category: str,
    severity: str,
    confidence: str,
    claim_status: str,
    title: str,
    description: str,
    intentional_pattern: bool,
    file_path: str,
    line_start: int,
    line_end: int,
    snippet: str,
    collection_method: str,
    verification_steps: list[str],
    false_positive_notes: str,
    remediation: str,
) -> dict[str, Any]:
    return {
        "id": finding_id(rule_id, file_path, line_start, line_end),
        "rule_id": rule_id,
        "category": category,
        "severity": severity,
        "confidence": confidence,
        "claim_status": claim_status,
        "title": title,
        "description": description,
        "intentional_pattern": intentional_pattern,
        "evidence": [
            {
                "file_path": normalize_path(file_path),
                "line_start": line_start,
                "line_end": line_end,
                "snippet": snippet,
                "collection_method": collection_method,
            }
        ],
        "verification_steps": verification_steps,
        "false_positive_notes": false_positive_notes,
        "remediation": remediation,
    }


def function_name(node: ast.AST | None) -> str:
    if node is None:
        return ""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return function_name(node.func)
    return ""


def dependency_name(node: ast.AST | None) -> str:
    if node is None:
        return ""
    if isinstance(node, ast.Call):
        return f"{function_name(node.func)}(...)"
    return function_name(node)


def keyword_string(node: ast.Call, name: str) -> str | None:
    for keyword in node.keywords:
        if keyword.arg != name:
            continue
        value = keyword.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return value.value
    return None


def collect_ts_findings(rel_path: str) -> list[dict[str, Any]]:
    path = REPO_ROOT / rel_path
    text = path.read_text(encoding="utf-8", errors="replace")
    findings: list[dict[str, Any]] = []
    lines = text.splitlines()
    pattern = re.compile(r"\bas\s+any\b")
    for line_number, line in enumerate(lines, start=1):
        if not pattern.search(line):
            continue
        severity = "info" if is_test_path(rel_path) else "medium"
        findings.append(
            build_finding(
                rule_id="ts-any-cast",
                category="type_safety",
                severity=severity,
                confidence="high",
                claim_status="verified",
                title="Type-safety bypass via `as any`",
                description="`as any` bypasses TypeScript checking at this site. Presence is verified. Runtime impact still depends on caller data shape.",
                intentional_pattern=False,
                file_path=rel_path,
                line_start=line_number,
                line_end=line_number,
                snippet=line.rstrip(),
                collection_method="pattern",
                verification_steps=[
                    "Run `pnpm --dir frontend exec tsc --noEmit`.",
                    "Replace `as any` with a typed helper or `keyof` access where practical.",
                ],
                false_positive_notes="Test doubles may use `as any` intentionally. Treat test-file hits as lower risk than app-code hits.",
                remediation="Prefer explicit types, union narrowing, or typed property access helpers over `as any`.",
            )
        )
    return findings


def handler_has_logger_call(handler: ast.ExceptHandler) -> bool:
    for node in ast.walk(handler):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "logger":
                return True
    return False


def handler_has_raise(handler: ast.ExceptHandler) -> bool:
    return any(isinstance(node, ast.Raise) for node in ast.walk(handler))


def module_level_task_assignments(tree: ast.Module) -> list[tuple[str, int]]:
    assignments: list[tuple[str, int]] = []
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target = node.target.id
            annotation = ast.unparse(node.annotation)
            if target.endswith("_task") and "Task" in annotation:
                assignments.append((target, node.lineno))
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.endswith("_task"):
                    if isinstance(node.value, ast.Constant) and node.value.value is None:
                        assignments.append((target.id, node.lineno))
    return assignments


def collect_python_findings(rel_path: str) -> tuple[list[dict[str, Any]], Counter]:
    path = REPO_ROOT / rel_path
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    tree = ast.parse(text, filename=rel_path)
    findings: list[dict[str, Any]] = []
    metrics: Counter = Counter()
    metrics["logger_exception_call_count"] = len(re.findall(r"\blogger\.exception\s*\(", text))

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
            line_number = getattr(node, "lineno", 1)
            runtime_path = rel_path.startswith("server/backend/app/")
            findings.append(
                build_finding(
                    rule_id="python-print-call",
                    category="runtime_logging",
                    severity="low" if runtime_path else "info",
                    confidence="high",
                    claim_status="verified",
                    title="Console `print()` call present",
                    description="Direct `print()` exists at this location. Presence is verified. Operational risk depends on whether file runs in production runtime.",
                    intentional_pattern=not runtime_path,
                    file_path=rel_path,
                    line_start=line_number,
                    line_end=line_number,
                    snippet=line_snippet(lines, line_number),
                    collection_method="ast",
                    verification_steps=[
                        "Confirm whether this file executes in production runtime or only in setup/migration paths.",
                        "Prefer structured logging where operational visibility matters.",
                    ],
                    false_positive_notes="Setup and migration scripts may intentionally print human-readable progress.",
                    remediation="Use structured logging in runtime paths. Keep script-only prints only when explicitly desired.",
                )
            )
            metrics["print_call_count"] += 1

        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "text":
            line_number = getattr(node, "lineno", 1)
            findings.append(
                build_finding(
                    rule_id="python-raw-sql-text",
                    category="sql_usage",
                    severity="low",
                    confidence="high",
                    claim_status="verified",
                    title="Raw SQL `text(...)` usage present",
                    description="SQLAlchemy `text(...)` appears here. Presence is verified. Injection risk is not inferred automatically without data-flow review.",
                    intentional_pattern=False,
                    file_path=rel_path,
                    line_start=line_number,
                    line_end=line_number,
                    snippet=line_snippet(lines, line_number),
                    collection_method="ast",
                    verification_steps=[
                        "Review whether user-controlled values can reach this `text(...)` expression.",
                        "Add parameter-binding or injection tests before labeling this site vulnerable.",
                    ],
                    false_positive_notes="Health checks and schema reconciliation often use fixed raw SQL safely.",
                    remediation="Prefer ORM/query-builder APIs when practical. If raw SQL remains, document trusted inputs and parameterization.",
                )
            )
            metrics["raw_sql_text_count"] += 1

        if not isinstance(node, ast.ExceptHandler):
            continue
        is_exception = isinstance(node.type, ast.Name) and node.type.id == "Exception"
        if isinstance(node.type, ast.Tuple):
            is_exception = any(isinstance(item, ast.Name) and item.id == "Exception" for item in node.type.elts)
        if not is_exception:
            continue

        line_number = getattr(node, "lineno", 1)
        handler_snippet = line_snippet(lines, line_number, getattr(node, "end_lineno", line_number))
        findings.append(
            build_finding(
                rule_id="python-bare-except",
                category="exception_handling",
                severity="low",
                confidence="high",
                claim_status="verified",
                title="Broad `except Exception` handler present",
                description="Broad exception capture is present at this site. Presence is verified. Safety depends on logging, fallback semantics, and caller expectations.",
                intentional_pattern=False,
                file_path=rel_path,
                line_start=line_number,
                line_end=getattr(node, "end_lineno", line_number),
                snippet=handler_snippet,
                collection_method="ast",
                verification_steps=[
                    "Inspect handler body for structured logging, safe fallback behavior, and re-raise semantics.",
                    "Add targeted failure-path tests if this code is security-sensitive or user-facing.",
                ],
                false_positive_notes="Health checks, cleanup code, and framework boundaries sometimes intentionally catch broad exceptions.",
                remediation="Narrow exception types where practical or pair broad catch with explicit logging and safe fallback semantics.",
            )
        )
        metrics["bare_except_count"] += 1
        if handler_has_logger_call(node):
            metrics["logged_bare_except_count"] += 1

        pass_only = all(isinstance(item, ast.Pass) for item in node.body)
        no_log = not handler_has_logger_call(node)
        no_raise = not handler_has_raise(node)
        simple_fallback = len(node.body) <= 2 and all(
            isinstance(item, (ast.Pass, ast.Assign, ast.AnnAssign, ast.Return, ast.Expr))
            for item in node.body
        )

        if pass_only and no_log and no_raise:
            findings.append(
                build_finding(
                    rule_id="python-except-pass",
                    category="exception_handling",
                    severity="medium",
                    confidence="high",
                    claim_status="verified",
                    title="Exception swallowed with `pass`",
                    description="Handler drops exception with `pass` and no local logging or re-raise. Presence is verified.",
                    intentional_pattern=False,
                    file_path=rel_path,
                    line_start=line_number,
                    line_end=getattr(node, "end_lineno", line_number),
                    snippet=handler_snippet,
                    collection_method="ast",
                    verification_steps=[
                        "Inspect caller behavior to confirm silent failure is acceptable.",
                        "Add logging or explicit documentation if silent cleanup is intentional.",
                    ],
                    false_positive_notes="Best-effort cleanup paths sometimes intentionally ignore kill/cancel failures.",
                    remediation="Log or surface failure context unless silent cleanup is explicitly intended and documented.",
                )
            )
            metrics["except_pass_count"] += 1
        elif simple_fallback and no_log and no_raise:
            findings.append(
                build_finding(
                    rule_id="python-fallback-without-log",
                    category="exception_handling",
                    severity="low",
                    confidence="high",
                    claim_status="verified",
                    title="Exception converted to fallback without logging",
                    description="Handler converts broad exception to fallback result with no local logging or re-raise. Presence is verified.",
                    intentional_pattern=False,
                    file_path=rel_path,
                    line_start=line_number,
                    line_end=getattr(node, "end_lineno", line_number),
                    snippet=handler_snippet,
                    collection_method="ast",
                    verification_steps=[
                        "Review whether fallback value can mask operational failures.",
                        "Add targeted tests for fallback behavior if code is user-facing or security-sensitive.",
                    ],
                    false_positive_notes="Helpers such as password comparison wrappers may intentionally return safe booleans instead of raising.",
                    remediation="Prefer explicit logging or narrower exception handling when fallback can hide actionable failures.",
                )
            )
            metrics["fallback_without_log_count"] += 1

    for variable_name, line_number in module_level_task_assignments(tree):
        findings.append(
            build_finding(
                rule_id="python-global-task-state",
                category="background_tasks",
                severity="low",
                confidence="high",
                claim_status="verified",
                title="Module-level background task singleton state",
                description="Module-level task handle exists here. Presence is verified. This is often intentional for lifecycle control and should not be auto-labeled a bug.",
                intentional_pattern=True,
                file_path=rel_path,
                line_start=line_number,
                line_end=line_number,
                snippet=line_snippet(lines, line_number),
                collection_method="ast",
                verification_steps=[
                    "Confirm matching start/stop guards exist and are covered by tests.",
                    "Review cancellation and restart behavior during shutdown/startup.",
                ],
                false_positive_notes="Background schedulers commonly use a singleton task handle to prevent duplicate loops.",
                remediation="Document lifecycle semantics and keep null/done guards around task start-stop paths.",
            )
        )
        metrics["global_task_state_count"] += 1

    return findings, metrics


def route_prefix_from_module(tree: ast.Module) -> str:
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "router" for target in node.targets):
            continue
        if not isinstance(node.value, ast.Call) or function_name(node.value.func) != "APIRouter":
            continue
        return keyword_string(node.value, "prefix") or ""
    return ""


def parameter_bindings(function_node: ast.AST) -> list[tuple[str, ast.AST]]:
    if not isinstance(function_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return []
    bindings: list[tuple[str, ast.AST]] = []
    args = list(function_node.args.posonlyargs) + list(function_node.args.args)
    defaults = [None] * (len(args) - len(function_node.args.defaults)) + list(function_node.args.defaults)
    for arg, default in zip(args, defaults):
        if default is not None:
            bindings.append((arg.arg, default))
    for arg, default in zip(function_node.args.kwonlyargs, function_node.args.kw_defaults):
        if default is not None:
            bindings.append((arg.arg, default))
    return bindings


def describe_auth_binding(binding: ast.AST) -> str | None:
    if isinstance(binding, ast.Call) and function_name(binding.func) == "Depends":
        if binding.args:
            return f"Depends({dependency_name(binding.args[0])})"
        return "Depends(<unknown>)"
    if isinstance(binding, ast.Call) and function_name(binding.func) == "Header":
        alias = keyword_string(binding, "alias")
        if alias:
            return f"Header(alias={alias})"
        return "Header(...)"
    return None


def decorator_dependencies(decorator: ast.Call) -> list[str]:
    evidence: list[str] = []
    for keyword in decorator.keywords:
        if keyword.arg != "dependencies" or not isinstance(keyword.value, ast.List):
            continue
        for item in keyword.value.elts:
            binding = describe_auth_binding(item)
            if binding:
                evidence.append(binding)
    return evidence


def classify_route(function_node: ast.AST, decorator: ast.Call, function_source: str) -> tuple[str, list[str]]:
    evidence: list[str] = []
    for _, default in parameter_bindings(function_node):
        binding = describe_auth_binding(default)
        if binding:
            evidence.append(binding)
    evidence.extend(decorator_dependencies(decorator))
    if "X-Agent-Key" in function_source:
        evidence.append("Body checks X-Agent-Key")
    if "METRICS_API_KEY" in function_source or "Authorization" in function_source:
        evidence.append("Body checks Authorization or METRICS_API_KEY")

    if any("require_role" in item for item in evidence):
        return "role_protected", sorted(set(evidence))
    if any("get_current_active_user" in item or "get_current_user" in item for item in evidence):
        return "authenticated", sorted(set(evidence))
    if any("Header(" in item or "Body checks" in item for item in evidence):
        return "alternate_auth", sorted(set(evidence))
    return "public", sorted(set(evidence))


def build_route_inventory(config: dict[str, Any]) -> dict[str, Any]:
    routes: list[dict[str, Any]] = []
    counts = Counter()
    file_count = 0

    for route_root in config["route_roots"]:
        root_path = REPO_ROOT / route_root
        for file_path in sorted(root_path.glob("*.py")):
            rel_path = normalize_path(file_path.relative_to(REPO_ROOT))
            source = file_path.read_text(encoding="utf-8", errors="replace")
            lines = source.splitlines()
            tree = ast.parse(source, filename=rel_path)
            prefix = route_prefix_from_module(tree)
            file_count += 1

            for node in tree.body:
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for decorator in node.decorator_list:
                    if not isinstance(decorator, ast.Call):
                        continue
                    method = function_name(decorator.func)
                    if method not in ROUTE_METHODS:
                        continue
                    raw_path = ""
                    if decorator.args and isinstance(decorator.args[0], ast.Constant) and isinstance(decorator.args[0].value, str):
                        raw_path = decorator.args[0].value
                    full_path = f"{prefix}{raw_path}" if prefix or raw_path else "<dynamic>"
                    function_source = "\n".join(lines[node.lineno - 1:getattr(node, "end_lineno", node.lineno)])
                    auth_classification, auth_evidence = classify_route(node, decorator, function_source)
                    counts[auth_classification] += 1
                    routes.append(
                        {
                            "method": method.upper(),
                            "path": full_path or "<dynamic>",
                            "file_path": rel_path,
                            "line_start": node.lineno,
                            "handler": node.name,
                            "auth_classification": auth_classification,
                            "auth_evidence": auth_evidence,
                        }
                    )

    return {
        "route_file_count": file_count,
        "backend_route_count": len(routes),
        "counts_by_auth": {key: counts.get(key, 0) for key in ROUTE_AUTH_CLASSES},
        "routes": sorted(routes, key=lambda item: (item["file_path"], item["line_start"], item["method"])),
    }


def build_test_inventory(config: dict[str, Any]) -> dict[str, Any]:
    backend_tests: list[str] = []
    frontend_tests: list[str] = []

    for root in config["backend_test_roots"]:
        for file_path in sorted((REPO_ROOT / root).rglob("test_*.py")):
            rel_path = normalize_path(file_path.relative_to(REPO_ROOT))
            if not is_excluded(rel_path, config["excluded_paths"]):
                backend_tests.append(rel_path)

    for root in config["frontend_test_roots"]:
        for file_path in sorted((REPO_ROOT / root).rglob("*")):
            if not file_path.is_file():
                continue
            rel_path = normalize_path(file_path.relative_to(REPO_ROOT))
            if is_excluded(rel_path, config["excluded_paths"]):
                continue
            if is_test_module_path(rel_path):
                frontend_tests.append(rel_path)

    frontend_tests = sorted(set(frontend_tests))
    return {
        "backend_test_count": len(backend_tests),
        "frontend_test_count": len(frontend_tests),
        "backend_tests": backend_tests,
        "frontend_tests": frontend_tests,
    }


def build_manual_review_required() -> list[dict[str, Any]]:
    return [
        {
            "id": "MR-001",
            "topic": "N+1 query behavior",
            "reason": "Static pattern checks can confirm eager-loading usage but cannot prove absence of query explosion at runtime.",
            "recommended_verification": [
                "Enable SQL query logging for representative list/detail endpoints.",
                "Compare query counts for single-item and multi-item requests under tests.",
            ],
        },
        {
            "id": "MR-002",
            "topic": "SQL injection exploitability",
            "reason": "Presence of raw SQL helpers such as `text(...)` does not prove exploitable data flow.",
            "recommended_verification": [
                "Trace caller-controlled inputs into every raw SQL site.",
                "Add injection payload tests before labeling a site vulnerable.",
            ],
        },
        {
            "id": "MR-003",
            "topic": "Route-auth semantics",
            "reason": "Route inventory can classify auth patterns, but only request tests prove 401/403 behavior and edge-case enforcement.",
            "recommended_verification": [
                "Test public, authenticated, role-protected, and alternate-auth endpoints with live requests.",
                "Check inactive-user and wrong-role behavior for protected routes.",
            ],
        },
        {
            "id": "MR-004",
            "topic": "Background task lifecycle safety",
            "reason": "Singleton task handles are often intentional; startup, cancellation, and restart behavior still need runtime verification.",
            "recommended_verification": [
                "Exercise start-stop-restart flows under tests or local runs.",
                "Confirm duplicate loop prevention and graceful cancellation behavior.",
            ],
        },
    ]


def build_limitations(scope: str, changed: list[str]) -> list[str]:
    limitations = [
        "Automation proves code patterns and inventories, not exploitability, performance characteristics, or full runtime behavior.",
        "Dependency vulnerability status is not checked by package-audit tools in this report.",
        "Route inventory is structural; HTTP response semantics still require request-level tests.",
    ]
    if scope == "changed":
        limitations.append(
            f"Finding scan scope is limited to changed source files ({len(changed)} file(s)); inventories still cover full configured route and test roots."
        )
    return limitations


def markdown_table(rows: list[tuple[str, str]]) -> str:
    output = ["| Item | Value |", "| --- | --- |"]
    output.extend(f"| {item} | {value} |" for item, value in rows)
    return "\n".join(output)


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    metadata = report["metadata"]
    inventories = report["inventories"]
    findings = report["findings"]
    intentional = [finding for finding in findings if finding["intentional_pattern"]]

    lines: list[str] = [
        "# Evidence Audit Report",
        "",
        "## Executive summary",
        f"- Repository: `{metadata['repository_name']}`",
        f"- Generated at: `{metadata['generated_at']}`",
        f"- Scan scope: `{metadata['scan_scope']}`",
        f"- Total findings: `{summary['total_findings']}`",
        f"- Verified facts: `{summary['verified_fact_count']}`",
        f"- Manual review required items: `{summary['manual_review_required_count']}`",
        "",
        "## Scope and exclusions",
        f"- Excluded paths: `{', '.join(metadata['excluded_paths'])}`",
        f"- Finding-scope file count: `{inventories['scan_stats']['finding_scope_file_count']}`",
        f"- Route inventory count: `{inventories['route_surface']['backend_route_count']}`",
        f"- Backend test modules: `{inventories['tests']['backend_test_count']}`",
        f"- Frontend test modules: `{inventories['tests']['frontend_test_count']}`",
        "",
        "## Verification methods used",
        "- Regex/pattern search for TypeScript `as any` and broad summary guardrails.",
        "- Python AST inspection for exception handlers, `print()`, `text(...)`, route inventory, and module-level task state.",
        "- Filesystem inventory for test modules and excluded-path accounting.",
        "",
        "## Findings summary",
        "### By severity",
        markdown_table([(key, str(value)) for key, value in summary["by_severity"].items()]),
        "",
        "### By confidence",
        markdown_table([(key, str(value)) for key, value in summary["by_confidence"].items()]),
        "",
        "### By category",
        markdown_table([(key, str(value)) for key, value in summary["by_category"].items()]),
        "",
        "## Detailed findings",
    ]

    for finding in findings:
        evidence = finding["evidence"][0]
        lines.extend(
            [
                f"### {finding['id']} - {finding['title']}",
                f"- Rule: `{finding['rule_id']}`",
                f"- Category: `{finding['category']}`",
                f"- Severity: `{finding['severity']}`",
                f"- Confidence: `{finding['confidence']}`",
                f"- Claim status: `{finding['claim_status']}`",
                f"- Intentional pattern: `{str(finding['intentional_pattern']).lower()}`",
                f"- Description: {finding['description']}",
                f"- Evidence: `{evidence['file_path']}:{evidence['line_start']}-{evidence['line_end']}`",
                "",
                "```text",
                evidence["snippet"] or "<no snippet>",
                "```",
                "",
                "- Verification steps:",
            ]
        )
        lines.extend(f"  - {step}" for step in finding["verification_steps"])
        lines.extend(
            [
                f"- False-positive notes: {finding['false_positive_notes']}",
                f"- Remediation: {finding['remediation']}",
                "",
            ]
        )

    lines.extend(
        [
            "## Intentional / low-risk patterns",
            *(["- None automatically marked as intentional."] if not intentional else []),
        ]
    )
    for finding in intentional:
        evidence = finding["evidence"][0]
        lines.append(f"- `{finding['id']}` at `{evidence['file_path']}:{evidence['line_start']}` - {finding['title']}")

    lines.extend(
        [
            "",
            "## Not proven / manual review required",
        ]
    )
    for item in report["manual_review_required"]:
        lines.append(f"- `{item['id']}` {item['topic']}: {item['reason']}")
        for step in item["recommended_verification"]:
            lines.append(f"  - {step}")

    lines.extend(
        [
            "",
            "## False positives rejected",
            "- None rejected automatically. Reviewer should record rejected findings explicitly during manual review.",
            "",
            "## Reproduction / validation commands",
        ]
    )
    for command in metadata["commands"]:
        lines.append(f"- `{command}`")

    lines.extend(
        [
            "",
            "## Final assessment with limitations",
        ]
    )
    lines.extend(f"- {item}" for item in report["limitations"])
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    args = parse_args()
    config = load_config()
    output_dir = REPO_ROOT / normalize_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    finding_scope_files = discover_files(config, SOURCE_SUFFIXES)
    changed: list[str] = []
    if args.scope == "changed":
        changed = changed_files(config, args.base_ref)
        if changed:
            finding_scope_files = changed
        else:
            args.scope = "full"

    findings: list[dict[str, Any]] = []
    metrics: Counter = Counter()
    for rel_path in finding_scope_files:
        suffix = Path(rel_path).suffix.lower()
        if suffix in {".ts", ".tsx", ".js", ".jsx"}:
            findings.extend(collect_ts_findings(rel_path))
            continue
        if suffix == ".py":
            python_findings, python_metrics = collect_python_findings(rel_path)
            findings.extend(python_findings)
            metrics.update(python_metrics)

    findings.sort(
        key=lambda item: (
            SEVERITY_ORDER[item["severity"]],
            item["category"],
            item["evidence"][0]["file_path"],
            item["evidence"][0]["line_start"],
        )
    )

    route_inventory = build_route_inventory(config)
    test_inventory = build_test_inventory(config)
    manual_review_required = build_manual_review_required()
    limitations = build_limitations(args.scope, changed)

    metadata = {
        "repository_name": REPO_ROOT.name,
        "generated_at": repo_now(),
        "scan_scope": args.scope,
        "base_ref": args.base_ref,
        "changed_files": changed,
        "excluded_paths": config["excluded_paths"],
        "generator": {
            "name": "repo-audit",
            "version": REPORT_VERSION,
        },
        "commands": [
            " ".join(["python", "scripts/audit/run_audit.py", *sys.argv[1:]]) or "python scripts/audit/run_audit.py",
        ],
        "commit_sha": git_output("rev-parse", "HEAD"),
        "branch": git_output("rev-parse", "--abbrev-ref", "HEAD"),
    }

    report = {
        "$schema": SCHEMA_PATH,
        "report_version": REPORT_VERSION,
        "metadata": metadata,
        "summary": {},
        "inventories": {
            "route_surface": route_inventory,
            "tests": test_inventory,
            "logging": {
                "logger_exception_call_count": metrics.get("logger_exception_call_count", 0),
                "bare_except_count": metrics.get("bare_except_count", 0),
                "logged_bare_except_count": metrics.get("logged_bare_except_count", 0),
                "except_pass_count": metrics.get("except_pass_count", 0),
                "fallback_without_log_count": metrics.get("fallback_without_log_count", 0),
                "print_call_count": metrics.get("print_call_count", 0),
                "raw_sql_text_count": metrics.get("raw_sql_text_count", 0),
                "global_task_state_count": metrics.get("global_task_state_count", 0),
            },
            "scan_stats": {
                "finding_scope_file_count": len(finding_scope_files),
                "changed_file_count": len(changed),
            },
        },
        "limitations": limitations,
        "manual_review_required": manual_review_required,
        "findings": findings,
    }

    markdown = render_markdown({**report, "summary": build_summary(findings, manual_review_required, [])})
    forbidden = detect_forbidden_phrases(markdown, config["forbidden_summary_phrases"])
    report["summary"] = build_summary(findings, manual_review_required, forbidden)
    markdown = render_markdown(report)

    json_path = output_dir / "audit-report.json"
    markdown_path = output_dir / "audit-report.md"
    if args.format in {"json", "both"}:
        json_path.write_text(json.dumps(report, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    if args.format in {"markdown", "both"}:
        markdown_path.write_text(markdown, encoding="utf-8")

    errors = validate_report_data(report, config["forbidden_summary_phrases"])
    errors.extend(
        f"Markdown contains forbidden phrase: {phrase}"
        for phrase in detect_forbidden_phrases(markdown, config["forbidden_summary_phrases"])
    )
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2

    blocking_findings = [
        finding
        for finding in findings
        if finding["confidence"] == "high" and severity_blocks(finding["severity"], args.strict_fail_on_severity)
    ]
    print(
        json.dumps(
            {
                "json_report": normalize_path(json_path.relative_to(REPO_ROOT)),
                "markdown_report": normalize_path(markdown_path.relative_to(REPO_ROOT)),
                "finding_count": len(findings),
                "blocking_finding_count": len(blocking_findings),
            }
        )
    )
    if args.strict and blocking_findings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())