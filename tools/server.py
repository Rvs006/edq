"""EDQ Tools Sidecar — REST API wrapper for security scanning tools."""

import base64
import hmac
import ipaddress
import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time

from typing import Tuple, Union

from functools import wraps

from flask import Flask, Response, jsonify, request

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Active process tracking — maps target IP → set of Popen objects
# ---------------------------------------------------------------------------
_active_procs: dict[str, set[subprocess.Popen]] = {}
_procs_lock = threading.Lock()


def _track_proc(target: str, proc: subprocess.Popen) -> None:
    """Register a running subprocess for a given target."""
    # Normalise target to just the first IP/host token
    key = target.split()[0].strip()
    with _procs_lock:
        _active_procs.setdefault(key, set()).add(proc)


def _untrack_proc(target: str, proc: subprocess.Popen) -> None:
    """Remove a finished subprocess from tracking."""
    key = target.split()[0].strip()
    with _procs_lock:
        procs = _active_procs.get(key)
        if procs:
            procs.discard(proc)
            if not procs:
                del _active_procs[key]


def _kill_procs_for_target(target: str) -> int:
    """Kill all tracked processes for a target. Returns count killed."""
    key = target.split()[0].strip()
    killed = 0
    with _procs_lock:
        procs = _active_procs.pop(key, set())
    for proc in procs:
        try:
            proc.kill()
            proc.wait(timeout=5)
            killed += 1
        except Exception:
            pass
    return killed

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


def _run_tool(cmd: list, timeout: int, target: str = "") -> dict:
    start = time.time()
    proc = None
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if target:
            _track_proc(target, proc)
        stdout, stderr = proc.communicate(timeout=timeout)
        duration = round(time.time() - start, 2)
        return {
            "exit_code": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "duration_seconds": duration,
            "output_file": None,
        }
    except subprocess.TimeoutExpired:
        if proc:
            proc.kill()
            proc.wait()
        duration = round(time.time() - start, 2)
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": f"Command timed out after {timeout}s",
            "duration_seconds": duration,
            "output_file": None,
        }
    except Exception as e:
        if proc and proc.poll() is None:
            proc.kill()
            proc.wait()
        duration = round(time.time() - start, 2)
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": str(e),
            "duration_seconds": duration,
            "output_file": None,
        }
    finally:
        if proc and target:
            _untrack_proc(target, proc)


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


@app.route("/detect-networks", methods=["GET"])
@require_api_key
def detect_networks() -> Response:
    """Discover host network interfaces and reachable subnets.

    Works from inside Docker by:
    1. Resolving host.docker.internal to find the host IP
    2. Running nmap -sn on likely subnets to find live hosts
    3. Detecting direct-connected devices (link-local)
    """
    import socket

    interfaces: list[dict] = []
    host_ip = None

    # Resolve the Docker host IP
    try:
        host_ip = socket.gethostbyname("host.docker.internal")
    except socket.gaierror:
        pass

    if host_ip and host_ip.startswith("192.168.65."):
        # Docker Desktop VM gateway — probe gateway IPs to find reachable subnets
        # Use TCP connect on common ports since ICMP doesn't work through NAT
        candidates = [
            ("192.168.1.0/24", ["192.168.1.1", "192.168.1.254"]),
            ("192.168.0.0/24", ["192.168.0.1", "192.168.0.254"]),
            ("10.0.0.0/24", ["10.0.0.1", "10.0.0.254"]),
            ("172.16.0.0/24", ["172.16.0.1", "172.16.0.254"]),
        ]
        for cidr, probe_ips in candidates:
            try:
                # Quick TCP connect probe on common gateway ports
                result = subprocess.run(
                    ["nmap", "-sT", "-Pn", "--top-ports", "5", "-T4",
                     "--max-retries", "1", "--host-timeout", "3s"] + probe_ips,
                    capture_output=True, text=True, timeout=12,
                )
                # Check if any port was open (means subnet is reachable)
                if "open" in result.stdout:
                    found_ips = []
                    for line in result.stdout.splitlines():
                        if "Nmap scan report for" in line:
                            parts = line.split()
                            ip_part = parts[-1].strip("()")
                            if _is_valid_target(ip_part):
                                found_ips.append(ip_part)

                    label = f"Local Network ({cidr})"
                    if cidr.startswith("10."):
                        label = f"Office/VPN ({cidr})"

                    interfaces.append({
                        "label": label,
                        "type": "ethernet",
                        "cidr": cidr,
                        "hosts_found": len(found_ips),
                        "sample_hosts": found_ips[:5],
                        "reachable": True,
                    })
            except (subprocess.TimeoutExpired, Exception):
                continue
    elif host_ip:
        # Direct host IP — derive /24 subnet
        parts = host_ip.split(".")
        if len(parts) == 4:
            subnet = f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
            interfaces.append({
                "label": f"Host Network ({subnet})",
                "type": "ethernet",
                "cidr": subnet,
                "hosts_found": 1,
                "sample_hosts": [host_ip],
                "reachable": True,
            })

    # Check for link-local (direct Cat6 cable connection — 169.254.x.x)
    try:
        result = subprocess.run(
            ["nmap", "-sn", "169.254.0.0/16", "--max-retries", "0", "-T5"],
            capture_output=True, text=True, timeout=10,
        )
        link_local_hosts = result.stdout.count("Nmap scan report for")
        if link_local_hosts > 0:
            found_ips = []
            for line in result.stdout.splitlines():
                if "Nmap scan report for" in line:
                    parts = line.split()
                    ip_part = parts[-1].strip("()")
                    if ip_part.startswith("169.254."):
                        found_ips.append(ip_part)
            if found_ips:
                interfaces.append({
                    "label": "Direct Cable Connection (link-local)",
                    "type": "direct",
                    "cidr": "169.254.0.0/16",
                    "hosts_found": len(found_ips),
                    "sample_hosts": found_ips[:5],
                    "reachable": True,
                })
    except (subprocess.TimeoutExpired, Exception):
        pass

    # Detect if running in Docker (for scan flag recommendations)
    in_docker = os.path.exists("/.dockerenv") or os.path.isfile("/proc/1/cgroup")

    return jsonify({
        "interfaces": interfaces,
        "host_ip": host_ip,
        "in_docker": in_docker,
        "scan_recommendation": "Use TCP connect scan (-sT -Pn) when running in Docker" if in_docker else None,
    })


