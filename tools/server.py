"""EDQ Tools Sidecar — REST API wrapper for security scanning tools."""

import base64
import os
import re
import shutil
import subprocess
import tempfile
import time

from typing import Tuple, Union

from flask import Flask, Response, jsonify, request

app = Flask(__name__)

ALLOWED_TOOLS = {
    "nmap": "nmap",
    "testssl": "testssl.sh",
    "ssh_audit": "ssh-audit",
    "hydra": "hydra",
    "nikto": "nikto",
}

IP_RE = re.compile(
    r"^("
    r"(\d{1,3}\.){3}\d{1,3}"
    r"|"
    r"[a-zA-Z0-9._-]{1,253}"
    r"|"
    r"[0-9a-fA-F:]{2,39}"
    r")$"
)

BLOCKED_ARGS = {"&&", "||", ";", "|", "`", "$", "(", ")", "{", "}", "<", ">", "\n", "\r"}


def _tool_available(binary: str) -> bool:
    return shutil.which(binary) is not None


def _check_tool_version(binary: str) -> bool:
    try:
        subprocess.run(
            [binary, "--version"],
            capture_output=True,
            timeout=10,
        )
        return True
    except Exception:
        return False


def _validate_target(target: str) -> str:
    target = target.strip()
    if not target or len(target) > 253:
        raise ValueError("Invalid target: empty or too long")
    if not IP_RE.match(target):
        raise ValueError(f"Invalid target format: {target}")
    return target


def _validate_args(args: list) -> list:
    sanitised = []
    for arg in args:
        arg = str(arg)
        for blocked in BLOCKED_ARGS:
            if blocked in arg:
                raise ValueError(f"Blocked character in argument: {blocked}")
        sanitised.append(arg)
    return sanitised


def _run_tool(cmd: list, timeout: int) -> dict:
    start = time.time()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            text=True,
        )
        duration = round(time.time() - start, 2)
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration_seconds": duration,
            "output_file": None,
        }
    except subprocess.TimeoutExpired:
        duration = round(time.time() - start, 2)
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": f"Command timed out after {timeout}s",
            "duration_seconds": duration,
            "output_file": None,
        }
    except Exception as e:
        duration = round(time.time() - start, 2)
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": str(e),
            "duration_seconds": duration,
            "output_file": None,
        }


def _parse_scan_request():
    data = request.get_json(force=True, silent=True)
    if not data:
        return None, None, None, ("Missing JSON body", 400)

    target = data.get("target")
    if not target:
        return None, None, None, ("Missing 'target' field", 400)

    try:
        target = _validate_target(target)
    except ValueError as e:
        return None, None, None, (str(e), 400)

    args = data.get("args", [])
    try:
        args = _validate_args(args)
    except ValueError as e:
        return None, None, None, (str(e), 400)

    try:
        timeout = min(int(data.get("timeout", 300)), 600)
    except (TypeError, ValueError):
        return None, None, None, ("'timeout' must be an integer", 400)

    return target, args, timeout, None


ESSENTIAL_TOOLS = {"nmap", "ssh_audit"}


@app.route("/health", methods=["GET"])
def health() -> Response:
    tools_status = {}
    for key, binary in ALLOWED_TOOLS.items():
        tools_status[key] = _tool_available(binary)

    overall = "healthy" if all(tools_status.get(k) for k in ESSENTIAL_TOOLS) else "degraded"
    return jsonify({"status": overall, "tools": tools_status})


@app.route("/scan/nmap", methods=["POST"])
def scan_nmap() -> Union[Response, Tuple[Response, int]]:
    target, args, timeout, err = _parse_scan_request()
    if err:
        return jsonify({"error": err[0]}), err[1]

    if not _tool_available("nmap"):
        return jsonify({"error": "nmap not available"}), 503

    cmd = ["nmap"] + args + [target]
    result = _run_tool(cmd, timeout)
    return jsonify(result)


@app.route("/scan/testssl", methods=["POST"])
def scan_testssl() -> Union[Response, Tuple[Response, int]]:
    target, args, timeout, err = _parse_scan_request()
    if err:
        return jsonify({"error": err[0]}), err[1]

    if not _tool_available("testssl.sh"):
        return jsonify({"error": "testssl.sh not available"}), 503

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        json_output_path = tmp.name

    try:
        cmd = ["testssl.sh", "--jsonfile", json_output_path] + args + [target]
        result = _run_tool(cmd, timeout)

        if os.path.isfile(json_output_path) and os.path.getsize(json_output_path) > 0:
            with open(json_output_path, "rb") as f:
                result["output_file"] = base64.b64encode(f.read()).decode("utf-8")
    finally:
        if os.path.isfile(json_output_path):
            os.unlink(json_output_path)

    return jsonify(result)


@app.route("/scan/ssh-audit", methods=["POST"])
def scan_ssh_audit() -> Union[Response, Tuple[Response, int]]:
    target, args, timeout, err = _parse_scan_request()
    if err:
        return jsonify({"error": err[0]}), err[1]

    if not _tool_available("ssh-audit"):
        return jsonify({"error": "ssh-audit not available"}), 503

    cmd = ["ssh-audit"] + args + [target]
    result = _run_tool(cmd, timeout)
    return jsonify(result)


@app.route("/scan/hydra", methods=["POST"])
def scan_hydra() -> Union[Response, Tuple[Response, int]]:
    target, args, timeout, err = _parse_scan_request()
    if err:
        return jsonify({"error": err[0]}), err[1]

    if not _tool_available("hydra"):
        return jsonify({"error": "hydra not available"}), 503

    cmd = ["hydra"] + args + [target]
    result = _run_tool(cmd, timeout)
    return jsonify(result)


@app.route("/scan/nikto", methods=["POST"])
def scan_nikto() -> Union[Response, Tuple[Response, int]]:
    target, args, timeout, err = _parse_scan_request()
    if err:
        return jsonify({"error": err[0]}), err[1]

    if not _tool_available("nikto"):
        return jsonify({"error": "nikto not available"}), 503

    cmd = ["nikto"] + args + ["-h", target]
    result = _run_tool(cmd, timeout)
    return jsonify(result)


@app.route("/scan/ping", methods=["POST"])
def scan_ping() -> Union[Response, Tuple[Response, int]]:
    data = request.get_json(force=True, silent=True)
    if not data or not data.get("target"):
        return jsonify({"error": "Missing 'target' field"}), 400

    try:
        target = _validate_target(data["target"])
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    try:
        count = min(int(data.get("count", 3)), 10)
        timeout = min(int(data.get("timeout", 30)), 60)
    except (TypeError, ValueError):
        return jsonify({"error": "'count' and 'timeout' must be integers"}), 400

    cmd = ["ping", "-c", str(count), "-W", "2", target]
    result = _run_tool(cmd, timeout)
    return jsonify(result)


@app.route("/versions", methods=["GET"])
def tool_versions() -> Response:
    """Return installed tool versions."""
    version_cmds = {
        "nmap": ["nmap", "--version"],
        "testssl": ["testssl.sh", "--version"],
        "ssh_audit": ["ssh-audit", "--help"],
        "hydra": ["hydra", "-h"],
        "nikto": ["nikto", "-Version"],
    }
    versions = {}
    for tool, cmd in version_cmds.items():
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            output = (result.stdout.strip() or result.stderr.strip())
            versions[tool] = output.split("\n")[0][:100] if output else "installed"
        except Exception:
            versions[tool] = "unavailable"
    return jsonify({"versions": versions})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001, debug=False)
