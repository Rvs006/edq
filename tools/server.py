"""EDQ Tools Sidecar — REST API wrapper for security scanning tools."""

import base64
import hmac
import ipaddress
import os
import re
import shutil
import subprocess
import tempfile
import time

from typing import Tuple, Union

from functools import wraps

from flask import Flask, Response, jsonify, request

app = Flask(__name__)

# Shared secret for authenticating requests from the backend
TOOLS_API_KEY = os.environ.get("TOOLS_API_KEY", "")

if not TOOLS_API_KEY:
    raise RuntimeError(
        "TOOLS_API_KEY environment variable is required. "
        "Generate one with: openssl rand -hex 32"
    )


def require_api_key(f):
    """Reject requests without a valid X-Tools-Key header."""
    @wraps(f)
    def decorated(*args, **kwargs):
        provided = request.headers.get("X-Tools-Key", "")
        if not provided or not hmac.compare_digest(provided, TOOLS_API_KEY):
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

ALLOWED_TOOLS = {
    "nmap": "nmap",
    "testssl": "testssl.sh",
    "ssh_audit": "ssh-audit",
    "hydra": "hydra",
    "nikto": "nikto",
}

# Hostname pattern: labels of 1-63 chars, total max 253, no leading/trailing hyphens
_HOSTNAME_LABEL_RE = re.compile(r"^(?!-)[a-zA-Z0-9-]{1,63}(?<!-)$")


def _is_valid_target(target: str) -> bool:
    """Return True if target is a valid IPv4, IPv6, CIDR range, or hostname."""
    # Try IPv4 / IPv6 first
    try:
        ipaddress.ip_address(target)
        return True
    except ValueError:
        pass
    # Try CIDR notation (e.g. 192.168.1.0/24)
    try:
        ipaddress.ip_network(target, strict=False)
        return True
    except ValueError:
        pass
    # Validate as hostname (RFC 1123)
    if len(target) > 253:
        return False
    labels = target.rstrip(".").split(".")
    return all(_HOSTNAME_LABEL_RE.match(label) for label in labels)


# Keep IP_RE for backward compatibility with callers that use it directly
IP_RE = re.compile(r".*")  # validation now done via _is_valid_target()

BLOCKED_ARGS = {"&&", "||", ";", "|", "`", "$", "(", ")", "{", "}", "<", ">", "\n", "\r"}

# Whitelist of allowed flags per tool to prevent argument injection
ALLOWED_FLAGS = {
    "nmap": {
        "-sn", "-sS", "-sT", "-sU", "-sV", "-sC", "-A", "-O", "-Pn", "-p", "-p-",
        "-T0", "-T1", "-T2", "-T3", "-T4", "-T5", "--top-ports", "--open",
        "-oX", "-oN", "-oG", "-v", "-vv", "--version-intensity",
        "--script", "-F", "-n", "-R", "-6", "--max-rate", "-",
    },
    "hydra": {
        "-l", "-L", "-p", "-P", "-s", "-t", "-f", "-V", "-v", "-e",
        "nsr", "-o", "-M", "-C",
    },
    "testssl": {
        "--jsonfile", "--csv", "--html", "--quiet", "--wide", "--color",
        "--fast", "--ip", "--nodns", "--sneaky", "--bugs", "--assume-http",
        "-p", "-s", "-f", "-U", "-S", "-P", "-h", "-E",
    },
    "ssh-audit": {
        "-p", "-T", "-t", "-n", "-v", "-l",
    },
    "nikto": {
        "-h", "-host", "-p", "-ssl", "-nossl", "-Tuning", "-Display", "-output",
        "-Format", "-timeout", "-maxtime", "-Cgidirs", "-id", "-ask",
    },
}


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
    if not _is_valid_target(target):
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


def _validate_args_for_tool(args: list, tool_name: str) -> list:
    """Validate args against both blocked chars and per-tool flag whitelist."""
    sanitised = _validate_args(args)
    allowed = ALLOWED_FLAGS.get(tool_name)
    if not allowed:
        return sanitised
    for arg in sanitised:
        if arg.startswith("-"):
            flag = arg.split("=")[0]
            if flag not in allowed:
                raise ValueError(f"Flag '{flag}' is not allowed for {tool_name}")
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


def _parse_scan_request(tool_name=None):
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
        if tool_name:
            args = _validate_args_for_tool(args, tool_name)
        else:
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
@require_api_key
def scan_nmap() -> Union[Response, Tuple[Response, int]]:
    target, args, timeout, err = _parse_scan_request(tool_name="nmap")
    if err:
        return jsonify({"error": err[0]}), err[1]

    if not _tool_available("nmap"):
        return jsonify({"error": "nmap not available"}), 503

    cmd = ["nmap"] + args + [target]
    result = _run_tool(cmd, timeout)
    return jsonify(result)


@app.route("/scan/testssl", methods=["POST"])
@require_api_key
def scan_testssl() -> Union[Response, Tuple[Response, int]]:
    target, args, timeout, err = _parse_scan_request(tool_name="testssl")
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
@require_api_key
def scan_ssh_audit() -> Union[Response, Tuple[Response, int]]:
    target, args, timeout, err = _parse_scan_request(tool_name="ssh-audit")
    if err:
        return jsonify({"error": err[0]}), err[1]

    if not _tool_available("ssh-audit"):
        return jsonify({"error": "ssh-audit not available"}), 503

    cmd = ["ssh-audit"] + args + [target]
    result = _run_tool(cmd, timeout)
    return jsonify(result)


@app.route("/scan/hydra", methods=["POST"])
@require_api_key
def scan_hydra() -> Union[Response, Tuple[Response, int]]:
    target, args, timeout, err = _parse_scan_request(tool_name="hydra")
    if err:
        return jsonify({"error": err[0]}), err[1]

    if not _tool_available("hydra"):
        return jsonify({"error": "hydra not available"}), 503

    cmd = ["hydra"] + args + [target]
    result = _run_tool(cmd, timeout)
    return jsonify(result)


@app.route("/scan/nikto", methods=["POST"])
@require_api_key
def scan_nikto() -> Union[Response, Tuple[Response, int]]:
    target, args, timeout, err = _parse_scan_request(tool_name="nikto")
    if err:
        return jsonify({"error": err[0]}), err[1]

    if not _tool_available("nikto"):
        return jsonify({"error": "nikto not available"}), 503

    cmd = ["nikto"] + args + ["-h", target]
    result = _run_tool(cmd, timeout)
    return jsonify(result)


@app.route("/scan/ping", methods=["POST"])
@require_api_key
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
@require_api_key
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


@app.route("/rotate-key", methods=["POST"])
@require_api_key
def rotate_key() -> Union[Response, Tuple[Response, int]]:
    """Accept a new API key from the backend during key rotation."""
    global TOOLS_API_KEY
    data = request.get_json(force=True, silent=True)
    if not data or not data.get("new_key"):
        return jsonify({"error": "Missing 'new_key' field"}), 400
    new_key = data["new_key"]
    if len(new_key) < 32:
        return jsonify({"error": "Key must be at least 32 characters"}), 400
    TOOLS_API_KEY = new_key
    return jsonify({"message": "Key rotated successfully"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001, debug=False)
