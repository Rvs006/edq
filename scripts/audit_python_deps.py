"""Audit backend Python dependencies with EDQ's documented policy exceptions."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_REQUIREMENTS = REPO_ROOT / "server" / "backend" / "requirements.txt"

ACCEPTED_VULNERABILITIES = {
    # CVE-2025-45768 / PYSEC-2025-183 is a disputed PyJWT weak-key advisory.
    # PyJWT has no fixed release for it; EDQ mitigates the risk by rejecting
    # short or reused HS256 signing secrets during app configuration startup.
    "PYSEC-2025-183": (
        "Disputed PyJWT weak-key advisory; EDQ enforces distinct JWT signing "
        "secrets of at least 32 characters in server/backend/app/config.py."
    ),
    "CVE-2025-45768": (
        "Alias for PYSEC-2025-183; retained so the audit stays stable if the "
        "vulnerability service reports the CVE ID instead of the PYSEC ID."
    ),
}


def main() -> int:
    try:
        import pip_audit  # noqa: F401
    except ModuleNotFoundError:
        print(
            "pip-audit is not installed. Install backend dev requirements first: "
            "python -m pip install -r server/backend/requirements-dev.txt",
            file=sys.stderr,
        )
        return 1

    command = [
        sys.executable,
        "-m",
        "pip_audit",
        "-r",
        str(BACKEND_REQUIREMENTS),
        "--progress-spinner",
        "off",
    ]
    for vuln_id in ACCEPTED_VULNERABILITIES:
        command.extend(["--ignore-vuln", vuln_id])

    print("Running backend Python dependency audit")
    for vuln_id, reason in ACCEPTED_VULNERABILITIES.items():
        print(f"Ignoring accepted advisory {vuln_id}: {reason}")

    return subprocess.call(command, cwd=REPO_ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
