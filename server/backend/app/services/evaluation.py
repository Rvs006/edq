"""Evaluation engine — applies pass/fail rules to parsed tool output.

Maps each test ID to evaluation logic that produces (verdict, comment) tuples.
"""

import logging
import re
from typing import Any

logger = logging.getLogger("edq.services.evaluation")

_DHCP_MESSAGE_LABELS = {
    1: "discover",
    2: "offer",
    3: "request",
    4: "decline",
    5: "ack",
    6: "nak",
    7: "release",
    8: "inform",
}


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
    return ("info", "MAC Vendor Lookup — Could not determine MAC address. The device may be behind a router/NAT. "
                     "Try scanning from the same subnet.\n\n"
                     "Platform note: MAC detection requires Layer-2 adjacency. In Docker, the scanner is behind a NAT bridge. "
                     "For best results, run EDQ on a host directly connected to the device's subnet (Linux or Windows host, not Docker).")


def _eval_u03(data: dict, _wl: list) -> tuple[str, str]:
    """Switch Negotiation — ethtool not in sidecar, mark N/A."""
    return ("na", "Switch Negotiation (Speed/Duplex) — Cannot run remotely from Docker. "
                   "To verify: check the switch port LED indicators, or run 'show interface status' "
                   "on the switch CLI, or use 'ethtool <interface>' from a host with direct access. "
                   "Expected: auto-negotiation enabled, 100Mbps or 1Gbps full-duplex.\n\n"
                   "Optimal environment: Linux host with direct Ethernet connection to the device's switch port.")


def _eval_u04(data: dict, _wl: list) -> tuple[str, str]:
    """DHCP Behaviour."""
    dhcp = data.get("dhcp_detected", data.get("dhcp_enabled"))
    dhcp_server = data.get("dhcp_server")
    offered_ip = data.get("offered_ip")
    script_output = (data.get("script_output") or "").strip()
    dhcp_observed = data.get("dhcp_observed", False)
    lease_acknowledged = data.get("dhcp_lease_acknowledged", False)
    offer_capable = data.get("offer_capable")
    dhcp_events = data.get("dhcp_events") or []
    if lease_acknowledged:
        details = ["DHCP Behaviour - DHCP request traffic observed and EDQ issued a lease acknowledgement to the device."]
        if offered_ip:
            details.append(f"Offered IP: {offered_ip}.")
        if dhcp_server:
            details.append(f"Server Identifier: {dhcp_server}.")
        return ("pass", " ".join(details))
    if dhcp_observed:
        details = ["DHCP Behaviour - DHCP client traffic from the device was observed."]
        if dhcp_events:
            seen_labels: list[str] = []
            for event in dhcp_events:
                message_type = event.get("message_type")
                label = _DHCP_MESSAGE_LABELS.get(message_type, f"type-{message_type}")
                if label not in seen_labels:
                    seen_labels.append(label)
            if seen_labels:
                details.append("Observed client messages: " + ", ".join(seen_labels) + ".")
        if offer_capable is False:
            details.append(
                "EDQ was not configured to offer a DHCP lease, so this run was observation-only. "
                "Configure Protocol Harness DHCP offer settings to complete the handshake automatically."
            )
        else:
            details.append("EDQ did not complete a full lease acknowledgement in this run, so address acceptance still requires confirmation.")
        if offered_ip:
            details.append(f"Configured offer IP: {offered_ip}.")
        if dhcp_server:
            details.append(f"Configured server identifier: {dhcp_server}.")
        return ("info", " ".join(details))
    if dhcp is True:
        details = "DHCP Behaviour — DHCP offer observed on the network segment."
        if dhcp_server:
            details += f" Server Identifier: {dhcp_server}."
        if offered_ip:
            details += f" IP Offered: {offered_ip}."
        details += (" This confirms DHCP service is present, but it does not prove the device under test accepted the lease."
                    " Confirm the device network settings or lease table for a true DHCP behaviour check.")
        if script_output:
            details += f"\n{script_output}"
        return ("info", details)
    if dhcp is False:
        return ("info", "DHCP Behaviour — No DHCP server response detected on the network segment. "
                         "The device may use static IP configuration, or the DHCP server may be on a different VLAN.")
    return ("info", "DHCP Behaviour — Could not be determined automatically. Check the device's network "
                     "settings page, or monitor DHCP lease tables on the network switch/router.\n\n"
                     "Platform note: DHCP detection uses broadcast probes. In Docker, broadcasts may not reach the device's subnet. "
                     "For best results, run from a host on the same VLAN.")


