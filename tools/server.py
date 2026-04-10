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

from collections import defaultdict
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

MAX_ARG_LENGTH = 200  # Maximum length per individual argument

# Whitelist of safe nmap scripts — only these may be passed to --script
ALLOWED_NMAP_SCRIPTS = frozenset({
    "default", "safe", "discovery", "version", "auth", "broadcast",
    "vuln", "exploit", "intrusive", "malware", "external",
    # Common individual scripts
    "banner", "dns-brute", "http-title", "http-headers", "http-methods",
    "http-server-header", "http-robots.txt", "http-enum", "http-auth",
    "ssl-cert", "ssl-enum-ciphers", "ssh-hostkey", "ssh2-enum-algos",
    "smb-os-discovery", "smb-protocols", "smb-security-mode",
    "snmp-info", "snmp-brute", "ftp-anon", "telnet-encryption",
    "nbstat", "ntp-info", "dns-zone-transfer",
    # Additional protocol scripts
    "upnp-info",
})

# Whitelist of allowed flags per tool to prevent argument injection
ALLOWED_FLAGS = {
    "nmap": {
        "-sn", "-sS", "-sT", "-sU", "-sV", "-sC", "-A", "-O", "-Pn", "-p", "-p-",
        "-T0", "-T1", "-T2", "-T3", "-T4", "-T5", "--top-ports", "--open",
        "-oX", "-oN", "-oG", "-v", "-vv", "--version-intensity",
        "--script", "-F", "-n", "-R", "-6", "--max-rate", "-",
        "--min-rate", "--max-retries", "--defeat-rst-ratelimit", "--send-ip", "-PR", "-e",
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
        "-p", "-T", "-t", "-n", "-v", "-l", "-j",
    },
    "nikto": {
        "-h", "-host", "-p", "-ssl", "-nossl", "-Tuning", "-Display", "-output",
        "-Format", "-timeout", "-maxtime", "-Cgidirs", "-id", "-ask",
    },
}

# Approved directory for hydra wordlist files (-L, -P, -C flags)
HYDRA_APPROVED_WORDLIST_DIRS = ("/app/wordlists/", "/usr/share/wordlists/")


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


def _validate_targets(target: str) -> str:
    """Validate one or more whitespace-separated scan targets for nmap."""
    target = target.strip()
    if not target:
        raise ValueError("Invalid target: empty or too long")
    tokens = target.split()
    if len(tokens) > 256:
        raise ValueError("Too many scan targets in a single request")
    for token in tokens:
        _validate_target(token)
    return " ".join(tokens)


def _validate_args(args: list) -> list:
    sanitised = []
    for arg in args:
        arg = str(arg)
        if len(arg) > MAX_ARG_LENGTH:
            app.logger.warning("Blocked oversized argument (%d chars): %.50s...", len(arg), arg)
            raise ValueError(f"Argument too long ({len(arg)} chars, max {MAX_ARG_LENGTH})")
        for blocked in BLOCKED_ARGS:
            if blocked in arg:
                app.logger.warning("Blocked argument containing '%s': %.50s", blocked, arg)
                raise ValueError(f"Blocked character in argument: {blocked}")
        sanitised.append(arg)
    return sanitised


def _validate_nmap_script_arg(script_value: str) -> None:
    """Validate that --script values only contain whitelisted script names."""
    # script_value can be comma-separated, e.g. "ssl-cert,ssl-enum-ciphers"
    scripts = [s.strip() for s in script_value.split(",")]
    for script in scripts:
        if not script:
            continue
        # Strip leading + or - modifiers (e.g. "+safe" or "-intrusive")
        clean = script.lstrip("+-")
        if clean not in ALLOWED_NMAP_SCRIPTS:
            app.logger.warning("Blocked disallowed nmap script: %s", script)
            raise ValueError(
                f"Nmap script '{clean}' is not in the allowed whitelist. "
                "Contact an admin to add it if needed."
            )


