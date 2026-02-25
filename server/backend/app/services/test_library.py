"""Universal Test Library — 30 tests that apply to every IP device.

Based on EDQ PRD v1.3 Section 9. Tests U01–U30.
"""

UNIVERSAL_TESTS = [
    {
        "test_id": "U01", "name": "Ping Response", "tier": "automatic", "tool": "nmap",
        "is_essential": True, "description": "Verify device responds to ICMP echo requests.",
        "compliance_map": ["ISO 27001 A.13.1.1"]
    },
    {
        "test_id": "U02", "name": "MAC Address Vendor Lookup", "tier": "automatic", "tool": "nmap",
        "is_essential": True, "description": "Identify device manufacturer via IEEE OUI database.",
        "compliance_map": ["ISO 27001 A.8.1.1"]
    },
    {
        "test_id": "U03", "name": "Switch Negotiation (Speed/Duplex)", "tier": "automatic", "tool": "ethtool",
        "is_essential": False, "description": "Verify Ethernet link negotiation parameters.",
        "compliance_map": []
    },
    {
        "test_id": "U04", "name": "DHCP Behaviour", "tier": "automatic", "tool": "discovery_metadata",
        "is_essential": False, "description": "Determine if device uses DHCP or static IP assignment.",
        "compliance_map": ["ISO 27001 A.13.1.1"]
    },
    {
        "test_id": "U05", "name": "IPv6 Support Detection", "tier": "automatic", "tool": "nmap",
        "is_essential": False, "description": "Check if device has IPv6 enabled and responding.",
        "compliance_map": ["ISO 27001 A.13.1.1"]
    },
    {
        "test_id": "U06", "name": "Full TCP Port Scan (All 65535)", "tier": "automatic", "tool": "nmap",
        "is_essential": True, "description": "Scan all 65535 TCP ports to identify open services.",
        "compliance_map": ["ISO 27001 A.13.1.1", "Cyber Essentials", "SOC2 CC6.1"]
    },
    {
        "test_id": "U07", "name": "UDP Top-100 Port Scan", "tier": "automatic", "tool": "nmap",
        "is_essential": False, "description": "Scan top 100 UDP ports for open services.",
        "compliance_map": ["ISO 27001 A.13.1.1"]
    },
    {
        "test_id": "U08", "name": "Service Version Detection", "tier": "automatic", "tool": "nmap",
        "is_essential": False, "description": "Identify service versions on open ports.",
        "compliance_map": ["ISO 27001 A.12.6.1"]
    },
    {
        "test_id": "U09", "name": "Protocol Whitelist Compliance", "tier": "automatic", "tool": "custom_rules",
        "is_essential": False, "description": "Compare discovered ports against allowed protocol whitelist.",
        "compliance_map": ["ISO 27001 A.13.1.1", "Cyber Essentials", "SOC2 CC6.1"]
    },
    {
        "test_id": "U10", "name": "TLS Version Assessment", "tier": "automatic", "tool": "sslyze",
        "is_essential": True, "description": "Verify TLS protocol versions (must support TLS 1.2+, reject SSL/TLS 1.0/1.1).",
        "compliance_map": ["ISO 27001 A.10.1.1", "Cyber Essentials", "SOC2 CC6.1"]
    },
    {
        "test_id": "U11", "name": "Cipher Suite Strength", "tier": "automatic", "tool": "sslyze",
        "is_essential": False, "description": "Evaluate cipher suite strength and reject weak ciphers.",
        "compliance_map": ["ISO 27001 A.10.1.1"]
    },
    {
        "test_id": "U12", "name": "Certificate Validity", "tier": "automatic", "tool": "sslyze",
        "is_essential": False, "description": "Check certificate expiry, chain, and trust.",
        "compliance_map": ["ISO 27001 A.10.1.1"]
    },
    {
        "test_id": "U13", "name": "HSTS Header Presence", "tier": "automatic", "tool": "sslyze",
        "is_essential": False, "description": "Verify HTTP Strict Transport Security header is set.",
        "compliance_map": ["ISO 27001 A.14.1.2"]
    },
    {
        "test_id": "U14", "name": "HTTP Security Headers", "tier": "automatic", "tool": "nikto",
        "is_essential": False, "description": "Check for security headers (CSP, X-Frame-Options, etc.).",
        "compliance_map": ["ISO 27001 A.14.1.2"]
    },
    {
        "test_id": "U15", "name": "SSH Algorithm Assessment", "tier": "automatic", "tool": "ssh-audit",
        "is_essential": False, "description": "Evaluate SSH key exchange, cipher, and MAC algorithms.",
        "compliance_map": ["ISO 27001 A.10.1.1", "Cyber Essentials"]
    },
    {
        "test_id": "U16", "name": "Default Credential Check", "tier": "automatic", "tool": "hydra",
        "is_essential": True, "description": "Test for default/common credentials on all services.",
        "compliance_map": ["ISO 27001 A.9.4.3", "Cyber Essentials", "SOC2 CC6.1"]
    },
    {
        "test_id": "U17", "name": "Brute Force Protection", "tier": "automatic", "tool": "custom",
        "is_essential": False, "description": "Verify account lockout after failed login attempts.",
        "compliance_map": ["ISO 27001 A.9.4.2", "Cyber Essentials"]
    },
    {
        "test_id": "U18", "name": "HTTP vs HTTPS Redirect", "tier": "automatic", "tool": "curl",
        "is_essential": False, "description": "Verify HTTP requests redirect to HTTPS.",
        "compliance_map": ["ISO 27001 A.14.1.2"]
    },
    {
        "test_id": "U19", "name": "OS Fingerprinting", "tier": "automatic", "tool": "nmap",
        "is_essential": False, "description": "Identify operating system and version.",
        "compliance_map": ["ISO 27001 A.12.6.1"]
    },
    {
        "test_id": "U20", "name": "Network Disconnection Behaviour", "tier": "guided_manual", "tool": None,
        "is_essential": False, "description": "Verify device behaviour when network cable is disconnected and reconnected.",
        "compliance_map": ["ISO 27001 A.17.1.1"]
    },
    {
        "test_id": "U21", "name": "Web Interface Password Change", "tier": "guided_manual", "tool": None,
        "is_essential": True, "description": "Verify password can be changed via web interface.",
        "compliance_map": ["ISO 27001 A.9.4.3", "Cyber Essentials", "SOC2 CC6.1"]
    },
    {
        "test_id": "U22", "name": "Firmware Update Mechanism", "tier": "guided_manual", "tool": None,
        "is_essential": False, "description": "Verify firmware update process and security.",
        "compliance_map": ["ISO 27001 A.12.6.1"]
    },
    {
        "test_id": "U23", "name": "Session Timeout Validation", "tier": "guided_manual", "tool": None,
        "is_essential": False, "description": "Verify web session times out after inactivity.",
        "compliance_map": ["ISO 27001 A.9.4.2"]
    },
    {
        "test_id": "U24", "name": "Physical Security (Reset/USB)", "tier": "guided_manual", "tool": None,
        "is_essential": False, "description": "Check for physical reset buttons, USB ports, and debug interfaces.",
        "compliance_map": ["ISO 27001 A.11.2.1"]
    },
    {
        "test_id": "U25", "name": "Manufacturer Security Documentation", "tier": "guided_manual", "tool": None,
        "is_essential": False, "description": "Verify manufacturer provides security hardening documentation.",
        "compliance_map": ["ISO 27001 A.14.2.5"]
    },
    {
        "test_id": "U26", "name": "NTP Synchronisation Check", "tier": "automatic", "tool": "nmap",
        "is_essential": True, "description": "Verify device supports NTP time synchronisation (NTPv4 preferred).",
        "compliance_map": ["ISO 27001 A.12.4.4"]
    },
    {
        "test_id": "U27", "name": "802.1x / EAP-TLS Support", "tier": "guided_manual", "tool": None,
        "is_essential": False, "description": "Check if device supports 802.1x port-based network access control.",
        "compliance_map": ["ISO 27001 A.13.1.1", "Cyber Essentials"]
    },
    {
        "test_id": "U28", "name": "BACnet/IP Discovery", "tier": "automatic", "tool": "nmap",
        "is_essential": False, "description": "Detect BACnet/IP services on port 47808.",
        "compliance_map": ["ISO 27001 A.13.1.1"]
    },
    {
        "test_id": "U29", "name": "DNS Support Verification", "tier": "automatic", "tool": "nmap",
        "is_essential": False, "description": "Verify device supports DNS resolution.",
        "compliance_map": ["ISO 27001 A.13.1.1"]
    },
    {
        "test_id": "U30", "name": "Password Policy Assessment", "tier": "guided_manual", "tool": None,
        "is_essential": False, "description": "Assess password complexity requirements and management capabilities.",
        "compliance_map": ["ISO 27001 A.9.4.3", "Cyber Essentials", "SOC2 CC6.1"]
    },
]

