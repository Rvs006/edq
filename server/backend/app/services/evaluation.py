"""Evaluation engine — applies pass/fail rules to parsed tool output.

Maps each test ID to evaluation logic that produces (verdict, comment) tuples.
"""

import logging
from typing import Any

logger = logging.getLogger("edq.services.evaluation")


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
        return ("info", f"No evaluation rule defined for {test_id}. This test may require manual assessment.")
    try:
        return evaluator(parsed_data, whitelist_entries or [])
    except Exception as exc:
        logger.warning("Evaluation error for %s: %s", test_id, exc)
        return ("error", f"Evaluation failed for {test_id}")


def _eval_u01(data: dict, _wl: list) -> tuple[str, str]:
    """Ping Response."""
    if data.get("reachable"):
        return ("pass", "Ping Response — Device responds to ICMP echo requests. Network reachability confirmed.")
    return ("fail", "Ping Response — Device did not respond to ping. Verify the IP address is correct and the device is powered on. Some devices block ICMP — check firewall settings.")


def _eval_u02(data: dict, _wl: list) -> tuple[str, str]:
    """MAC Vendor Lookup."""
    mac = data.get("mac_address")
    vendor = data.get("oui_vendor", "")
    if mac and vendor:
        return ("pass", f"MAC Vendor Lookup — MAC address identified: {mac}. Vendor: {vendor}.")
    if mac:
        return ("advisory", f"MAC Vendor Lookup — MAC {mac} found but vendor not in OUI database. The manufacturer may not be registered.")
    return ("info", "MAC Vendor Lookup — Could not determine MAC address. The device may be behind a router/NAT. Try scanning from the same subnet.")


def _eval_u03(data: dict, _wl: list) -> tuple[str, str]:
    """Switch Negotiation — ethtool not in sidecar, mark N/A."""
    return ("na", "Switch Negotiation (Speed/Duplex) — This test checks Ethernet link speed and duplex settings using ethtool. "
                   "It cannot run remotely from the Docker sidecar. To verify: physically check the switch port configuration "
                   "or run 'ethtool <interface>' from a device with direct network access.")


def _eval_u04(data: dict, _wl: list) -> tuple[str, str]:
    """DHCP Behaviour."""
    dhcp = data.get("dhcp_enabled")
    if dhcp is True:
        return ("pass", "DHCP Behaviour — Device accepts DHCP lease. Automatic IP assignment confirmed.")
    if dhcp is False:
        return ("info", "DHCP Behaviour — Device uses static IP configuration. No DHCP lease detected.")
    return ("info", "DHCP Behaviour — Could not be determined automatically. Check the device's network "
                     "settings page, or monitor DHCP lease tables on the network switch/router.")


def _eval_u05(data: dict, _wl: list) -> tuple[str, str]:
    """IPv6 Support Detection — informational."""
    if data.get("ipv6_supported"):
        return ("info", "IPv6 Detection — IPv6 is enabled and responding on this device.")
    return ("info", "IPv6 Detection — No IPv6 response. The device may not support IPv6, or it is disabled in device settings.")


def _eval_u06(data: dict, _wl: list) -> tuple[str, str]:
    """Full TCP Port Scan."""
    open_ports = data.get("open_ports", [])
    count = len(open_ports)
    if count == 0:
        return ("info", "TCP Port Scan — No open TCP ports found. Verify the device is reachable and not blocking scans.")
    port_list = ", ".join(
        f"{p['port']}/{p.get('service', '?')}" for p in open_ports[:20]
    )
    suffix = f" (and {count - 20} more)" if count > 20 else ""
    return ("info", f"TCP Port Scan — {count} open TCP port(s) found: {port_list}{suffix}. Review for unnecessary services.")


def _eval_u07(data: dict, _wl: list) -> tuple[str, str]:
    """UDP Top-100 Port Scan."""
    open_ports = data.get("open_ports", [])
    count = len(open_ports)
    if count == 0:
        return ("info", "UDP Port Scan — No open UDP ports detected in top 100 scan.")
    port_list = ", ".join(
        f"{p['port']}/{p.get('service', '?')}" for p in open_ports[:20]
    )
    return ("info", f"UDP Port Scan — {count} open/filtered UDP port(s) found: {port_list}.")


def _eval_u08(data: dict, _wl: list) -> tuple[str, str]:
    """Service Version Detection."""
    open_ports = data.get("open_ports", [])
    if not open_ports:
        return ("info", "Service Detection — No service versions could be determined.")
    services = [
        f"{p['port']}: {p.get('service', '?')} {p.get('version', '')}".strip()
        for p in open_ports[:15]
    ]
    return ("info", f"Service Detection — Versions identified on {len(open_ports)} port(s): {'; '.join(services)}.")