def _validate_hydra_wordlist_paths(args: list) -> None:
    """Validate that -L, -P, -C file paths point to approved directories only."""
    wordlist_flags = {"-L", "-P", "-C"}
    i = 0
    while i < len(args):
        arg = str(args[i])
        if arg in wordlist_flags:
            if i + 1 >= len(args):
                raise ValueError(f"Flag '{arg}' requires a file path argument")
            file_path = str(args[i + 1])
            # Resolve the path to catch traversal attempts (e.g. /app/wordlists/../../etc/passwd)
            resolved = os.path.normpath(file_path)
            if os.path.isabs(resolved):
                if not any(resolved.startswith(d) for d in HYDRA_APPROVED_WORDLIST_DIRS):
                    app.logger.warning(
                        "Blocked hydra wordlist path outside approved dirs: %s", file_path
                    )
                    raise ValueError(
                        f"Wordlist path '{file_path}' is not in an approved directory. "
                        f"Allowed: {', '.join(HYDRA_APPROVED_WORDLIST_DIRS)}"
                    )
            # Relative paths: block any traversal attempts
            elif ".." in resolved:
                raise ValueError(
                    f"Wordlist path '{file_path}' contains directory traversal"
                )
            i += 2
        else:
            i += 1


def _validate_args_for_tool(args: list, tool_name: str) -> list:
    """Validate args against both blocked chars and per-tool flag whitelist."""
    sanitised = _validate_args(args)
    allowed = ALLOWED_FLAGS.get(tool_name)
    if not allowed:
        return sanitised
    i = 0
    while i < len(sanitised):
        arg = sanitised[i]
        if arg.startswith("-"):
            flag = arg.split("=")[0]
            if flag not in allowed:
                app.logger.warning("Blocked flag '%s' for tool %s", flag, tool_name)
                raise ValueError(f"Flag '{flag}' is not allowed for {tool_name}")
            # Validate --script values for nmap
            if tool_name == "nmap" and flag == "--script":
                if "=" in arg:
                    # --script=value form
                    script_value = arg.split("=", 1)[1]
                    _validate_nmap_script_arg(script_value)
                elif i + 1 < len(sanitised) and not sanitised[i + 1].startswith("-"):
                    # --script value form (next arg is the value)
                    _validate_nmap_script_arg(sanitised[i + 1])
        i += 1

    # Validate hydra wordlist paths are in approved directories
    if tool_name == "hydra":
        _validate_hydra_wordlist_paths(sanitised)

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
        target = _validate_targets(target) if tool_name == "nmap" else _validate_target(target)
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


# ---------------------------------------------------------------------------
# Concurrency limit — max concurrent subprocess scans
# ---------------------------------------------------------------------------
MAX_CONCURRENT_SCANS = int(os.environ.get("MAX_CONCURRENT_SCANS", "10"))
_scan_semaphore = threading.Semaphore(MAX_CONCURRENT_SCANS)


# ---------------------------------------------------------------------------
# Per-target rate limiter — max 5 scans per target per minute
# ---------------------------------------------------------------------------
_RATE_LIMIT_MAX = 30
_RATE_LIMIT_WINDOW = 60  # seconds
_rate_limit_store: dict[str, list[float]] = defaultdict(list)
_rate_limit_lock = threading.Lock()


def _check_rate_limit(target: str) -> bool:
    """Return True if request is allowed, False if rate-limited."""
    key = target.split()[0].strip()
    now = time.time()
    with _rate_limit_lock:
        timestamps = _rate_limit_store[key]
        # Prune expired entries
        _rate_limit_store[key] = [t for t in timestamps if now - t < _RATE_LIMIT_WINDOW]
        if len(_rate_limit_store[key]) >= _RATE_LIMIT_MAX:
            return False
        _rate_limit_store[key].append(now)
        return True


@app.route("/health", methods=["GET"])
def health() -> Response:
    tools_status = {}
    for key, binary in ALLOWED_TOOLS.items():
        tools_status[key] = _tool_available(binary)

    overall = "healthy" if all(tools_status.get(k) for k in ESSENTIAL_TOOLS) else "degraded"
    return jsonify({"status": overall, "tools": tools_status})