@app.route("/scan/nmap", methods=["POST"])
@require_api_key
def scan_nmap() -> Union[Response, Tuple[Response, int]]:
    target, args, timeout, err = _parse_scan_request(tool_name="nmap")
    if err:
        return jsonify({"error": err[0]}), err[1]

    if not _tool_available("nmap"):
        return jsonify({"error": "nmap not available"}), 503

    cmd = ["nmap"] + args + [target]
    result = _run_tool(cmd, timeout, target=target)
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
        result = _run_tool(cmd, timeout, target=target)

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
    result = _run_tool(cmd, timeout, target=target)
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
    result = _run_tool(cmd, timeout, target=target)
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
    result = _run_tool(cmd, timeout, target=target)
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


@app.route("/kill", methods=["POST"])
@require_api_key
def kill_processes() -> Union[Response, Tuple[Response, int]]:
    """Kill all running tool processes for a given target IP."""
    data = request.get_json(force=True, silent=True)
    if not data or not data.get("target"):
        return jsonify({"error": "Missing 'target' field"}), 400
    target = data["target"].strip()
    killed = _kill_procs_for_target(target)
    return jsonify({"killed": killed, "target": target})


@app.route("/kill-all", methods=["POST"])
@require_api_key
def kill_all_processes() -> Union[Response, Tuple[Response, int]]:
    """Kill ALL running tool processes. Used during orphan recovery."""
    total_killed = 0
    with _procs_lock:
        all_targets = list(_active_procs.keys())
    for t in all_targets:
        total_killed += _kill_procs_for_target(t)
    return jsonify({"killed": total_killed})


@app.route("/active-processes", methods=["GET"])
@require_api_key
def active_processes() -> Response:
    """List active processes grouped by target."""
    with _procs_lock:
        summary = {
            target: len(procs) for target, procs in _active_procs.items()
        }
    return jsonify(summary)


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


def _run_tool_stream(cmd: list, timeout: int, target: str = ""):
    """Generator yielding SSE events: stdout lines then final result JSON."""
    import json as _json
    start = time.time()
    stdout_lines: list[str] = []
    stderr_text = ""
    exit_code = -1
    proc = None
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            bufsize=1,  # line-buffered
        )
        if target:
            _track_proc(target, proc)
        # Read stdout line by line
        for line in proc.stdout:
            stdout_lines.append(line)
            yield f"data: {_json.dumps({'type': 'stdout', 'line': line})}\n\n"
        proc.wait(timeout=timeout)
        exit_code = proc.returncode
        stderr_text = proc.stderr.read() if proc.stderr else ""
    except subprocess.TimeoutExpired:
        if proc:
            proc.kill()
            proc.wait()
        stderr_text = f"Command timed out after {timeout}s"
    except Exception as e:
        if proc and proc.poll() is None:
            proc.kill()
            proc.wait()
        stderr_text = str(e)
    finally:
        if proc and target:
            _untrack_proc(target, proc)

    duration = round(time.time() - start, 2)
    result = {
        "exit_code": exit_code,
        "stdout": "".join(stdout_lines),
        "stderr": stderr_text,
        "duration_seconds": duration,
        "output_file": None,
    }
    yield f"data: {_json.dumps({'type': 'result', 'data': result})}\n\n"