def _eval_u09(data: dict, wl: list) -> tuple[str, str]:
    """Protocol Whitelist Compliance."""
    open_ports = set()
    for p in data.get("open_ports", []):
        open_ports.add(int(p["port"]))

    if not open_ports:
        return ("pass", "Whitelist Compliance — No open ports to compare against whitelist.")

    allowed_ports = set()
    for entry in wl:
        port_val = entry.get("port")
        if port_val is not None:
            allowed_ports.add(int(port_val))

    non_compliant = sorted(open_ports - allowed_ports)
    if non_compliant:
        return ("fail", f"Whitelist Compliance — Non-whitelisted ports open: {non_compliant}. These services are not approved. Disable them or add to the whitelist if justified.")
    return ("pass", "Whitelist Compliance — All open ports match the protocol whitelist.")


def _eval_u10(data: dict, _wl: list) -> tuple[str, str]:
    """TLS Version Assessment."""
    weak = data.get("weak_versions", [])
    tls_versions = data.get("tls_versions", [])
    if not tls_versions:
        return ("na", "TLS Assessment — No HTTPS service detected (port 443 not open) or testssl could not connect. "
                       "If this device should support HTTPS, verify the web server configuration and ensure TLS is enabled. "
                       "Devices without HTTPS transmit data in cleartext, which is a security concern on shared networks.")
    if weak:
        return ("fail", f"TLS Assessment — Weak TLS versions detected: {', '.join(weak)}. Disable TLS 1.0/1.1 and SSLv3 in the device web server settings.")
    return ("pass", f"TLS Assessment — TLS versions: {', '.join(tls_versions)}. All secure (TLS 1.2+).")


def _eval_u11(data: dict, _wl: list) -> tuple[str, str]:
    """Cipher Suite Strength."""
    weak_ciphers = data.get("weak_ciphers", [])
    ciphers = data.get("ciphers", [])
    if not ciphers:
        return ("na", "Cipher Strength — No cipher suites detected. TLS may not be configured.")
    if weak_ciphers:
        names = [c.get("name", str(c)) if isinstance(c, dict) else str(c) for c in weak_ciphers[:5]]
        return ("fail", f"Cipher Strength — Weak ciphers found: {', '.join(names)}. Disable RC4, DES, 3DES, NULL, and EXPORT ciphers in the TLS configuration.")
    return ("pass", f"Cipher Strength — All {len(ciphers)} cipher suite(s) are strong.")


def _eval_u12(data: dict, _wl: list) -> tuple[str, str]:
    """Certificate Validity."""
    if data.get("cert_valid"):
        expiry = data.get("cert_expiry", "unknown")
        issuer = data.get("cert_issuer", "unknown")
        return ("pass", f"Certificate Validity — Certificate is valid. Expires: {expiry}. Issuer: {issuer}.")
    expiry = data.get("cert_expiry")
    if expiry:
        return ("advisory", f"Certificate Validity — Issue found: certificate may be expired or self-signed. Expiry: {expiry}. Renew or replace the certificate.")
    return ("na", "Certificate Validity — No certificate detected or testssl could not connect.")


def _eval_u13(data: dict, _wl: list) -> tuple[str, str]:
    """HSTS Header Presence."""
    if data.get("hsts"):
        max_age = data.get("hsts_max_age")
        suffix = f" with max-age={max_age}" if max_age else ""
        return ("pass", f"HSTS Header — Present{suffix}. HTTPS-only browsing enforced.")
    return ("fail", "HSTS Header — Missing. Add 'Strict-Transport-Security' header to prevent protocol downgrade attacks.")


def _eval_u14(data: dict, _wl: list) -> tuple[str, str]:
    """HTTP Security Headers (nikto)."""
    stdout = data.get("raw", data.get("stdout", ""))
    if not stdout:
        return ("na", "HTTP Headers — No HTTP service detected or nikto could not connect.")

    issues = _extract_nikto_findings(stdout)
    vuln_count = len(issues)

    if vuln_count > 5:
        details = "; ".join(issues[:5]) + f" (+{vuln_count - 5} more)"
        return ("fail", f"HTTP Headers — Missing or misconfigured headers ({vuln_count} issues): {details}. Add Content-Security-Policy, X-Frame-Options, X-Content-Type-Options.")
    if vuln_count > 0:
        details = "; ".join(issues)
        return ("advisory", f"HTTP Headers — {vuln_count} issue(s) found: {details}. Review and add missing security headers.")
    return ("pass", "HTTP Headers — Security headers are properly configured.")


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
        return ("na", "SSH Algorithms — No SSH service detected (port 22 closed). Not applicable.")

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
        return ("fail", f"SSH Algorithms — Weak algorithms found: {'; '.join(parts)}. Update the SSH server configuration to remove weak algorithms.")

    if total_weak > 0:
        return ("advisory", f"SSH Algorithms — {total_weak} weak algorithm(s) found. Update the SSH server configuration to remove weak algorithms.")

    return ("pass", f"SSH Algorithms — All SSH key exchange, cipher, and MAC algorithms are strong. Version: {version}.")