def _tcp_probe(ip: str, ports: tuple = (80, 443, 53, 22, 8080, 8443), timeout: float = 1.5) -> bool:
    """Quick TCP connect probe — returns True if any port responds."""
    import socket as _sock
    for port in ports:
        try:
            s = _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect((ip, port))
            s.close()
            return True
        except (OSError, _sock.timeout):
            try:
                s.close()
            except Exception:
                pass
    return False


def _get_container_subnets() -> list[dict]:
    """Discover subnets reachable from this container via ip route / ip addr."""
    subnets: list[dict] = []
    seen_cidrs: set[str] = set()
    try:
        result = subprocess.run(
            ["ip", "route"], capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            # e.g. "192.168.1.0/24 via 172.17.0.1 dev eth0"
            # or   "default via 172.17.0.1 dev eth0"
            parts = line.split()
            if not parts or parts[0] == "default":
                continue
            cidr = parts[0]
            try:
                net = ipaddress.ip_network(cidr, strict=False)
            except ValueError:
                continue
            # Skip Docker-internal and loopback subnets
            if (net.is_private and str(net).startswith(("172.17.", "172.18.", "172.19.",
                "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25."))) \
                    or net.is_loopback or str(net) in seen_cidrs:
                continue
            seen_cidrs.add(str(net))
            subnets.append({
                "cidr": str(net),
                "gateway": parts[2] if len(parts) > 2 and parts[1] == "via" else None,
            })
    except Exception:
        pass
    return subnets


@app.route("/detect-networks", methods=["GET"])
@require_api_key
def detect_networks() -> Response:
    """Discover host network interfaces and reachable subnets.

    Works from inside Docker by:
    1. Resolving host.docker.internal to find the host IP
    2. Probing common subnets via TCP connect (socket + nmap)
    3. Falling back to container route table if DNS resolution fails
    4. Detecting direct-connected devices (link-local)
    """
    import socket

    interfaces: list[dict] = []
    host_ip = None
    debug_info: dict = {}

    # -- Step 1: Resolve the Docker host IP --
    try:
        host_ip = socket.gethostbyname("host.docker.internal")
        debug_info["host_docker_internal"] = host_ip
    except socket.gaierror as e:
        debug_info["host_docker_internal_error"] = str(e)

    # -- Step 2: Detect subnets based on host IP --
    if host_ip and host_ip.startswith("192.168.65."):
        # Docker Desktop VM gateway — probe common LAN subnets
        debug_info["mode"] = "docker_desktop_gateway"
        candidates = [
            ("192.168.1.0/24", ["192.168.1.1", "192.168.1.254"]),
            ("192.168.0.0/24", ["192.168.0.1", "192.168.0.254"]),
            ("10.0.0.0/24", ["10.0.0.1", "10.0.0.254"]),
            ("172.16.0.0/24", ["172.16.0.1", "172.16.0.254"]),
        ]
        for cidr, probe_ips in candidates:
            # Fast path: try Python socket probe first (faster than nmap)
            reachable_via_socket = any(_tcp_probe(ip) for ip in probe_ips)
            if reachable_via_socket:
                found_ips = [ip for ip in probe_ips if _tcp_probe(ip)]
                label = f"Office/VPN ({cidr})" if cidr.startswith("10.") else f"Local Network ({cidr})"
                interfaces.append({
                    "label": label,
                    "type": "ethernet",
                    "cidr": cidr,
                    "hosts_found": len(found_ips),
                    "sample_hosts": found_ips[:5],
                    "reachable": True,
                })
                continue

            # Slow path: try nmap TCP connect if socket probe failed
            try:
                result = subprocess.run(
                    ["nmap", "-sT", "-Pn", "--top-ports", "10", "-T4",
                     "--max-retries", "1", "--host-timeout", "5s"] + probe_ips,
                    capture_output=True, text=True, timeout=15,
                )
                if "open" in result.stdout:
                    found_ips = []
                    for line in result.stdout.splitlines():
                        if "Nmap scan report for" in line:
                            parts = line.split()
                            ip_part = parts[-1].strip("()")
                            if _is_valid_target(ip_part):
                                found_ips.append(ip_part)
                    label = f"Office/VPN ({cidr})" if cidr.startswith("10.") else f"Local Network ({cidr})"
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
        # Direct host IP — check it's not a Docker/WSL internal IP
        debug_info["mode"] = "direct_host_ip"
        try:
            addr = ipaddress.ip_address(host_ip)
            net = ipaddress.ip_network(f"{host_ip}/24", strict=False)
            is_docker_internal = str(net).startswith(("172.17.", "172.18.", "172.19.",
                "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25."))
            if not is_docker_internal and addr.is_private:
                subnet = str(net)
                interfaces.append({
                    "label": f"Host Network ({subnet})",
                    "type": "ethernet",
                    "cidr": subnet,
                    "hosts_found": 1,
                    "sample_hosts": [host_ip],
                    "reachable": True,
                })
            elif is_docker_internal:
                # host.docker.internal resolved to a Docker-internal IP (WSL2)
                # Fall through to container subnet detection below
                debug_info["host_ip_is_docker_internal"] = True
        except ValueError:
            pass

    # -- Step 3: Fallback — detect via container route table --
    if not interfaces:
        debug_info["fallback"] = "container_routes"
        container_subnets = _get_container_subnets()
        for sub in container_subnets:
            cidr = sub["cidr"]
            gateway = sub.get("gateway")
            # Verify the gateway is reachable via TCP probe
            if gateway and _tcp_probe(gateway):
                label = f"Local Network ({cidr})"
                if cidr.startswith("10."):
                    label = f"Office/VPN ({cidr})"
                interfaces.append({
                    "label": label,
                    "type": "ethernet",
                    "cidr": cidr,
                    "hosts_found": 1,
                    "sample_hosts": [gateway],
                    "reachable": True,
                })

        # Last resort: probe the Docker host IP itself on the most common subnets
        if not interfaces and not host_ip:
            debug_info["fallback"] = "blind_probe"
            for cidr, gateways in [
                ("192.168.1.0/24", ["192.168.1.1"]),
                ("192.168.0.0/24", ["192.168.0.1"]),
                ("10.0.0.0/24", ["10.0.0.1"]),
            ]:
                for gw in gateways:
                    if _tcp_probe(gw, timeout=2.0):
                        interfaces.append({
                            "label": f"Local Network ({cidr})",
                            "type": "ethernet",
                            "cidr": cidr,
                            "hosts_found": 1,
                            "sample_hosts": [gw],
                            "reachable": True,
                        })
                        break
                if interfaces:
                    break

    # -- Step 4: Link-local detection (direct Cat6 cable — 169.254.x.x) --
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
        "debug": debug_info,
    })