@app.route("/stream/nmap", methods=["POST"])
@require_api_key
def stream_nmap() -> Union[Response, Tuple[Response, int]]:
    target, args, timeout, err = _parse_scan_request(tool_name="nmap")
    if err:
        return jsonify({"error": err[0]}), err[1]
    if not _tool_available("nmap"):
        return jsonify({"error": "nmap not available"}), 503
    cmd = ["nmap"] + args + [target]
    return Response(_run_tool_stream(cmd, timeout, target=target), mimetype="text/event-stream")


@app.route("/stream/testssl", methods=["POST"])
@require_api_key
def stream_testssl() -> Union[Response, Tuple[Response, int]]:
    target, args, timeout, err = _parse_scan_request(tool_name="testssl")
    if err:
        return jsonify({"error": err[0]}), err[1]
    if not _tool_available("testssl.sh"):
        return jsonify({"error": "testssl.sh not available"}), 503

    # Create temp file for JSON output like the sync endpoint
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        json_output_path = tmp.name

    def _stream_testssl_gen():
        import json as _json
        start = time.time()
        stdout_lines = []
        stderr_text = ""
        exit_code = -1
        proc = None
        try:
            cmd = ["testssl.sh", "--jsonfile", json_output_path] + args + [target]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
            _track_proc(target, proc)
            for line in proc.stdout:
                stdout_lines.append(line)
                yield f"data: {_json.dumps({'type': 'stdout', 'line': line})}\n\n"
            proc.wait(timeout=timeout)
            exit_code = proc.returncode
            stderr_text = proc.stderr.read() if proc.stderr else ""
        except subprocess.TimeoutExpired:
            if proc:
                proc.kill()
                proc.wait()
            stderr_text = f"Command timed out after {timeout}s"
        except Exception as e:
            if proc and proc.poll() is None:
                proc.kill()
                proc.wait()
            stderr_text = str(e)
        finally:
            if proc:
                _untrack_proc(target, proc)

        duration = round(time.time() - start, 2)
        result = {
            "exit_code": exit_code,
            "stdout": "".join(stdout_lines),
            "stderr": stderr_text,
            "duration_seconds": duration,
            "output_file": None,
        }
        # Attach JSON output file if generated
        try:
            if os.path.isfile(json_output_path) and os.path.getsize(json_output_path) > 0:
                with open(json_output_path, "rb") as f:
                    result["output_file"] = base64.b64encode(f.read()).decode("utf-8")
        finally:
            if os.path.isfile(json_output_path):
                os.unlink(json_output_path)

        yield f"data: {_json.dumps({'type': 'result', 'data': result})}\n\n"

    return Response(_stream_testssl_gen(), mimetype="text/event-stream")


@app.route("/stream/ssh-audit", methods=["POST"])
@require_api_key
def stream_ssh_audit() -> Union[Response, Tuple[Response, int]]:
    target, args, timeout, err = _parse_scan_request(tool_name="ssh-audit")
    if err:
        return jsonify({"error": err[0]}), err[1]
    if not _tool_available("ssh-audit"):
        return jsonify({"error": "ssh-audit not available"}), 503
    cmd = ["ssh-audit"] + args + [target]
    return Response(_run_tool_stream(cmd, timeout), mimetype="text/event-stream")


@app.route("/stream/hydra", methods=["POST"])
@require_api_key
def stream_hydra() -> Union[Response, Tuple[Response, int]]:
    target, args, timeout, err = _parse_scan_request(tool_name="hydra")
    if err:
        return jsonify({"error": err[0]}), err[1]
    if not _tool_available("hydra"):
        return jsonify({"error": "hydra not available"}), 503
    cmd = ["hydra"] + args + [target]
    return Response(_run_tool_stream(cmd, timeout), mimetype="text/event-stream")


@app.route("/stream/nikto", methods=["POST"])
@require_api_key
def stream_nikto() -> Union[Response, Tuple[Response, int]]:
    target, args, timeout, err = _parse_scan_request(tool_name="nikto")
    if err:
        return jsonify({"error": err[0]}), err[1]
    if not _tool_available("nikto"):
        return jsonify({"error": "nikto not available"}), 503
    cmd = ["nikto"] + args + ["-h", target]
    return Response(_run_tool_stream(cmd, timeout), mimetype="text/event-stream")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001, debug=False)