def _eval_u16(data: dict, _wl: list) -> tuple[str, str]:
    """Default Credential Check."""
    found = data.get("found_credentials", [])
    if found:
        creds = [f"{c['login']}:{c['password']}" for c in found[:3]]
        return ("fail", f"Default Credentials — Default credentials work ({', '.join(creds)}). CRITICAL: Change the default password immediately via the device web interface.")
    return ("pass", "Default Credentials — No default credentials found. Device uses custom credentials.")


def _eval_u17(data: dict, _wl: list) -> tuple[str, str]:
    """Brute Force Protection."""
    lockout_detected = data.get("lockout_detected", False)
    error_msg = data.get("error", "")
    if lockout_detected:
        return ("pass", "Brute Force Protection — Account lockout detected after rapid login attempts. Protection is active.")
    if "connection refused" in error_msg.lower() or "max retries" in error_msg.lower():
        return ("pass", "Brute Force Protection — Connection refused after rapid attempts. Brute force protection is active.")
    return ("advisory", "Brute Force Protection — No lockout detected after rapid login attempts. Enable account lockout or rate limiting on the device.")


def _eval_u18(data: dict, _wl: list) -> tuple[str, str]:
    """HTTP→HTTPS Redirect."""
    redirects = data.get("redirects_to_https", False)
    http_open = data.get("http_open", False)
    if redirects:
        return ("pass", "HTTP→HTTPS Redirect — HTTP correctly redirects to HTTPS.")
    if not http_open:
        return ("pass", "HTTP→HTTPS Redirect — No HTTP service detected. Only HTTPS available.")
    return ("fail", "HTTP→HTTPS Redirect — HTTP does not redirect to HTTPS. Configure the web server to redirect port 80 to port 443.")


def _eval_u19(data: dict, _wl: list) -> tuple[str, str]:
    """OS Fingerprinting — informational."""
    os_fp = data.get("os_fingerprint")
    if os_fp:
        return ("info", f"OS Fingerprint — Operating system identified: {os_fp}.")
    return ("info", "OS Fingerprint — Could not determine OS. The device may block fingerprinting probes.")


def _eval_u26(data: dict, _wl: list) -> tuple[str, str]:
    """NTP Synchronisation Check."""
    ntp_open = data.get("ntp_open", False)
    if ntp_open:
        return ("pass", "NTP Check — NTP service detected on port 123. Time synchronisation supported.")
    return ("advisory", "NTP Check — No NTP service detected. Device may not sync time, affecting log accuracy and certificate validation.")


def _eval_u28(data: dict, _wl: list) -> tuple[str, str]:
    """BACnet/IP Discovery."""
    bacnet_open = data.get("bacnet_open", False)
    if bacnet_open:
        return ("info", "BACnet Discovery — BACnet service detected on port 47808. Ensure traffic is restricted to the BAS VLAN.")
    return ("info", "BACnet Discovery — No BACnet service detected on port 47808.")


def _eval_u29(data: dict, _wl: list) -> tuple[str, str]:
    """DNS Support Verification."""
    dns_open = data.get("dns_open", False)
    if dns_open:
        return ("info", "DNS Verification — DNS service detected on port 53.")
    return ("info", "DNS Verification — No DNS service detected. Device may use external DNS.")


def _eval_u31(data: dict, _wl: list) -> tuple[str, str]:
    """SNMP Version Check."""
    open_ports = data.get("open_ports", [])
    snmp_ports = [p for p in open_ports if p.get("port") in (161, 162)]
    if not snmp_ports:
        return ("pass", "SNMP Check — No SNMP services detected.")
    stdout = data.get("raw", data.get("stdout", ""))
    stdout_lower = (stdout or "").lower()
    if "snmpv1" in stdout_lower or "snmpv2" in stdout_lower or "v2c" in stdout_lower:
        return ("fail", "SNMP Check — SNMP v1/v2c detected. These versions transmit community strings in cleartext. Upgrade to SNMPv3 only.")
    if "snmpv3" in stdout_lower:
        return ("pass", "SNMP Check — SNMPv3 only detected. Secure configuration.")
    return ("advisory", "SNMP Check — SNMP port open but version could not be determined. Verify manually that only SNMPv3 is in use.")