@app.route("/scan/nmap", methods=["POST"])
@require_api_key
def scan_nmap() -> Union[Response, Tuple[Response, int]]:
    target, args, timeout, err = _parse_scan_request(tool_name="nmap")
    if err:
        return jsonify({"error": err[0]}), err[1]

    if not _tool_available("nmap"):
        return jsonify({"error": "nmap not available"}), 503

    if not _check_rate_limit(target):
        return jsonify({"error": "Rate limit exceeded: max 5 scans per target per minute"}), 429

    cmd = ["nmap"] + args + target.split()
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

    if not _check_rate_limit(target):
        return jsonify({"error": "Rate limit exceeded: max 5 scans per target per minute"}), 429

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

    if not _check_rate_limit(target):
        return jsonify({"error": "Rate limit exceeded: max 5 scans per target per minute"}), 429

    cmd = ["ssh-audit"] + args + [target]
    result = _run_tool(cmd, timeout, target=target)
    return jsonify(result)


@app.route("/scan/hydra", methods=["POST"])
@require_api_key
def scan_hydra() -> Union[Response, Tuple[Response, int]]:
    """Run hydra credential test.

    NOTE: The caller is responsible for including the target IP and service
    in the args list (e.g. [..., "192.168.1.1", "http-get"]).  The sidecar
    does NOT append target to avoid double-IP issues since hydra requires
    the target to appear before the service name in the argument list.
    """
    target, args, timeout, err = _parse_scan_request(tool_name="hydra")
    if err:
        return jsonify({"error": err[0]}), err[1]

    if not _tool_available("hydra"):
        return jsonify({"error": "hydra not available"}), 503

    if not _check_rate_limit(target):
        return jsonify({"error": "Rate limit exceeded: max 5 scans per target per minute"}), 429

    # Do not append target — the caller includes target+service in args
    cmd = ["hydra"] + args
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

    if not _check_rate_limit(target):
        return jsonify({"error": "Rate limit exceeded: max 5 scans per target per minute"}), 429

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

    if not _check_rate_limit(target):
        return jsonify({"error": "Rate limit exceeded: max 5 scans per target per minute"}), 429

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