def _eval_u04_v2(data: dict, _wl: list) -> tuple[str, str]:
    """DHCP Behaviour."""
    dhcp = data.get("dhcp_detected", data.get("dhcp_enabled"))
    dhcp_server = data.get("dhcp_server")
    offered_ip = data.get("offered_ip")
    script_output = (data.get("script_output") or "").strip()
    dhcp_observed = data.get("dhcp_observed", False)
    lease_acknowledged = data.get("dhcp_lease_acknowledged", False)
    offer_capable = data.get("offer_capable")
    dhcp_events = data.get("dhcp_events") or []

    if lease_acknowledged:
        details = ["DHCP Behaviour - DHCP request traffic observed and EDQ issued a lease acknowledgement to the device."]
        if offered_ip:
            details.append(f"Offered IP: {offered_ip}.")
        if dhcp_server:
            details.append(f"Server Identifier: {dhcp_server}.")
        return ("pass", " ".join(details))

    if dhcp_observed:
        details = ["DHCP Behaviour - DHCP client traffic from the device was observed."]
        if dhcp_events:
            seen_labels: list[str] = []
            for event in dhcp_events:
                message_type = event.get("message_type")
                label = _DHCP_MESSAGE_LABELS.get(message_type, f"type-{message_type}")
                if label not in seen_labels:
                    seen_labels.append(label)
            if seen_labels:
                details.append("Observed client messages: " + ", ".join(seen_labels) + ".")
        if offer_capable is False:
            details.append(
                "EDQ was not configured to offer a DHCP lease, so this run was observation-only. "
                "Configure Protocol Harness DHCP offer settings to complete the handshake automatically."
            )
        else:
            details.append(
                "EDQ did not complete a full lease acknowledgement in this run, so address acceptance still requires confirmation."
            )
        if offered_ip:
            details.append(f"Configured offer IP: {offered_ip}.")
        if dhcp_server:
            details.append(f"Configured server identifier: {dhcp_server}.")
        return ("info", " ".join(details))

    if dhcp is True:
        details = "DHCP Behaviour - DHCP offer observed on the network segment."
        if dhcp_server:
            details += f" Server Identifier: {dhcp_server}."
        if offered_ip:
            details += f" IP Offered: {offered_ip}."
        details += (
            " This confirms DHCP service is present, but it does not prove the device under test accepted the lease."
            " Confirm the device network settings or lease table for a true DHCP behaviour check."
        )
        if script_output:
            details += f"\n{script_output}"
        return ("info", details)

    if dhcp is False:
        return (
            "info",
            "DHCP Behaviour - No DHCP server response detected on the network segment. "
            "The device may use static IP configuration, or the DHCP server may be on a different VLAN.",
        )

    return (
        "info",
        "DHCP Behaviour - Could not be determined automatically. Check the device's network "
        "settings page, or monitor DHCP lease tables on the network switch/router.\n\n"
        "Platform note: DHCP detection uses broadcast probes. In Docker, broadcasts may not reach the device's subnet. "
        "For best results, run from a host on the same VLAN.",
    )


def _eval_u05(data: dict, _wl: list) -> tuple[str, str]:
    """IPv6 Support Detection — informational."""
    if data.get("ipv6_supported"):
        return ("info", "IPv6 Detection — IPv6 is enabled and responding on this device.")
    return ("info", "IPv6 Detection — No IPv6 response. The device may not support IPv6, or it is disabled in device settings.")