# Default protocol whitelist (Electracom Default)
DEFAULT_WHITELIST_ENTRIES = [
    {"port": 22, "protocol": "TCP", "service": "sFTP / SSH (RFC 4253/959)", "required_version": "SSHv2"},
    {"port": 53, "protocol": "TCP/UDP", "service": "DNS (RFC 1034)", "required_version": None},
    {"port": 68, "protocol": "UDP", "service": "DHCP (RFC 2131)", "required_version": None},
    {"port": 123, "protocol": "UDP", "service": "NTP (RFC 5905)", "required_version": "NTPv4"},
    {"port": 161, "protocol": "TCP/UDP", "service": "SNMPv3 (RFC 3411-3418)", "required_version": "v3 only"},
    {"port": 443, "protocol": "TCP", "service": "HTTPS (RFC 2616)", "required_version": None},
    {"port": 636, "protocol": "TCP/UDP", "service": "LDAPS (RFC 4513)", "required_version": None},
    {"port": 989, "protocol": "TCP/UDP", "service": "FTPS data (RFC 4217)", "required_version": None},
    {"port": 990, "protocol": "TCP/UDP", "service": "FTPS control (RFC 4217)", "required_version": None},
    {"port": 8883, "protocol": "TCP/UDP", "service": "MQTTS (MQTT over TLS)", "required_version": None},
    {"port": 47808, "protocol": "TCP/UDP", "service": "BACnet (Building Automation)", "required_version": None},
]


def get_test_by_id(test_id: str) -> dict:
    """Get a test definition by its ID."""
    for test in UNIVERSAL_TESTS:
        if test["test_id"] == test_id:
            return test
    return None


def get_all_test_ids() -> list:
    """Get all test IDs."""
    return [t["test_id"] for t in UNIVERSAL_TESTS]


def get_essential_test_ids() -> list:
    """Get IDs of essential tests."""
    return [t["test_id"] for t in UNIVERSAL_TESTS if t["is_essential"]]


def get_automatic_test_ids() -> list:
    """Get IDs of automatic tests."""
    return [t["test_id"] for t in UNIVERSAL_TESTS if t["tier"] == "automatic"]


def get_manual_test_ids() -> list:
    """Get IDs of guided manual tests."""
    return [t["test_id"] for t in UNIVERSAL_TESTS if t["tier"] == "guided_manual"]