# Pinned latest-known versions — update these when rebuilding the image
LATEST_KNOWN_VERSIONS = {
    "nmap": "7.95",
    "testssl": "3.2.3",
    "ssh_audit": "3.3.0",
    "hydra": "9.5",
    "nikto": "2.5.0",
}

_VERSION_PARSE = {
    "nmap": re.compile(r"Nmap version ([\d.]+)"),
    "testssl": re.compile(r"testssl\.sh\s+([\d.]+)"),
    "ssh_audit": re.compile(r"([\d.]+)"),
    "hydra": re.compile(r"Hydra v([\d.]+)"),
    "nikto": re.compile(r"Nikto\s+v?([\d.]+)"),
}


@app.route("/check-updates", methods=["GET"])
@require_api_key
def check_updates() -> Response:
    """Compare installed tool versions against latest known versions."""
    version_cmds = {
        "nmap": ["nmap", "--version"],
        "testssl": ["testssl.sh", "--version"],
        "ssh_audit": ["ssh-audit", "--help"],
        "hydra": ["hydra", "-h"],
        "nikto": ["nikto", "-Version"],
    }
    results = {}
    for tool, cmd in version_cmds.items():
        installed = None
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            output = (proc.stdout.strip() or proc.stderr.strip())
            pattern = _VERSION_PARSE.get(tool)
            if pattern and output:
                match = pattern.search(output)
                if match:
                    installed = match.group(1)
        except Exception:
            pass

        latest = LATEST_KNOWN_VERSIONS.get(tool, "unknown")
        up_to_date = (installed == latest) if installed else None
        results[tool] = {
            "installed": installed or "unknown",
            "latest_known": latest,
            "up_to_date": up_to_date,
            "action": "none" if up_to_date else "rebuild image to update",
        }

    any_outdated = any(not r["up_to_date"] for r in results.values())
    return jsonify({
        "tools": results,
        "image_rebuild_recommended": any_outdated,
        "update_instructions": (
            "Run 'docker compose build tools' to rebuild with latest pinned versions. "
            "Do NOT auto-update tools at runtime — untested versions may break scans."
        ) if any_outdated else "All tools are up to date.",
    })


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


def _guarded_stream(generator):
    """Wrap a streaming generator with concurrency semaphore control."""
    try:
        yield from generator
    finally:
        _scan_semaphore.release()


@app.route("/stream/nmap", methods=["POST"])
@require_api_key
def stream_nmap() -> Union[Response, Tuple[Response, int]]:
    target, args, timeout, err = _parse_scan_request(tool_name="nmap")
    if err:
        return jsonify({"error": err[0]}), err[1]
    if not _tool_available("nmap"):
        return jsonify({"error": "nmap not available"}), 503
    if not _check_rate_limit(target):
        return jsonify({"error": "Rate limit exceeded: max 5 scans per target per minute"}), 429
    if not _scan_semaphore.acquire(blocking=False):
        return jsonify({"error": "Too many concurrent scans, please retry later"}), 503
    cmd = ["nmap"] + args + target.split()
    return Response(
        _guarded_stream(_run_tool_stream(cmd, timeout, target=target)),
        mimetype="text/event-stream",
    )