def _format_port_table(open_ports: list[dict], include_version: bool = False) -> str:
    if not open_ports:
        return ""
    sorted_ports = sorted(
        open_ports,
        key=lambda p: (str(p.get("protocol", "tcp")), int(p.get("port", 0))),
    )
    if include_version:
        lines = ["PORT\tSTATE\tSERVICE\tVERSION"]
        for p in sorted_ports:
            version = (p.get("version") or "").strip()
            lines.append(
                f"{p.get('port')}/{p.get('protocol', 'tcp')}\t{p.get('state', 'open')}\t{p.get('service', '?')}\t{version}".rstrip()
            )
        return "\n".join(lines)

    lines = ["PORT\tSTATE\tSERVICE"]
    for p in sorted_ports:
        lines.append(
            f"{p.get('port')}/{p.get('protocol', 'tcp')}\t{p.get('state', 'open')}\t{p.get('service', '?')}"
        )
    return "\n".join(lines)


def _first_script(open_ports: list[dict], *script_ids: str) -> dict | None:
    """Find the first script matching any of the provided IDs in open ports.
    
    Scans a list of open_ports for the first script whose "id" attribute matches
    any of the provided script_ids. Returns that script dict (with id, output, etc.),
    or None if no match is found.
    
    Private utility for reuse by evaluation logic (e.g., evaluate_ports, evaluate_host)
    to extract specific NSE script results from port discovery data.
    
    Args:
        open_ports: List of port dicts (each with optional "scripts" list).
        *script_ids: Variable number of script ID strings to match against.
    
    Returns:
        The first script dict whose id matches any script_ids, or None.
    """
    wanted = set(script_ids)
    for port in open_ports:
        for script in port.get("scripts", []) or []:
            if script.get("id") in wanted:
                return script
    return None


_SERVICE_LABELS = {
    "ftp": "FTP",
    "ssh": "SSH",
    "http": "HTTP",
    "https": "HTTPS",
    "ssl/http": "HTTPS",
    "ssl/https": "HTTPS",
    "netbios-ssn": "SAMBA",
    "microsoft-ds": "SAMBA",
    "domain": "DNS",
    "domain?": "DNS",
    "ntp": "NTP",
    "bacnet": "BACNET",
    "bacnet-ip": "BACNET",
}


