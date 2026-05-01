"""EDQ scanner agent — REST API wrapper for security scanning tools."""

import base64
import errno
import hmac
import ipaddress
import json
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import tempfile
import threading
import time

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    "snmpwalk": "snmpwalk",
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

_TRACEBACK_HEADER_RE = re.compile(r"^Traceback \(most recent call last\):$")
_TRACEBACK_FRAME_RE = re.compile(r'^\s*File ".+", line \d+, in .+$')
_TRACEBACK_EXCEPTION_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception):")


def _sanitize_stderr(text: str) -> str:
    """Remove Python traceback frames from stderr before returning tool output."""
    if not text:
        return ""

    cleaned: list[str] = []
    in_traceback = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip("\r\n")
        stripped = line.strip()
        if _TRACEBACK_HEADER_RE.match(stripped):
            in_traceback = True
            if not cleaned or cleaned[-1] != "[stderr traceback omitted]":
                cleaned.append("[stderr traceback omitted]")
            continue
        if in_traceback:
            if (
                _TRACEBACK_FRAME_RE.match(line)
                or stripped.startswith(("raise ", "return ", "yield ", "await "))
                or stripped.startswith("^")
                or _TRACEBACK_EXCEPTION_RE.match(stripped)
            ):
                continue
            in_traceback = False
        cleaned.append(line)

    return "\n".join(cleaned)


def _sanitize_stderr_line(line: str, in_traceback: bool) -> tuple[str, bool]:
    """Streaming variant of _sanitize_stderr that preserves traceback state."""
    raw_line = line.rstrip("\r\n")
    stripped = raw_line.strip()
    if _TRACEBACK_HEADER_RE.match(stripped):
        return "[stderr traceback omitted]", True
    if _TRACEBACK_FRAME_RE.match(raw_line):
        return "[stderr traceback omitted]" if not in_traceback else "", True
    if in_traceback:
        if (
            stripped.startswith(("raise ", "return ", "yield ", "await "))
            or stripped.startswith("^")
        ):
            return "", True
        if _TRACEBACK_EXCEPTION_RE.match(stripped):
            return "", False
        if stripped:
            return "", True
        return "", False
    return raw_line, False


def _internal_tool_error() -> str:
    return "Scanner command failed"

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
    "nbstat", "ntp-info", "dns-zone-transfer", "bacnet-info",
    # Additional protocol scripts
    "upnp-info",
    "dhcp-discover",
})

# Whitelist of allowed flags per tool to prevent argument injection
ALLOWED_FLAGS = {
    "nmap": {
        "-sn", "-sS", "-sT", "-sU", "-sV", "-sC", "-A", "-O", "-Pn", "-p", "-p-",
        "-T0", "-T1", "-T2", "-T3", "-T4", "-T5", "--top-ports", "--open",
        "-v", "-vv", "--version-intensity", "--stats-every",
        "--script", "-F", "-n", "-R", "-6", "--max-rate", "--privileged", "-", "-oX",
        "--min-rate", "--max-retries", "--defeat-rst-ratelimit", "--send-ip", "-PR", "-e",
        "--host-timeout", "--traceroute", "--osscan-guess",
        # Host-discovery probe types — needed to reliably find devices whose
        # firewalls drop default nmap probes but still answer ICMP / specific TCP ports.
        "-PE", "-PP", "-PM", "-PS", "-PA", "-PU", "-PY",
    },
    "hydra": {
        "-l", "-L", "-p", "-P", "-s", "-t", "-f", "-V", "-v", "-e",
        "nsr", "-M", "-C",
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
        "-h", "-host", "-p", "-ssl", "-nossl", "-Tuning", "-Display",
        "-Format", "-timeout", "-maxtime", "-Cgidirs", "-id", "-ask",
    },
    "snmpwalk": {
        "-v", "-c", "-t", "-r", "-O", "-On", "-Oq", "-Ov", "-Oqv", "-OQv", "-Os",
    },
}

# Approved directory for hydra wordlist files (-L, -P, -C flags)
HYDRA_APPROVED_WORDLIST_DIRS = ("/app/wordlists/", "/usr/share/wordlists/")

_MAC_VENDOR_FALLBACKS = {
    "000CAB": "Commend International GmbH",
    "2C2D48": "Commend International GmbH",
    "BC6A44": "Commend International GmbH",
    "38D135": "EasyIO Corporation Sdn. Bhd.",
    "00408C": "Axis Communications AB",
    "ACCC8E": "Axis Communications AB",
    "B8A44F": "Axis Communications AB",
    "E82725": "Axis Communications AB",
    "00BC99": "Hangzhou Hikvision Digital Technology Co.,Ltd.",
    "0C75D2": "Hangzhou Hikvision Digital Technology Co.,Ltd.",
    "1012FB": "Hangzhou Hikvision Digital Technology Co.,Ltd.",
    "244845": "Hangzhou Hikvision Digital Technology Co.,Ltd.",
    "2857BE": "Hangzhou Hikvision Digital Technology Co.,Ltd.",
    "4CF5DC": "Hangzhou Hikvision Digital Technology Co.,Ltd.",
    "5850ED": "Hangzhou Hikvision Digital Technology Co.,Ltd.",
}
_MAC_PREFIX_RE = re.compile(r"^[0-9A-F]{6}$")
_MAC_VENDOR_CACHE: dict[str, str] | None = None


def _tool_available(binary: str) -> bool:
    return shutil.which(binary) is not None


def _normalize_mac_address(mac: str) -> str | None:
    hex_only = re.sub(r"[^0-9A-Fa-f]+", "", str(mac or ""))
    if len(hex_only) != 12:
        return None
    hex_only = hex_only.upper()
    return ":".join(hex_only[i:i + 2] for i in range(0, 12, 2))


def _normalize_mac_prefix(mac: str) -> str | None:
    hex_only = re.sub(r"[^0-9A-Fa-f]+", "", str(mac or ""))
    if len(hex_only) < 6:
        return None
    prefix = hex_only[:6].upper()
    return prefix if _MAC_PREFIX_RE.match(prefix) else None