@app.route("/stream/testssl", methods=["POST"])
@require_api_key
def stream_testssl() -> Union[Response, Tuple[Response, int]]:
    target, args, timeout, err = _parse_scan_request(tool_name="testssl")
    if err:
        return jsonify({"error": err[0]}), err[1]
    if not _tool_available("testssl.sh"):
        return jsonify({"error": "testssl.sh not available"}), 503
    if not _check_rate_limit(target):
        return jsonify({"error": "Rate limit exceeded: max 5 scans per target per minute"}), 429
    if not _scan_semaphore.acquire(blocking=False):
        return jsonify({"error": "Too many concurrent scans, please retry later"}), 503

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

    return Response(
        _guarded_stream(_stream_testssl_gen()),
        mimetype="text/event-stream",
    )


@app.route("/stream/ssh-audit", methods=["POST"])
@require_api_key
def stream_ssh_audit() -> Union[Response, Tuple[Response, int]]:
    target, args, timeout, err = _parse_scan_request(tool_name="ssh-audit")
    if err:
        return jsonify({"error": err[0]}), err[1]
    if not _tool_available("ssh-audit"):
        return jsonify({"error": "ssh-audit not available"}), 503
    if not _check_rate_limit(target):
        return jsonify({"error": "Rate limit exceeded: max 5 scans per target per minute"}), 429
    if not _scan_semaphore.acquire(blocking=False):
        return jsonify({"error": "Too many concurrent scans, please retry later"}), 503
    cmd = ["ssh-audit"] + args + [target]
    return Response(
        _guarded_stream(_run_tool_stream(cmd, timeout)),
        mimetype="text/event-stream",
    )


@app.route("/stream/hydra", methods=["POST"])
@require_api_key
def stream_hydra() -> Union[Response, Tuple[Response, int]]:
    """Stream hydra output.

    NOTE: The caller is responsible for including the target IP and service
    in the args list.  The sidecar does NOT append target to avoid
    double-IP issues.
    """
    target, args, timeout, err = _parse_scan_request(tool_name="hydra")
    if err:
        return jsonify({"error": err[0]}), err[1]
    if not _tool_available("hydra"):
        return jsonify({"error": "hydra not available"}), 503
    if not _check_rate_limit(target):
        return jsonify({"error": "Rate limit exceeded: max 5 scans per target per minute"}), 429
    if not _scan_semaphore.acquire(blocking=False):
        return jsonify({"error": "Too many concurrent scans, please retry later"}), 503
    # Do not append target — the caller includes target+service in args
    cmd = ["hydra"] + args
    return Response(
        _guarded_stream(_run_tool_stream(cmd, timeout, target=target)),
        mimetype="text/event-stream",
    )


@app.route("/stream/nikto", methods=["POST"])
@require_api_key
def stream_nikto() -> Union[Response, Tuple[Response, int]]:
    target, args, timeout, err = _parse_scan_request(tool_name="nikto")
    if err:
        return jsonify({"error": err[0]}), err[1]
    if not _tool_available("nikto"):
        return jsonify({"error": "nikto not available"}), 503
    if not _check_rate_limit(target):
        return jsonify({"error": "Rate limit exceeded: max 5 scans per target per minute"}), 429
    if not _scan_semaphore.acquire(blocking=False):
        return jsonify({"error": "Too many concurrent scans, please retry later"}), 503
    cmd = ["nikto"] + args + ["-h", target]
    return Response(
        _guarded_stream(_run_tool_stream(cmd, timeout)),
        mimetype="text/event-stream",
    )


# Production entry point — use gunicorn in Docker (see Dockerfile CMD).
# This block is only used for local development.
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001, debug=False)