def _service_label(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    if not value:
        return "UNKNOWN"
    return _SERVICE_LABELS.get(value, value.upper())


def _script_output(script: dict | None) -> str:
    if not script:
        return ""
    output = str(script.get("output") or "").strip()
    if output:
        return output

    details = script.get("details") or {}
    if not isinstance(details, dict):
        return ""

    lines: list[str] = []
    for key, value in details.items():
        if isinstance(value, dict):
            for nested_key, nested_value in value.items():
                lines.append(f"{nested_key}: {nested_value}")
        elif isinstance(value, list):
            for entry in value:
                if isinstance(entry, dict):
                    for nested_key, nested_value in entry.items():
                        lines.append(f"{nested_key}: {nested_value}")
                else:
                    lines.append(f"{key}: {entry}")
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(line for line in lines if line.strip())


def _eval_u06(data: dict, _wl: list) -> tuple[str, str]:
    """Full TCP Port Scan."""
    open_ports = data.get("open_ports", [])
    count = len(open_ports)
    if count == 0:
        return ("info", "TCP Port Scan — No open TCP ports found. Verify the device is reachable and not blocking scans.")
    return (
        "info",
        f"TCP Port Scan — {count} open TCP port(s) found.\n{_format_port_table(open_ports)}",
    )


def _eval_u07(data: dict, _wl: list) -> tuple[str, str]:
    """UDP Top-100 Port Scan."""
    open_ports = data.get("open_ports", [])
    count = len(open_ports)
    caveat = " Note: UDP scanning through Docker may miss some ports due to NAT/firewall behaviour."
    if count == 0:
        return ("info", f"UDP Port Scan — No open UDP ports detected in top 100 scan.{caveat}")
    return (
        "info",
        f"UDP Port Scan — {count} open/filtered UDP port(s) found.{caveat}\n{_format_port_table(open_ports)}",
    )


def _eval_u08(data: dict, _wl: list) -> tuple[str, str]:
    """Service Version Detection."""
    open_ports = data.get("open_ports", [])
    if not open_ports:
        return ("info", "Service Detection — No service versions could be determined.")
    return (
        "info",
        f"Service Detection — Versions identified on {len(open_ports)} port(s).\n{_format_port_table(open_ports, include_version=True)}",
    )


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
        port_details = {int(p["port"]): p for p in data.get("open_ports", [])}
        details = []
        for port in non_compliant:
            port_info = port_details.get(port, {})
            protocol = (port_info.get("protocol") or "tcp").upper()
            service = _service_label(port_info.get("service"))
            if service in {"FTP", "TELNET", "SAMBA"}:
                suffix = "disable." if service in {"FTP", "TELNET"} else "disable if not required."
            else:
                suffix = "review and disable if not required."
            details.append(f"{protocol} port {port}: {service} found open, {suffix}")
        return ("fail", "Whitelist Compliance — Non-whitelisted ports open.\n" + "\n".join(details))
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
    return ("info", "OS Fingerprint — Could not determine OS. The device may block fingerprinting probes.\n\n"
                     "Platform note: OS fingerprinting works best with a direct network connection (not through Docker NAT). "
                     "Alternatively, check the device admin interface for OS/firmware information.")


def _eval_u26(data: dict, _wl: list) -> tuple[str, str]:
    """NTP Synchronisation Check."""
    ntp_open = data.get("ntp_open", False)
    ntp_observed = data.get("ntp_observed_sync", False)
    ntp_version = data.get("ntp_version")
    ntp_service = data.get("ntp_service")
    script_output = (data.get("ntp_script_output") or "").strip()
    if ntp_observed:
        details = ["NTP Check — NTP traffic seen. Time synchronised."]
        if ntp_version:
            details.append(f"NTP version {ntp_version} detected.")
        if script_output:
            details.append(f"\n{script_output}")
        return ("pass", " ".join(details).strip())
    if ntp_open:
        details = ["NTP Check — UDP/123 responded."]
        if ntp_service:
            details.append(f"Service: {ntp_service}.")
        if ntp_version:
            details.append(f"NTP version evidence: {ntp_version}.")
        details.append("EDQ did not observe the device contacting an EDQ-hosted NTP server in this run, so synchronisation is still unproven.")
        if script_output:
            details.append(f"\n{script_output}")
        return ("info", " ".join(details).strip())
    return ("advisory", "NTP Check — No NTP service detected. Device may not sync time, affecting log accuracy and certificate validation.")


def _eval_u28(data: dict, _wl: list) -> tuple[str, str]:
    """BACnet/IP Discovery."""
    bacnet_open = data.get("bacnet_open", False)
    bacnet_details = data.get("bacnet_details") or {}
    script_output = (data.get("bacnet_script_output") or "").strip()
    if bacnet_open:
        parts = ["BACnet Discovery — BACnet service detected on port 47808."]
        for key in ("Vendor Name", "Vendor ID", "Instance Number", "Model Name", "Application Software", "Firmware"):
            value = bacnet_details.get(key)
            if value:
                parts.append(f"{key}: {value}.")
        if script_output:
            parts.append(f"\n{script_output}")
        parts.append("Ensure BACnet traffic is restricted to the BAS VLAN.")
        return ("info", " ".join(parts).strip())
    return ("info", "BACnet Discovery — No BACnet service detected on port 47808.")


def _eval_u29(data: dict, _wl: list) -> tuple[str, str]:
    """DNS Support Verification."""
    dns_open = data.get("dns_open", False)
    dns_observed = data.get("dns_observed_requests", False)
    dns_service = data.get("dns_service")
    dns_version = data.get("dns_version")
    if dns_observed:
        return ("pass", "DNS Verification — Device made DNS requests to the EDQ laptop.")
    if dns_open:
        parts = ["DNS Verification — DNS-related service detected on port 53."]
        if dns_service:
            parts.append(f"Service: {dns_service}.")
        if dns_version:
            parts.append(f"Version evidence: {dns_version}.")
        parts.append("EDQ did not observe outbound DNS requests to the EDQ laptop in this run, so request-direction verification is still required.")
        return ("info", " ".join(parts))
    return ("info", "DNS Verification — No DNS service detected on port 53. Device may use external DNS or may require manual capture of outbound DNS requests.")


def _eval_u31(data: dict, _wl: list) -> tuple[str, str]:
    """SNMP Version Check."""
    open_ports = data.get("open_ports", [])
    snmp_ports = [p for p in open_ports if p.get("port") in (161, 162)]
    if not snmp_ports:
        return ("pass", "SNMP Check — No SNMP services detected.")
    snmpwalk_out = (data.get("snmpwalk_output", "") or "").strip()
    if snmpwalk_out and ".1.3.6" in snmpwalk_out:
        return ("fail", "SNMP Check — Default community string 'public' accepted on SNMPv1/v2c (verified by snmpwalk). Disable insecure SNMP versions and change community strings.")
    stdout = data.get("raw", data.get("stdout", ""))
    stdout_lower = (stdout or "").lower()
    if "snmpv1" in stdout_lower or "snmpv2" in stdout_lower or "v2c" in stdout_lower:
        return ("fail", "SNMP Check — SNMP v1/v2c detected. These versions transmit community strings in cleartext. Upgrade to SNMPv3 only.")
    if "snmpv3" in stdout_lower:
        if snmpwalk_out:
            return ("advisory", "SNMP Check — SNMPv3 detected but SNMP port also responded to v1/v2c probes. Verify only SNMPv3 is enabled.")
        return ("pass", "SNMP Check — SNMPv3 only detected. Secure configuration.")
    if snmpwalk_out == "" and snmp_ports:
        return ("pass", "SNMP Check — SNMP port open but default community 'public' rejected (snmpwalk got no response). Likely SNMPv3-only or access-controlled.")
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
    services_detail = []
    for p in open_ports:
        version = p.get("version", "") or ""
        service = p.get("service", "") or ""
        protocol = p.get("protocol", "tcp") or "tcp"
        state = p.get("state", "open") or "open"
        port_num = p.get("port", "?")
        # Build detailed service line: port/protocol service [version] (product) extra_info (state)
        detail = f"{port_num}/{protocol} {service}"
        if version:
            detail += f" [{version}]"
        product = p.get("product", "") or ""
        extra_info = p.get("extra_info", "") or ""
        if product:
            detail += f" ({product})"
        if extra_info:
            detail += f" {extra_info}"
        detail += f" ({state})"
        services_detail.append(detail)
        banner = f"{service} {version}".lower()
        if any(kw in banner for kw in ["10.0.", "192.168.", "172.16.", "internal", "debug"]):
            leaky.append(f"port {port_num}: {service} {version}".strip())
    services_summary = _format_port_table(open_ports, include_version=True)
    script_outputs = [
        _script_output(script)
        for port in open_ports
        for script in port.get("scripts", []) or []
        if _script_output(script)
    ]
    if leaky:
        detail = f"Banner Grabbing — Banners reveal sensitive info: {'; '.join(leaky[:5])}. Configure services to suppress version information.\n{services_summary}"
        if script_outputs:
            detail += "\n" + "\n\n".join(script_outputs[:3])
        return ("advisory", detail)
    detail = f"Banner Grabbing — Service banners captured.\n{services_summary}"
    if script_outputs:
        detail += "\n" + "\n\n".join(script_outputs[:3])
    return ("info", detail)


def _eval_u37(data: dict, _wl: list) -> tuple[str, str]:
    """RTSP Stream Authentication."""
    rtsp_open = data.get("rtsp_open", False)
    auth_required = data.get("auth_required", False)
    if not rtsp_open:
        return ("na", "RTSP Auth — No RTSP service detected (port 554 closed).")
    if auth_required:
        return ("pass", "RTSP Auth — Stream requires authentication.")
    return ("fail", "RTSP Auth — Stream accessible without authentication. Anyone on the network can view the video. Enable RTSP authentication.")


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
    "U04": _eval_u04_v2,
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
