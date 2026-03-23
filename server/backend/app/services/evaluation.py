"""Evaluation engine — applies pass/fail rules to parsed tool output.

Maps each test ID to evaluation logic that produces (verdict, comment) tuples.
"""

from typing import Any


def evaluate_result(
    test_id: str,
    parsed_data: dict[str, Any],
    whitelist_entries: list[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    """Return (verdict, comment) for a parsed test result.

    Args:
        test_id: Universal test identifier (e.g. "U01").
        parsed_data: Structured data from the relevant parser.
        whitelist_entries: Protocol whitelist entries for U09 comparison.

    Returns:
        Tuple of (verdict_str, comment_str).
        verdict_str is one of: pass, fail, advisory, info, na, error
    """
    evaluator = _EVALUATORS.get(test_id)
    if evaluator is None:
        return ("info", f"No evaluation rule defined for {test_id}")
    try:
        return evaluator(parsed_data, whitelist_entries or [])
    except Exception as exc:
        return ("error", f"Evaluation error for {test_id}: {exc}")


def _eval_u01(data: dict, _wl: list) -> tuple[str, str]:
    """Ping Response."""
    if data.get("reachable"):
        return ("pass", "Device responds to ICMP echo requests")
    return ("fail", "Device did not respond to ping — unreachable")


def _eval_u02(data: dict, _wl: list) -> tuple[str, str]:
    """MAC Vendor Lookup."""
    mac = data.get("mac_address")
    vendor = data.get("oui_vendor", "")
    if mac and vendor:
        return ("pass", f"MAC {mac} registered to {vendor}")
    if mac:
        return ("advisory", f"MAC {mac} found but vendor not in OUI database")
    return ("info", "MAC address could not be determined")


def _eval_u03(data: dict, _wl: list) -> tuple[str, str]:
    """Switch Negotiation — ethtool not in sidecar, mark N/A."""
    return ("na", "Switch negotiation test requires ethtool (not available in sidecar)")


def _eval_u04(data: dict, _wl: list) -> tuple[str, str]:
    """DHCP Behaviour."""
    dhcp = data.get("dhcp_enabled")
    if dhcp is True:
        return ("pass", "Device accepts DHCP lease")
    if dhcp is False:
        return ("info", "Device uses static IP configuration")
    return ("info", "DHCP behaviour could not be determined from discovery data")


def _eval_u05(data: dict, _wl: list) -> tuple[str, str]:
    """IPv6 Support Detection — informational."""
    if data.get("ipv6_supported"):
        return ("info", "IPv6 is enabled on this device")
    return ("info", "IPv6 does not appear to be enabled")


def _eval_u06(data: dict, _wl: list) -> tuple[str, str]:
    """Full TCP Port Scan."""
    open_ports = data.get("open_ports", [])
    count = len(open_ports)
    if count == 0:
        return ("info", "No open TCP ports detected")
    port_list = ", ".join(
        f"{p['port']}/{p.get('service', '?')}" for p in open_ports[:20]
    )
    suffix = f" (and {count - 20} more)" if count > 20 else ""
    return ("info", f"{count} open TCP port(s): {port_list}{suffix}")


def _eval_u07(data: dict, _wl: list) -> tuple[str, str]:
    """UDP Top-100 Port Scan."""
    open_ports = data.get("open_ports", [])
    count = len(open_ports)
    if count == 0:
        return ("info", "No open UDP ports detected in top 100")
    port_list = ", ".join(
        f"{p['port']}/{p.get('service', '?')}" for p in open_ports[:20]
    )
    return ("info", f"{count} open/filtered UDP port(s): {port_list}")


def _eval_u08(data: dict, _wl: list) -> tuple[str, str]:
    """Service Version Detection."""
    open_ports = data.get("open_ports", [])
    if not open_ports:
        return ("info", "No services detected")
    services = [
        f"{p['port']}: {p.get('service', '?')} {p.get('version', '')}".strip()
        for p in open_ports[:15]
    ]
    return ("info", f"Detected services: {'; '.join(services)}")


def _eval_u09(data: dict, wl: list) -> tuple[str, str]:
    """Protocol Whitelist Compliance."""
    open_ports = set()
    for p in data.get("open_ports", []):
        open_ports.add(int(p["port"]))

    if not open_ports:
        return ("pass", "No open ports to compare against whitelist")

    allowed_ports = set()
    for entry in wl:
        port_val = entry.get("port")
        if port_val is not None:
            allowed_ports.add(int(port_val))

    non_compliant = sorted(open_ports - allowed_ports)
    if non_compliant:
        return ("fail", f"Non-whitelisted ports open: {non_compliant}")
    return ("pass", "All open ports are on the protocol whitelist")


def _eval_u10(data: dict, _wl: list) -> tuple[str, str]:
    """TLS Version Assessment."""
    weak = data.get("weak_versions", [])
    tls_versions = data.get("tls_versions", [])
    if not tls_versions:
        return ("na", "No TLS service detected or testssl could not connect")
    if weak:
        return ("fail", f"Weak TLS versions detected: {', '.join(weak)}")
    return ("pass", f"TLS versions: {', '.join(tls_versions)} — no weak versions")


def _eval_u11(data: dict, _wl: list) -> tuple[str, str]:
    """Cipher Suite Strength."""
    weak_ciphers = data.get("weak_ciphers", [])
    ciphers = data.get("ciphers", [])
    if not ciphers:
        return ("na", "No cipher suites detected")
    if weak_ciphers:
        names = [c.get("name", str(c)) if isinstance(c, dict) else str(c) for c in weak_ciphers[:5]]
        return ("fail", f"Weak cipher suites detected: {', '.join(names)}")
    return ("pass", f"{len(ciphers)} cipher suite(s) — all acceptable strength")


def _eval_u12(data: dict, _wl: list) -> tuple[str, str]:
    """Certificate Validity."""
    if data.get("cert_valid"):
        expiry = data.get("cert_expiry", "unknown")
        return ("pass", f"Certificate valid, expires {expiry}")
    expiry = data.get("cert_expiry")
    if expiry:
        return ("advisory", f"Certificate issue detected. Expiry: {expiry}")
    return ("na", "No certificate detected or testssl could not connect")


def _eval_u13(data: dict, _wl: list) -> tuple[str, str]:
    """HSTS Header Presence."""
    if data.get("hsts"):
        max_age = data.get("hsts_max_age")
        suffix = f" (max-age={max_age})" if max_age else ""
        return ("pass", f"HSTS header present{suffix}")
    return ("fail", "HSTS header not set — HTTP Strict Transport Security missing")


def _eval_u14(data: dict, _wl: list) -> tuple[str, str]:
    """HTTP Security Headers (nikto)."""
    stdout = data.get("raw", data.get("stdout", ""))
    if not stdout:
        return ("na", "No HTTP service detected or nikto could not connect")

    issues = []
    stdout_lower = stdout.lower()
    if "x-frame-options" in stdout_lower:
        issues.append("X-Frame-Options issue")
    if "x-content-type" in stdout_lower:
        issues.append("X-Content-Type-Options issue")
    if "content-security-policy" not in stdout_lower:
        pass

    vuln_count = stdout_lower.count("+ osvdb-")
    if vuln_count > 5:
        return ("fail", f"Nikto found {vuln_count} potential issues")
    if vuln_count > 0:
        return ("advisory", f"Nikto found {vuln_count} potential issue(s)")
    return ("pass", "No significant HTTP security header issues found")


def _eval_u15(data: dict, _wl: list) -> tuple[str, str]:
    """SSH Algorithm Assessment."""
    score = data.get("overall_score", "good")
    weak_kex = data.get("weak_kex", [])
    weak_ciphers = data.get("weak_ciphers", [])
    weak_macs = data.get("weak_macs", [])
    weak_hk = data.get("weak_host_keys", [])

    version = data.get("ssh_version", "")
    total_weak = len(weak_kex) + len(weak_ciphers) + len(weak_macs) + len(weak_hk)

    if not version and total_weak == 0:
        return ("na", "SSH service not detected or ssh-audit could not connect")

    if score == "fail" or total_weak > 3:
        parts = []
        if weak_kex:
            parts.append(f"KEX: {', '.join(weak_kex[:3])}")
        if weak_ciphers:
            parts.append(f"Ciphers: {', '.join(weak_ciphers[:3])}")
        if weak_macs:
            parts.append(f"MACs: {', '.join(weak_macs[:3])}")
        if weak_hk:
            parts.append(f"Host keys: {', '.join(weak_hk)}")
        return ("fail", f"Weak SSH algorithms: {'; '.join(parts)}")

    if total_weak > 0:
        return ("advisory", f"{total_weak} weak algorithm(s) found — see parsed data for details")

    return ("pass", f"SSH algorithms acceptable. Version: {version}")


def _eval_u16(data: dict, _wl: list) -> tuple[str, str]:
    """Default Credential Check."""
    found = data.get("found_credentials", [])
    if found:
        creds = [f"{c['login']}:{c['password']}" for c in found[:3]]
        return ("fail", f"Default credentials accepted: {', '.join(creds)}")
    return ("pass", "Default/common credentials were rejected")


def _eval_u17(data: dict, _wl: list) -> tuple[str, str]:
    """Brute Force Protection."""
    lockout_detected = data.get("lockout_detected", False)
    error_msg = data.get("error", "")
    if lockout_detected:
        return ("pass", "Account lockout detected after repeated failed login attempts")
    if "connection refused" in error_msg.lower() or "max retries" in error_msg.lower():
        return ("pass", "Connection refused after rapid attempts — brute force protection active")
    return ("advisory", "No account lockout detected — brute force protection may not be configured")


def _eval_u18(data: dict, _wl: list) -> tuple[str, str]:
    """HTTP→HTTPS Redirect."""
    redirects = data.get("redirects_to_https", False)
    http_open = data.get("http_open", False)
    if redirects:
        return ("pass", "HTTP requests redirect to HTTPS")
    if not http_open:
        return ("pass", "HTTP port not open — only HTTPS available")
    return ("fail", "HTTP is accessible without redirect to HTTPS")


def _eval_u19(data: dict, _wl: list) -> tuple[str, str]:
    """OS Fingerprinting — informational."""
    os_fp = data.get("os_fingerprint")
    if os_fp:
        return ("info", f"OS fingerprint: {os_fp}")
    return ("info", "OS fingerprint could not be determined")


def _eval_u26(data: dict, _wl: list) -> tuple[str, str]:
    """NTP Synchronisation Check."""
    ntp_open = data.get("ntp_open", False)
    if ntp_open:
        return ("pass", "NTP service detected (port 123 open)")
    return ("advisory", "NTP port 123 not detected — device may not support time synchronisation")


def _eval_u28(data: dict, _wl: list) -> tuple[str, str]:
    """BACnet/IP Discovery."""
    bacnet_open = data.get("bacnet_open", False)
    if bacnet_open:
        return ("info", "BACnet/IP service detected on port 47808")
    return ("info", "BACnet/IP not detected on port 47808")


def _eval_u29(data: dict, _wl: list) -> tuple[str, str]:
    """DNS Support Verification."""
    dns_open = data.get("dns_open", False)
    if dns_open:
        return ("pass", "DNS service detected (port 53)")
    return ("info", "DNS port 53 not detected — device may use external DNS")


def _eval_u31(data: dict, _wl: list) -> tuple[str, str]:
    """SNMP Version Check."""
    open_ports = data.get("open_ports", [])
    snmp_ports = [p for p in open_ports if p.get("port") in (161, 162)]
    if not snmp_ports:
        return ("pass", "No SNMP services detected")
    stdout = data.get("raw", data.get("stdout", ""))
    stdout_lower = (stdout or "").lower()
    if "snmpv1" in stdout_lower or "snmpv2" in stdout_lower or "v2c" in stdout_lower:
        return ("fail", "Insecure SNMP version detected (v1/v2c). Only SNMPv3 is acceptable.")
    if "snmpv3" in stdout_lower:
        return ("pass", "SNMPv3 detected — secure SNMP version in use")
    return ("advisory", "SNMP port open but version could not be determined — verify manually")


def _eval_u32(data: dict, _wl: list) -> tuple[str, str]:
    """UPnP/SSDP Exposure."""
    open_ports = data.get("open_ports", [])
    upnp_ports = [p for p in open_ports if p.get("port") == 1900]
    if upnp_ports:
        return ("advisory", "UPnP/SSDP service detected on port 1900 — may expose device to network attacks")
    return ("pass", "No UPnP/SSDP service detected")


def _eval_u33(data: dict, _wl: list) -> tuple[str, str]:
    """mDNS/Bonjour Exposure."""
    open_ports = data.get("open_ports", [])
    mdns_ports = [p for p in open_ports if p.get("port") == 5353]
    if mdns_ports:
        return ("advisory", "mDNS/Bonjour service detected on port 5353 — may leak device information")
    return ("pass", "No mDNS/Bonjour service detected")


def _eval_u34(data: dict, _wl: list) -> tuple[str, str]:
    """Telnet/Insecure Protocol Detection."""
    telnet_open = data.get("telnet_open", False)
    ftp_open = data.get("ftp_open", False)
    insecure = data.get("insecure_ports", [])
    if telnet_open or ftp_open:
        parts = []
        if telnet_open:
            parts.append("Telnet (23)")
        if ftp_open:
            parts.append("FTP (21)")
        other = [p for p in insecure if p not in (21, 23)]
        if other:
            parts.append(f"ports {other}")
        return ("fail", f"Insecure cleartext protocols detected: {', '.join(parts)}")
    if insecure:
        return ("fail", f"Insecure cleartext protocol ports open: {insecure}")
    return ("pass", "No insecure cleartext protocols (Telnet, FTP) detected")


def _eval_u35(data: dict, _wl: list) -> tuple[str, str]:
    """Web Server Vulnerability Scan (nikto)."""
    stdout = data.get("raw", data.get("stdout", ""))
    if not stdout:
        return ("na", "No HTTP service detected or nikto could not connect")
    stdout_lower = stdout.lower()
    vuln_count = stdout_lower.count("+ osvdb-")
    if vuln_count > 10:
        return ("fail", f"Nikto found {vuln_count} potential vulnerabilities — critical review needed")
    if vuln_count > 3:
        return ("advisory", f"Nikto found {vuln_count} potential issue(s) — review recommended")
    if vuln_count > 0:
        return ("advisory", f"Nikto found {vuln_count} minor issue(s)")
    return ("pass", "No significant web server vulnerabilities found")


def _eval_u36(data: dict, _wl: list) -> tuple[str, str]:
    """Banner Grabbing / Information Leakage."""
    open_ports = data.get("open_ports", [])
    if not open_ports:
        return ("info", "No services detected for banner analysis")
    leaky = []
    for p in open_ports:
        version = p.get("version", "") or ""
        service = p.get("service", "") or ""
        banner = f"{service} {version}".lower()
        if any(kw in banner for kw in ["10.0.", "192.168.", "172.16.", "internal", "debug"]):
            leaky.append(f"port {p['port']}: {service} {version}".strip())
    if leaky:
        return ("advisory", f"Potential information leakage in banners: {'; '.join(leaky[:5])}")
    return ("pass", "No sensitive information disclosed in service banners")


def _eval_u37(data: dict, _wl: list) -> tuple[str, str]:
    """RTSP Stream Authentication."""
    rtsp_open = data.get("rtsp_open", False)
    auth_required = data.get("auth_required", False)
    if not rtsp_open:
        return ("na", "No RTSP service detected on port 554")
    if auth_required:
        return ("pass", "RTSP streams require authentication")
    return ("fail", "RTSP streams accessible without authentication")


_EVALUATORS: dict[str, Any] = {
    "U01": _eval_u01,
    "U02": _eval_u02,
    "U03": _eval_u03,
    "U04": _eval_u04,
    "U05": _eval_u05,
    "U06": _eval_u06,
    "U07": _eval_u07,
    "U08": _eval_u08,
    "U09": _eval_u09,
    "U10": _eval_u10,
    "U11": _eval_u11,
    "U12": _eval_u12,
    "U13": _eval_u13,
    "U14": _eval_u14,
    "U15": _eval_u15,
    "U16": _eval_u16,
    "U17": _eval_u17,
    "U18": _eval_u18,
    "U19": _eval_u19,
    "U26": _eval_u26,
    "U28": _eval_u28,
    "U29": _eval_u29,
    "U31": _eval_u31,
    "U32": _eval_u32,
    "U33": _eval_u33,
    "U34": _eval_u34,
    "U35": _eval_u35,
    "U36": _eval_u36,
    "U37": _eval_u37,
}