def _eval_u32(data: dict, _wl: list) -> tuple[str, str]:
    """UPnP/SSDP Exposure."""
    open_ports = data.get("open_ports", [])
    upnp_ports = [p for p in open_ports if p.get("port") == 1900]
    if upnp_ports:
        return ("fail", "UPnP Check — UPnP/SSDP open on port 1900. This can expose the device to network attacks. Disable UPnP if not required.")
    return ("pass", "UPnP Check — No UPnP/SSDP service exposed.")


def _eval_u33(data: dict, _wl: list) -> tuple[str, str]:
    """mDNS/Bonjour Exposure."""
    open_ports = data.get("open_ports", [])
    mdns_ports = [p for p in open_ports if p.get("port") == 5353]
    if mdns_ports:
        return ("fail", "mDNS Check — mDNS open on port 5353. This leaks device information. Disable if not required.")
    return ("pass", "mDNS Check — No mDNS/Bonjour service exposed.")


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
        return ("fail", f"Insecure Protocols — Found: {', '.join(parts)}. Telnet and FTP transmit credentials in cleartext. Disable and use SSH/SFTP instead.")
    if insecure:
        return ("fail", f"Insecure Protocols — Cleartext protocol ports open: {insecure}. Disable and use encrypted alternatives.")
    return ("pass", "Insecure Protocols — No Telnet/FTP detected.")


def _eval_u35(data: dict, _wl: list) -> tuple[str, str]:
    """Web Server Vulnerability Scan (nikto)."""
    stdout = data.get("raw", data.get("stdout", ""))
    if not stdout:
        return ("na", "Web Vulnerability Scan — No HTTP service detected or nikto could not connect.")

    issues = _extract_nikto_findings(stdout)
    vuln_count = len(issues)

    if vuln_count > 10:
        details = "; ".join(issues[:5]) + f" (+{vuln_count - 5} more)"
        return ("fail", f"Web Vulnerability Scan — Nikto found {vuln_count} issues: {details}. Review and patch the web server.")
    if vuln_count > 3:
        details = "; ".join(issues[:5])
        return ("advisory", f"Web Vulnerability Scan — Nikto found {vuln_count} issue(s): {details}. Review and patch.")
    if vuln_count > 0:
        details = "; ".join(issues)
        return ("advisory", f"Web Vulnerability Scan — Nikto found {vuln_count} minor issue(s): {details}.")
    return ("pass", "Web Vulnerability Scan — Nikto found no significant issues.")


def _eval_u36(data: dict, _wl: list) -> tuple[str, str]:
    """Banner Grabbing / Information Leakage."""
    open_ports = data.get("open_ports", [])
    if not open_ports:
        return ("info", "Banner Grabbing — No services detected for banner analysis.")
    leaky = []
    for p in open_ports:
        version = p.get("version", "") or ""
        service = p.get("service", "") or ""
        banner = f"{service} {version}".lower()
        if any(kw in banner for kw in ["10.0.", "192.168.", "172.16.", "internal", "debug"]):
            leaky.append(f"port {p['port']}: {service} {version}".strip())
    if leaky:
        return ("advisory", f"Banner Grabbing — Banners reveal version info: {'; '.join(leaky[:5])}. Configure services to suppress version information.")
    return ("pass", "Banner Grabbing — No sensitive information leakage in service banners.")


def _eval_u37(data: dict, _wl: list) -> tuple[str, str]:
    """RTSP Stream Authentication."""
    rtsp_open = data.get("rtsp_open", False)
    auth_required = data.get("auth_required", False)
    if not rtsp_open:
        return ("na", "RTSP Auth — No RTSP service detected (port 554 closed).")
    if auth_required:
        return ("pass", "RTSP Auth — Stream requires authentication.")
    return ("fail", "RTSP Auth — Stream accessible without authentication. Anyone on the network can view the video. Enable RTSP authentication.")


import re

_NIKTO_FINDING_RE = re.compile(r"\+ (OSVDB-\d+): (.+)")


def _extract_nikto_findings(stdout: str) -> list[str]:
    """Extract structured findings from nikto output.

    Returns list of strings like "OSVDB-3092: /admin/: Directory indexing found"
    """
    findings: list[str] = []
    for line in stdout.splitlines():
        line = line.strip()
        m = _NIKTO_FINDING_RE.match(line)
        if m:
            findings.append(f"{m.group(1)}: {m.group(2).strip()}")
        elif line.startswith("+ ") and "osvdb" in line.lower():
            # Fallback for non-standard OSVDB references
            findings.append(line[2:].strip())
    return findings


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