def _load_mac_vendor_cache() -> dict[str, str]:
    global _MAC_VENDOR_CACHE
    if _MAC_VENDOR_CACHE is not None:
        return _MAC_VENDOR_CACHE

    cache = dict(_MAC_VENDOR_FALLBACKS)
    candidates = [
        "/usr/share/nmap/nmap-mac-prefixes",
        "/usr/local/share/nmap/nmap-mac-prefixes",
        "/opt/homebrew/share/nmap/nmap-mac-prefixes",
        "C:\\Program Files (x86)\\Nmap\\nmap-mac-prefixes",
        "C:\\Program Files\\Nmap\\nmap-mac-prefixes",
    ]

    nmap_binary = shutil.which("nmap")
    if nmap_binary:
        candidates.append(os.path.normpath(os.path.join(os.path.dirname(nmap_binary), "..", "share", "nmap", "nmap-mac-prefixes")))

    for path in candidates:
        if not path or not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#"):
                        continue
                    parts = stripped.split(maxsplit=1)
                    if len(parts) != 2:
                        continue
                    prefix, vendor = parts
                    prefix = prefix.strip().upper()
                    vendor = vendor.strip()
                    if _MAC_PREFIX_RE.match(prefix) and vendor:
                        cache[prefix] = vendor
        except Exception:
            continue

    _MAC_VENDOR_CACHE = cache
    return cache


def _lookup_mac_vendor(mac: str) -> str | None:
    prefix = _normalize_mac_prefix(mac)
    if not prefix:
        return None
    return _load_mac_vendor_cache().get(prefix)


def _running_in_docker() -> bool:
    if os.path.exists("/.dockerenv"):
        return True

    try:
        with open("/proc/1/cgroup", encoding="utf-8", errors="ignore") as handle:
            cgroup = handle.read().lower()
        return any(marker in cgroup for marker in ("docker", "containerd", "kubepods"))
    except OSError:
        return False


def _runtime_info() -> dict[str, str | bool]:
    in_docker = _running_in_docker()
    return {
        "os": platform.system() or os.name,
        "platform": platform.platform(),
        "in_docker": in_docker,
        "scanner_mode": "docker" if in_docker else "host",
    }


def _is_windows() -> bool:
    return os.name == "nt" or platform.system().lower().startswith("windows")


def _env_truthy(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_windows_ipconfig(stdout: str) -> list[dict[str, str]]:
    interfaces: list[dict[str, str]] = []
    current_name = ""
    current_ip = ""
    current_mask = ""

    def flush_current() -> None:
        nonlocal current_ip, current_mask
        if not current_ip or not current_mask:
            return
        try:
            ip_obj = ipaddress.ip_address(current_ip)
            network = ipaddress.ip_network(f"{current_ip}/{current_mask}", strict=False)
        except ValueError:
            return
        if ip_obj.is_loopback or network.prefixlen == 32:
            return
        interfaces.append(
            {
                "label": current_name or f"Host Interface ({network})",
                "type": "direct" if ip_obj.is_link_local else "ethernet",
                "cidr": str(network),
                "host_ip": current_ip,
            }
        )

    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        adapter_match = re.match(r"^(?:.+\s)?adapter\s+(.+):$", line, re.IGNORECASE)
        if adapter_match:
            flush_current()
            current_name = adapter_match.group(1).strip()
            current_ip = ""
            current_mask = ""
            continue

        if "IPv4 Address" in line or line.lower().startswith("ipv4"):
            ip_match = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", line)
            if ip_match:
                current_ip = ip_match.group(1)
            continue

        if "Subnet Mask" in line:
            mask_match = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", line)
            if mask_match:
                current_mask = mask_match.group(1)

    flush_current()
    return interfaces


def _detect_host_interfaces() -> tuple[list[dict], str | None, dict]:
    interfaces: list[dict] = []
    debug: dict = {"mode": "host_interfaces"}

    if _is_windows() and shutil.which("ipconfig"):
        try:
            result = subprocess.run(
                ["ipconfig", "/all"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=10,
            )
            debug["ipconfig_exit_code"] = result.returncode
            for item in _parse_windows_ipconfig(result.stdout):
                network = ipaddress.ip_network(item["cidr"], strict=False)
                host_ip = item["host_ip"]
                interfaces.append(
                    {
                        "label": item["label"],
                        "type": item["type"],
                        "cidr": str(network),
                        "hosts_found": 1,
                        "sample_hosts": [host_ip],
                        "reachable": True,
                    }
                )
        except Exception as exc:
            debug["ipconfig_error"] = str(exc)

    elif shutil.which("ip"):
        try:
            result = subprocess.run(
                ["ip", "-o", "-4", "addr", "show", "scope", "global"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            debug["ip_addr_exit_code"] = result.returncode
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) < 4 or parts[2] != "inet":
                    continue
                device = parts[1]
                address = parts[3]
                try:
                    interface = ipaddress.ip_interface(address)
                except ValueError:
                    continue
                network = interface.network
                if interface.ip.is_loopback:
                    continue
                interfaces.append(
                    {
                        "label": f"{device} ({network})",
                        "type": "direct" if interface.ip.is_link_local else "ethernet",
                        "cidr": str(network),
                        "hosts_found": 1,
                        "sample_hosts": [str(interface.ip)],
                        "reachable": True,
                    }
                )
        except Exception as exc:
            debug["ip_addr_error"] = str(exc)

    seen_cidrs: set[str] = set()
    deduped: list[dict] = []
    host_ip = None
    for interface in interfaces:
        cidr = interface.get("cidr")
        if not cidr or cidr in seen_cidrs:
            continue
        seen_cidrs.add(cidr)
        deduped.append(interface)
        sample_hosts = interface.get("sample_hosts") or []
        if not host_ip and sample_hosts:
            host_ip = sample_hosts[0]

    return deduped, host_ip, debug


def _parse_neighbor_table(stdout: str, subnet: str | None = None) -> list[dict[str, str | None]]:
    network = None
    if subnet:
        try:
            network = ipaddress.ip_network(subnet, strict=False)
        except ValueError:
            network = None

    entries: list[dict[str, str | None]] = []
    seen_ips: set[str] = set()
    current_device = None

    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        interface_match = re.match(r"^Interface:\s+(?P<dev>.+?)\s+---", line, re.IGNORECASE)
        if interface_match:
            current_device = interface_match.group("dev").strip()
            continue

        ip = None
        mac = None
        device = current_device
        state = None

        parts = line.split()
        if parts:
            try:
                ipaddress.ip_address(parts[0])
                ip = parts[0]
            except ValueError:
                ip = None

        if ip:
            if "dev" in parts:
                dev_index = parts.index("dev")
                if dev_index + 1 < len(parts):
                    device = parts[dev_index + 1]
            if "lladdr" in parts:
                mac_index = parts.index("lladdr")
                if mac_index + 1 < len(parts):
                    mac = _normalize_mac_address(parts[mac_index + 1])
            if not mac and len(parts) >= 2:
                mac = _normalize_mac_address(parts[1])
            last_token = parts[-1].strip().upper()
            if last_token.isalpha():
                state = last_token
        else:
            arp_match = re.search(
                r"\((?P<ip>[0-9a-fA-F:.]+)\)\s+at\s+(?P<mac>(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}|<incomplete>)(?:\s+\[[^\]]+\])?(?:\s+on\s+(?P<dev>\S+))?",
                line,
            )
            if arp_match:
                ip = arp_match.group("ip")
                device = arp_match.group("dev")
                raw_mac = arp_match.group("mac")
                mac = _normalize_mac_address(raw_mac) if raw_mac.lower() != "<incomplete>" else None
                state = "REACHABLE" if mac else "INCOMPLETE"

        if not ip or ip in seen_ips:
            continue

        try:
            ip_obj = ipaddress.ip_address(ip)
        except ValueError:
            continue

        if network and ip_obj not in network:
            continue

        if not mac or state in {"INCOMPLETE", "FAILED"}:
            continue
        if mac == "FF:FF:FF:FF:FF:FF":
            continue

        entries.append(
            {
                "ip": ip,
                "mac": mac,
                "vendor": _lookup_mac_vendor(mac) if mac else None,
                "device": device,
                "state": state,
            }
        )
        seen_ips.add(ip)

    return entries


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


def _validate_testssl_target(target: str) -> str:
    target = target.strip()
    if _is_valid_target(target):
        return target
    host = ""
    port_text = ""
    if target.startswith("[") and "]:" in target:
        host, port_text = target[1:].split("]:", 1)
    elif target.count(":") == 1:
        host, port_text = target.rsplit(":", 1)
    if not host or not port_text.isdigit():
        raise ValueError(f"Invalid target format: {target}")
    port = int(port_text)
    if port < 1 or port > 65535 or not _is_valid_target(host):
        raise ValueError(f"Invalid target format: {target}")
    return f"{host}:{port}"


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
    # nmap host-discovery probe flags that accept an inline port-list suffix
    # (e.g. "-PS22,80,443"). Strip the suffix before checking the allowlist.
    _NMAP_PROBE_PREFIXES = ("-PS", "-PA", "-PU", "-PY") if tool_name == "nmap" else ()
    # Port-list suffix must be digits, commas, and hyphens only (ranges OK).
    _PORT_SUFFIX_RE = re.compile(r"^[0-9,\-]+$")
    i = 0
    while i < len(sanitised):
        arg = sanitised[i]
        if arg.startswith("-"):
            flag = arg.split("=")[0]
            # Normalize probe-with-ports form to bare flag for allowlist check
            for prefix in _NMAP_PROBE_PREFIXES:
                if flag.startswith(prefix) and len(flag) > len(prefix):
                    suffix = flag[len(prefix):]
                    if not _PORT_SUFFIX_RE.match(suffix):
                        app.logger.warning(
                            "Blocked probe suffix '%s' for tool %s", suffix, tool_name
                        )
                        raise ValueError(
                            f"Invalid port-list suffix for {prefix}: '{suffix}'"
                        )
                    flag = prefix
                    break
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


def _is_ip_or_cidr_arg(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        pass
    try:
        ipaddress.ip_network(value, strict=False)
        return "/" in value
    except ValueError:
        return False


def _validate_no_extra_ip_targets(args: list[str], target: str, tool_name: str) -> None:
    allowed_targets = set(target.split())
    extras = [
        arg for arg in args
        if _is_ip_or_cidr_arg(arg) and arg not in allowed_targets
    ]
    if extras:
        raise ValueError(
            f"Unexpected positional target(s) in {tool_name} args: {', '.join(extras[:3])}"
        )


def _validate_hydra_target_arg(target: str, args: list[str]) -> None:
    try:
        ipaddress.ip_address(target)
    except ValueError:
        return
    target_args = [arg for arg in args if _is_ip_or_cidr_arg(arg)]
    if target_args != [target]:
        raise ValueError("Hydra args must include exactly the validated target and no other IP/CIDR targets")


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
            "stderr": _sanitize_stderr(stderr),
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
            "stderr": _internal_tool_error(),
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
        if tool_name == "nmap":
            target = _validate_targets(target)
        elif tool_name == "testssl":
            target = _validate_testssl_target(target)
        else:
            target = _validate_target(target)
    except ValueError:
        return None, None, None, ("Invalid target", 400)

    args = data.get("args", [])
    try:
        if tool_name:
            args = _validate_args_for_tool(args, tool_name)
        else:
            args = _validate_args(args)
    except ValueError:
        return None, None, None, ("Invalid scan arguments", 400)

    if tool_name in {"nmap", "testssl", "ssh-audit", "nikto", "snmpwalk"}:
        try:
            _validate_no_extra_ip_targets(args, target, tool_name)
        except ValueError as exc:
            return None, None, None, (str(exc), 400)

    try:
        timeout = min(int(data.get("timeout", 300)), 600)
    except (TypeError, ValueError):
        return None, None, None, ("'timeout' must be an integer", 400)

    return target, args, timeout, None


ESSENTIAL_TOOLS = {"nmap", "testssl", "ssh_audit", "hydra", "nikto", "snmpwalk"}


# ---------------------------------------------------------------------------
# Concurrency limit — max concurrent subprocess scans
# ---------------------------------------------------------------------------
def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        app.logger.warning("Invalid integer for %s; using %d", name, default)
        return default


_TOOL_VERSION_CACHE_TTL = _env_int("EDQ_TOOL_VERSION_CACHE_SECONDS", 300)
_TOOL_VERSION_TIMEOUT_SECONDS = _env_int("EDQ_TOOL_VERSION_TIMEOUT_SECONDS", 2)
_tool_version_cache: dict[str, object] = {"versions": None, "ts": 0.0}
_tool_version_lock = threading.Lock()


MAX_CONCURRENT_SCANS = _env_int("MAX_CONCURRENT_SCANS", 10)
_scan_semaphore = threading.Semaphore(MAX_CONCURRENT_SCANS)


# ---------------------------------------------------------------------------
# Per-target rate limiter — configurable max scans per target per minute.
# ---------------------------------------------------------------------------
_RATE_LIMIT_MAX = _env_int("EDQ_TOOLS_RATE_LIMIT_PER_TARGET_PER_MINUTE", 120)
_RATE_LIMIT_WINDOW = _env_int("EDQ_TOOLS_RATE_LIMIT_WINDOW_SECONDS", 60)
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


def _rate_limit_response() -> tuple[Response, int]:
    return jsonify({
        "error": f"Rate limit exceeded: max {_RATE_LIMIT_MAX} scans per target per {_RATE_LIMIT_WINDOW}s"
    }), 429


@app.route("/health", methods=["GET"])
def health() -> Response:
    tools_status = {}
    for key, binary in ALLOWED_TOOLS.items():
        tools_status[key] = _tool_available(binary)

    overall = "healthy" if all(tools_status.get(k) for k in ESSENTIAL_TOOLS) else "degraded"
    return jsonify({"status": overall, "tools": tools_status, "runtime": _runtime_info()})


@app.route("/", methods=["GET"])
def root() -> Response:
    """Browser-friendly scanner status page."""
    return jsonify({
        "service": "EDQ scanner agent",
        "status_endpoint": "/health",
        "authenticated_endpoints": [
            "/versions",
            "/detect-networks",
            "/scan/nmap",
            "/scan/ping",
            "/scan/tcp-probe",
            "/scan/neighbors",
        ],
        "note": "Use /health in a browser. Scan endpoints require X-Tools-Key.",
        "runtime": _runtime_info(),
    })


_NETWORK_DETECT_TCP_PORTS = (80, 443, 22, 445)
_NETWORK_DETECT_TCP_TIMEOUT = 0.2


def _tcp_probe(ip: str, ports: tuple = (80, 443, 53, 22, 8080, 8443), timeout: float = 0.35) -> bool:
    """Quick TCP connect probe — returns True if any port responds."""
    for port in ports:
        _probed_port, state = _tcp_probe_port_detail(ip, port, timeout)
        if state in {"open", "refused"}:
            return True
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
    in_docker = _running_in_docker()

    if not in_docker:
        interfaces, host_ip, debug_info = _detect_host_interfaces()
        return jsonify({
            "interfaces": interfaces,
            "host_ip": host_ip,
            "in_docker": False,
            "scanner_mode": "host",
            "scan_recommendation": (
                "Host scanner detected. Discovery, TCP probes, ARP lookup, and "
                "interface detection run from the host network namespace."
            ),
            "debug": debug_info,
        })

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
            found_ips = [
                ip
                for ip in probe_ips
                if _tcp_probe(
                    ip,
                    ports=_NETWORK_DETECT_TCP_PORTS,
                    timeout=_NETWORK_DETECT_TCP_TIMEOUT,
                )
            ]
            if found_ips:
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

            if not _env_truthy("EDQ_DETECT_NETWORKS_DEEP_SCAN"):
                continue

            # Slow path: try nmap TCP connect if socket probe failed
            try:
                result = subprocess.run(
                    ["nmap", "-sT", "-Pn", "--top-ports", "10", "-T4",
                     "--max-retries", "0", "--host-timeout", "2s"] + probe_ips,
                    capture_output=True, text=True, timeout=5,
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
            if gateway and _tcp_probe(
                gateway,
                ports=_NETWORK_DETECT_TCP_PORTS,
                timeout=_NETWORK_DETECT_TCP_TIMEOUT,
            ):
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
                    if _tcp_probe(
                        gw,
                        ports=_NETWORK_DETECT_TCP_PORTS,
                        timeout=_NETWORK_DETECT_TCP_TIMEOUT,
                    ):
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
    if _env_truthy("EDQ_DETECT_LINK_LOCAL_SCAN"):
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

    return jsonify({
        "interfaces": interfaces,
        "host_ip": host_ip,
        "in_docker": in_docker,
        "scanner_mode": "docker" if in_docker else "host",
        "scan_recommendation": (
            "Docker detected — EDQ will prefer raw SYN scans when privileges are available, "
            "otherwise it falls back to TCP connect (-sT -Pn)."
        ) if in_docker else None,
        "debug": debug_info,
    })


_TCP_REFUSED_ERRNOS = {
    errno.ECONNREFUSED,
    errno.ECONNRESET,
    10061,  # WSAECONNREFUSED
    10054,  # WSAECONNRESET
}


def _validate_tcp_ports(raw_ports) -> list[int]:
    if raw_ports is None:
        raw_ports = [80, 443, 22, 23, 554, 8080, 8443, 1883, 8883, 502, 47808]
    if not isinstance(raw_ports, list):
        raise ValueError("'ports' must be a list")

    ports: list[int] = []
    seen: set[int] = set()
    for raw_port in raw_ports:
        try:
            port = int(raw_port)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid TCP port: {raw_port}")
        if port < 1 or port > 65535:
            raise ValueError(f"Invalid TCP port: {port}")
        if port not in seen:
            seen.add(port)
            ports.append(port)
        if len(ports) >= 100:
            break

    if not ports:
        raise ValueError("At least one TCP port is required")
    return ports


def _expand_tcp_probe_targets(target: str, max_hosts: int) -> list[str]:
    target = str(target or "").strip()
    if not target:
        raise ValueError("Missing 'target' field")

    tokens = target.split()
    if len(tokens) > 1:
        if len(tokens) > max_hosts:
            raise ValueError(f"Too many probe targets; max {max_hosts}")
        expanded: list[str] = []
        for token in tokens:
            if not _is_valid_target(token):
                raise ValueError(f"Invalid target format: {token}")
            expanded.append(token)
        return expanded

    if not _is_valid_target(target):
        raise ValueError(f"Invalid target format: {target}")

    try:
        network = ipaddress.ip_network(target, strict=False)
    except ValueError:
        return [target]

    addresses = list(network) if network.prefixlen >= 31 else list(network.hosts())
    if len(addresses) > max_hosts:
        raise ValueError(f"Target expands to {len(addresses)} hosts; max {max_hosts}")
    return [str(address) for address in addresses]


def _tcp_probe_port_detail(ip: str, port: int, timeout: float) -> tuple[int, str]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, port))
        if result == 0:
            return port, "open"
        if result in _TCP_REFUSED_ERRNOS:
            return port, "refused"
        return port, "none"
    except OSError as exc:
        if getattr(exc, "errno", None) in _TCP_REFUSED_ERRNOS:
            return port, "refused"
        return port, "none"
    finally:
        try:
            sock.close()
        except Exception:
            pass


def _tcp_probe_host_detail(
    ip: str,
    ports: list[int],
    timeout: float,
    stop_on_first_open: bool = False,
) -> dict:
    responses: list[dict] = []
    open_ports: list[dict] = []
    first_refused_port: int | None = None

    for port in ports:
        probed_port, state = _tcp_probe_port_detail(ip, port, timeout)
        responses.append({"port": probed_port, "state": state})
        if state == "open":
            open_ports.append({"port": probed_port, "service": "", "version": ""})
            if stop_on_first_open:
                break
        elif state == "refused" and first_refused_port is None:
            first_refused_port = probed_port

    reachable = bool(open_ports) or first_refused_port is not None
    source = None
    if open_ports:
        source = f"tcp:{open_ports[0]['port']}"
    elif first_refused_port is not None:
        source = f"tcp_refused:{first_refused_port}"

    return {
        "ip": ip,
        "reachable": reachable,
        "source": source,
        "open_ports": open_ports,
        "responses": responses,
    }


@app.route("/scan/tcp-probe", methods=["POST"])
@require_api_key
def scan_tcp_probe() -> Union[Response, Tuple[Response, int]]:
    """Probe TCP reachability from the scanner agent network namespace."""
    data = request.get_json(force=True, silent=True)
    if not data or not data.get("target"):
        return jsonify({"error": "Missing 'target' field"}), 400

    try:
        max_hosts = min(max(int(data.get("max_hosts", 1024)), 1), 4096)
        concurrency = min(max(int(data.get("concurrency", 64)), 1), 256)
        connect_timeout = min(max(float(data.get("connect_timeout", 1.0)), 0.1), 10.0)
        stop_on_first_open = bool(data.get("stop_on_first_open", False))
        ports = _validate_tcp_ports(data.get("ports"))
        targets = _expand_tcp_probe_targets(str(data["target"]), max_hosts)
    except (TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400

    rate_key = targets[0] if targets else str(data["target"])
    if not _check_rate_limit(rate_key):
        return _rate_limit_response()

    started = time.time()
    results_by_ip: dict[str, dict] = {}
    workers = min(concurrency, max(len(targets), 1))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(
                _tcp_probe_host_detail,
                ip,
                ports,
                connect_timeout,
                stop_on_first_open,
            ): ip
            for ip in targets
        }
        for future in as_completed(future_map):
            ip = future_map[future]
            try:
                results_by_ip[ip] = future.result()
            except Exception as exc:
                results_by_ip[ip] = {
                    "ip": ip,
                    "reachable": False,
                    "source": None,
                    "open_ports": [],
                    "responses": [],
                    "error": str(exc),
                }

    hosts = [results_by_ip[ip] for ip in targets if ip in results_by_ip]
    return jsonify({
        "target": str(data["target"]),
        "ports": ports,
        "hosts": hosts,
        "duration_seconds": round(time.time() - started, 2),
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
        return _rate_limit_response()

    if not _scan_semaphore.acquire(blocking=False):
        return jsonify({"error": "Too many concurrent scans, please retry later"}), 503

    try:
        cmd = ["nmap"] + args + target.split()
        result = _run_tool(cmd, timeout, target=target)
        return jsonify(result)
    finally:
        _scan_semaphore.release()


@app.route("/scan/testssl", methods=["POST"])
@require_api_key
def scan_testssl() -> Union[Response, Tuple[Response, int]]:
    target, args, timeout, err = _parse_scan_request(tool_name="testssl")
    if err:
        return jsonify({"error": err[0]}), err[1]

    if not _tool_available("testssl.sh"):
        return jsonify({"error": "testssl.sh not available"}), 503

    if not _check_rate_limit(target):
        return _rate_limit_response()

    if not _scan_semaphore.acquire(blocking=False):
        return jsonify({"error": "Too many concurrent scans, please retry later"}), 503

    try:
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
    finally:
        _scan_semaphore.release()


@app.route("/scan/ssh-audit", methods=["POST"])
@require_api_key
def scan_ssh_audit() -> Union[Response, Tuple[Response, int]]:
    target, args, timeout, err = _parse_scan_request(tool_name="ssh-audit")
    if err:
        return jsonify({"error": err[0]}), err[1]

    if not _tool_available("ssh-audit"):
        return jsonify({"error": "ssh-audit not available"}), 503

    if not _check_rate_limit(target):
        return _rate_limit_response()

    if not _scan_semaphore.acquire(blocking=False):
        return jsonify({"error": "Too many concurrent scans, please retry later"}), 503

    try:
        cmd = ["ssh-audit"] + args + [target]
        result = _run_tool(cmd, timeout, target=target)
        return jsonify(result)
    finally:
        _scan_semaphore.release()


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
        return _rate_limit_response()

    if not _scan_semaphore.acquire(blocking=False):
        return jsonify({"error": "Too many concurrent scans, please retry later"}), 503

    try:
        # Do not append target — the caller includes target+service in args
        _validate_hydra_target_arg(target, args)
        cmd = ["hydra"] + args
        result = _run_tool(cmd, timeout, target=target)
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        _scan_semaphore.release()


@app.route("/scan/nikto", methods=["POST"])
@require_api_key
def scan_nikto() -> Union[Response, Tuple[Response, int]]:
    target, args, timeout, err = _parse_scan_request(tool_name="nikto")
    if err:
        return jsonify({"error": err[0]}), err[1]

    if not _tool_available("nikto"):
        return jsonify({"error": "nikto not available"}), 503

    if not _check_rate_limit(target):
        return _rate_limit_response()

    if not _scan_semaphore.acquire(blocking=False):
        return jsonify({"error": "Too many concurrent scans, please retry later"}), 503

    try:
        cmd = ["nikto"] + args + ["-h", target]
        result = _run_tool(cmd, timeout, target=target)
        return jsonify(result)
    finally:
        _scan_semaphore.release()


@app.route("/scan/snmpwalk", methods=["POST"])
@require_api_key
def scan_snmpwalk() -> Union[Response, Tuple[Response, int]]:
    target, args, timeout, err = _parse_scan_request(tool_name="snmpwalk")
    if err:
        return jsonify({"error": err[0]}), err[1]

    if not _tool_available("snmpwalk"):
        return jsonify({"error": "snmpwalk not available"}), 503

    if not _check_rate_limit(target):
        return _rate_limit_response()

    if not _scan_semaphore.acquire(blocking=False):
        return jsonify({"error": "Too many concurrent scans, please retry later"}), 503

    try:
        cmd = ["snmpwalk"] + args + [target]
        result = _run_tool(cmd, timeout, target=target)
        return jsonify(result)
    finally:
        _scan_semaphore.release()


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
        return _rate_limit_response()

    try:
        count = min(int(data.get("count", 3)), 10)
        timeout = min(int(data.get("timeout", 30)), 60)
    except (TypeError, ValueError):
        return jsonify({"error": "'count' and 'timeout' must be integers"}), 400

    cmd = ["ping", "-n", str(count), "-w", "2000", target] if _is_windows() else ["ping", "-c", str(count), "-W", "2", target]
    result = _run_tool(cmd, timeout)
    return jsonify(result)


@app.route("/scan/arp-cache", methods=["POST"])
@require_api_key
def scan_arp_cache() -> Union[Response, Tuple[Response, int]]:
    """Ping a target to populate ARP cache, then read the MAC address."""
    data = request.get_json(force=True, silent=True)
    if not data or not data.get("target"):
        return jsonify({"error": "Missing 'target' field"}), 400

    try:
        target = _validate_target(data["target"])
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    if not _check_rate_limit(target):
        return _rate_limit_response()

    # Step 1: ping to populate ARP cache
    ping_cmd = ["ping", "-n", "1", "-w", "2000", target] if _is_windows() else ["ping", "-c", "1", "-W", "2", target]
    _run_tool(ping_cmd, timeout=5)

    # Step 2: read ARP cache
    if _is_windows() and shutil.which("arp"):
        result = _run_tool(["arp", "-a", target], timeout=5)
    elif shutil.which("ip"):
        result = _run_tool(["ip", "neigh", "show", target], timeout=5)
    elif shutil.which("arp"):
        result = _run_tool(["arp", "-an"], timeout=5)
    else:
        return jsonify({"error": "Neighbor table tool unavailable"}), 503
    result["entries"] = _parse_neighbor_table(result.get("stdout", ""), target)
    return jsonify(result)


@app.route("/scan/neighbors", methods=["POST"])
@require_api_key
def scan_neighbors() -> Union[Response, Tuple[Response, int]]:
    data = request.get_json(force=True, silent=True) or {}
    subnet = data.get("subnet")
    if subnet is not None:
        try:
            subnet = str(ipaddress.ip_network(str(subnet), strict=False))
        except ValueError:
            return jsonify({"error": "Invalid subnet"}), 400

    rate_key = subnet or "__neighbors__"
    if not _check_rate_limit(rate_key):
        return _rate_limit_response()

    if shutil.which("ip"):
        result = _run_tool(["ip", "neigh", "show"], timeout=5)
    elif shutil.which("arp"):
        arp_args = ["arp", "-a"] if os.name == "nt" else ["arp", "-an"]
        result = _run_tool(arp_args, timeout=5)
    else:
        return jsonify({"error": "Neighbor table tool unavailable"}), 503

    result["entries"] = _parse_neighbor_table(result.get("stdout", ""), subnet)
    if subnet:
        result["subnet"] = subnet
    return jsonify(result)


@app.route("/scan/mac-vendor", methods=["POST"])
@require_api_key
def scan_mac_vendor() -> Union[Response, Tuple[Response, int]]:
    data = request.get_json(force=True, silent=True)
    if not data or not data.get("mac"):
        return jsonify({"error": "Missing 'mac' field"}), 400

    prefix = _normalize_mac_prefix(str(data["mac"]))
    if not prefix:
        return jsonify({"error": "Invalid MAC address"}), 400

    vendor = _lookup_mac_vendor(prefix)
    return jsonify({"mac_prefix": prefix, "vendor": vendor})


@app.route("/versions", methods=["GET"])
@require_api_key
def tool_versions() -> Response:
    """Return installed tool versions."""
    now = time.time()
    with _tool_version_lock:
        cached_versions = _tool_version_cache.get("versions")
        cached_at = float(_tool_version_cache.get("ts") or 0.0)
        if isinstance(cached_versions, dict) and now - cached_at < _TOOL_VERSION_CACHE_TTL:
            return jsonify({"versions": cached_versions, "cached": True})

    version_cmds = {
        "nmap": ["nmap", "--version"],
        "testssl": ["testssl.sh", "--version"],
        "ssh_audit": ["ssh-audit", "--help"],
        "hydra": ["hydra", "-h"],
        "nikto": ["nikto", "-Version"],
        "snmpwalk": ["snmpwalk", "-V"],
    }
    versions = {}
    for tool, cmd in version_cmds.items():
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=_TOOL_VERSION_TIMEOUT_SECONDS,
            )
            output = result.stdout.strip() or result.stderr.strip()
            versions[tool] = _clean_version_output(output) if output else "installed"
        except subprocess.TimeoutExpired:
            versions[tool] = "installed" if _tool_available(ALLOWED_TOOLS.get(tool, tool)) else "unavailable"
        except Exception:
            versions[tool] = "unavailable"
    with _tool_version_lock:
        _tool_version_cache["versions"] = dict(versions)
        _tool_version_cache["ts"] = now
    return jsonify({"versions": versions})


# Pinned latest-known versions — update these when rebuilding the image
LATEST_KNOWN_VERSIONS = {
    "nmap": "7.95",
    "testssl": "3.2.3",
    "ssh_audit": "3.3.0",
    "hydra": "9.5",
    "nikto": "2.6.0",
    "snmpwalk": "5.9.3",
}

_VERSION_PARSE = {
    "nmap": re.compile(r"Nmap version ([\d.]+)"),
    "testssl": re.compile(r"testssl\.sh\s+(?:version\s+)?([\d.]+)", re.IGNORECASE),
    "ssh_audit": re.compile(r"ssh-audit\s+v([\d.]+)", re.IGNORECASE),
    "hydra": re.compile(r"Hydra v([\d.]+)"),
    "nikto": re.compile(r"Nikto\s+v?([\d.]+)"),
    "snmpwalk": re.compile(r"NET-SNMP version:\s*([\d.]+)"),
}


_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _clean_version_output(output: str) -> str:
    cleaned = _ANSI_ESCAPE_RE.sub("", output or "")
    for line in cleaned.splitlines():
        line = line.strip()
        if line and any(char.isalnum() for char in line):
            return line[:100]
    return "installed"


def _parse_installed_version(tool: str, output: str) -> str | None:
    cleaned = _ANSI_ESCAPE_RE.sub("", output or "")
    pattern = _VERSION_PARSE.get(tool)
    if not pattern:
        return None
    match = pattern.search(cleaned)
    return match.group(1).strip().rstrip(".") if match else None


def _version_parts(value: str | None) -> tuple[int, ...] | None:
    if not value or value == "unknown":
        return None
    parts = [int(part) for part in re.findall(r"\d+", value)]
    return tuple(parts) if parts else None


def _is_installed_version_current(installed: str | None, latest: str) -> bool | None:
    installed_parts = _version_parts(installed)
    latest_parts = _version_parts(latest)
    if installed_parts is None or latest_parts is None:
        return None
    max_len = max(len(installed_parts), len(latest_parts))
    installed_padded = installed_parts + (0,) * (max_len - len(installed_parts))
    latest_padded = latest_parts + (0,) * (max_len - len(latest_parts))
    return installed_padded >= latest_padded


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
        "snmpwalk": ["snmpwalk", "-V"],
    }
    results = {}
    for tool, cmd in version_cmds.items():
        installed = None
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            output = (proc.stdout.strip() or proc.stderr.strip())
            if output:
                installed = _parse_installed_version(tool, output)
        except Exception:
            pass

        latest = LATEST_KNOWN_VERSIONS.get(tool, "unknown")
        up_to_date = _is_installed_version_current(installed, latest)
        results[tool] = {
            "installed": installed or "unknown",
            "latest_known": latest,
            "up_to_date": up_to_date,
            "action": (
                "none"
                if up_to_date is True
                else "rebuild image to update"
                if up_to_date is False
                else "check manually"
            ),
        }

    any_outdated = any(r["up_to_date"] is False for r in results.values())
    any_unknown = any(r["up_to_date"] is None for r in results.values())
    return jsonify({
        "tools": results,
        "image_rebuild_recommended": any_outdated,
        "update_instructions": (
            "Run 'docker compose up -d --build backend' to rebuild with latest pinned scanner versions. "
            "Do not auto-update tools at runtime; untested versions may break scans."
        ) if any_outdated else (
            "One or more scanner versions could not be parsed; check the scanner image manually."
            if any_unknown else
            "All scanner tools are at or above the image's latest-known pinned versions."
        ),
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
    import queue
    import threading

    start = time.time()
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    stderr_text = ""
    exit_code = -1
    proc = None
    stderr_in_traceback = False
    events: "queue.Queue[tuple[str, str]]" = queue.Queue()

    def _reader(stream, stream_name: str) -> None:
        try:
            for line in iter(stream.readline, ""):
                events.put((stream_name, line))
        finally:
            try:
                stream.close()
            except Exception:
                pass

    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            bufsize=1,  # line-buffered
        )
        if target:
            _track_proc(target, proc)

        readers = []
        if proc.stdout:
            readers.append(threading.Thread(target=_reader, args=(proc.stdout, "stdout"), daemon=True))
        if proc.stderr:
            readers.append(threading.Thread(target=_reader, args=(proc.stderr, "stderr"), daemon=True))
        for reader in readers:
            reader.start()

        deadline = time.monotonic() + timeout
        timed_out = False
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 and proc.poll() is None:
                timed_out = True
                proc.kill()
                break

            try:
                stream_name, line = events.get(timeout=min(max(remaining, 0.0), 0.25))
            except queue.Empty:
                if proc.poll() is not None:
                    break
                continue

            if stream_name == "stdout":
                stdout_lines.append(line)
                yield f"data: {_json.dumps({'type': 'stdout', 'line': line})}\n\n"
            else:
                safe_line, stderr_in_traceback = _sanitize_stderr_line(line, stderr_in_traceback)
                if safe_line:
                    stderr_lines.append(safe_line)
                    yield f"data: {_json.dumps({'type': 'stderr', 'line': safe_line})}\n\n"

        proc.wait(timeout=5)

        for reader in readers:
            reader.join(timeout=1.0)

        # Drain any lines read just before process exit/kill.
        while True:
            try:
                stream_name, line = events.get_nowait()
            except queue.Empty:
                break
            if stream_name == "stdout":
                stdout_lines.append(line)
                yield f"data: {_json.dumps({'type': 'stdout', 'line': line})}\n\n"
            else:
                safe_line, stderr_in_traceback = _sanitize_stderr_line(line, stderr_in_traceback)
                if safe_line:
                    stderr_lines.append(safe_line)
                    yield f"data: {_json.dumps({'type': 'stderr', 'line': safe_line})}\n\n"

        exit_code = -1 if timed_out else proc.returncode
        stderr_text = _sanitize_stderr("\n".join(stderr_lines))
        if timed_out:
            timeout_msg = f"Command timed out after {timeout}s"
            stderr_text = f"{stderr_text}\n{timeout_msg}".strip()
    except Exception as e:
        if proc and proc.poll() is None:
            proc.kill()
            proc.wait()
        stderr_text = _internal_tool_error()
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
        return _rate_limit_response()
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
        return _rate_limit_response()
    if not _scan_semaphore.acquire(blocking=False):
        return jsonify({"error": "Too many concurrent scans, please retry later"}), 503

    # Create temp file for JSON output like the sync endpoint
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        json_output_path = tmp.name

    def _stream_testssl_gen():
        import json as _json
        import queue

        start = time.time()
        stdout_lines = []
        stderr_lines = []
        stderr_text = ""
        exit_code = -1
        proc = None
        stderr_in_traceback = False
        events: "queue.Queue[tuple[str, str]]" = queue.Queue()

        def _reader(stream, stream_name: str) -> None:
            try:
                for line in iter(stream.readline, ""):
                    events.put((stream_name, line))
            finally:
                try:
                    stream.close()
                except Exception:
                    pass

        try:
            cmd = ["testssl.sh", "--jsonfile", json_output_path] + args + [target]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
            _track_proc(target, proc)

            readers = []
            if proc.stdout:
                readers.append(threading.Thread(target=_reader, args=(proc.stdout, "stdout"), daemon=True))
            if proc.stderr:
                readers.append(threading.Thread(target=_reader, args=(proc.stderr, "stderr"), daemon=True))
            for reader in readers:
                reader.start()

            deadline = time.monotonic() + timeout
            timed_out = False
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0 and proc.poll() is None:
                    timed_out = True
                    proc.kill()
                    break

                try:
                    stream_name, line = events.get(timeout=min(max(remaining, 0.0), 0.25))
                except queue.Empty:
                    if proc.poll() is not None:
                        break
                    continue

                if stream_name == "stdout":
                    stdout_lines.append(line)
                    yield f"data: {_json.dumps({'type': 'stdout', 'line': line})}\n\n"
                else:
                    safe_line, stderr_in_traceback = _sanitize_stderr_line(line, stderr_in_traceback)
                    if safe_line:
                        stderr_lines.append(safe_line)
                        yield f"data: {_json.dumps({'type': 'stderr', 'line': safe_line})}\n\n"

            proc.wait(timeout=5)
            for reader in readers:
                reader.join(timeout=1.0)

            while True:
                try:
                    stream_name, line = events.get_nowait()
                except queue.Empty:
                    break
                if stream_name == "stdout":
                    stdout_lines.append(line)
                    yield f"data: {_json.dumps({'type': 'stdout', 'line': line})}\n\n"
                else:
                    safe_line, stderr_in_traceback = _sanitize_stderr_line(line, stderr_in_traceback)
                    if safe_line:
                        stderr_lines.append(safe_line)
                        yield f"data: {_json.dumps({'type': 'stderr', 'line': safe_line})}\n\n"

            exit_code = -1 if timed_out else proc.returncode
            stderr_text = _sanitize_stderr("\n".join(stderr_lines))
            if timed_out:
                timeout_msg = f"Command timed out after {timeout}s"
                stderr_text = f"{stderr_text}\n{timeout_msg}".strip()
        except Exception as e:
            if proc and proc.poll() is None:
                proc.kill()
                proc.wait()
            stderr_text = _internal_tool_error()
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
        return _rate_limit_response()
    if not _scan_semaphore.acquire(blocking=False):
        return jsonify({"error": "Too many concurrent scans, please retry later"}), 503
    cmd = ["ssh-audit"] + args + [target]
    return Response(
        _guarded_stream(_run_tool_stream(cmd, timeout, target=target)),
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
        return _rate_limit_response()
    if not _scan_semaphore.acquire(blocking=False):
        return jsonify({"error": "Too many concurrent scans, please retry later"}), 503
    # Do not append target — the caller includes target+service in args
    try:
        _validate_hydra_target_arg(target, args)
    except ValueError:
        _scan_semaphore.release()
        return jsonify({"error": "Invalid hydra target arguments"}), 400
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
        return _rate_limit_response()
    if not _scan_semaphore.acquire(blocking=False):
        return jsonify({"error": "Too many concurrent scans, please retry later"}), 503
    cmd = ["nikto"] + args + ["-h", target]
    return Response(
        _guarded_stream(_run_tool_stream(cmd, timeout, target=target)),
        mimetype="text/event-stream",
    )


@app.route("/stream/snmpwalk", methods=["POST"])
@require_api_key
def stream_snmpwalk() -> Union[Response, Tuple[Response, int]]:
    target, args, timeout, err = _parse_scan_request(tool_name="snmpwalk")
    if err:
        return jsonify({"error": err[0]}), err[1]
    if not _tool_available("snmpwalk"):
        return jsonify({"error": "snmpwalk not available"}), 503
    if not _check_rate_limit(target):
        return _rate_limit_response()
    if not _scan_semaphore.acquire(blocking=False):
        return jsonify({"error": "Too many concurrent scans, please retry later"}), 503
    cmd = ["snmpwalk"] + args + [target]
    return Response(
        _guarded_stream(_run_tool_stream(cmd, timeout, target=target)),
        mimetype="text/event-stream",
    )


# Production entry point — use gunicorn in Docker (see Dockerfile CMD).
# This block is only used for local development.
if __name__ == "__main__":
    host = os.environ.get("EDQ_SCANNER_HOST", "0.0.0.0")
    port = int(os.environ.get("EDQ_SCANNER_PORT", os.environ.get("PORT", "8001")))
    app.run(host=host, port=port, debug=False)
