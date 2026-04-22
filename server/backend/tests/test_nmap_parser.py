"""Unit tests for NmapParser — especially parse_host_discovery MAC handling."""

import pytest
from app.services.parsers.nmap_parser import NmapParser


@pytest.fixture
def parser():
    return NmapParser()


class TestParseHostDiscovery:
    """Tests for parse_host_discovery() — the nmap -sn stdout parser."""

    def test_single_host_with_mac(self, parser):
        stdout = (
            "Starting Nmap 7.94 ( https://nmap.org ) at 2026-04-10 12:00 UTC\n"
            "Nmap scan report for 192.168.1.10\n"
            "Host is up (0.0012s latency).\n"
            "MAC Address: AA:BB:CC:DD:EE:FF (Axis Communications)\n"
            "Nmap done: 1 IP address (1 host up) scanned in 1.23 seconds\n"
        )
        hosts = parser.parse_host_discovery(stdout)
        assert len(hosts) == 1
        assert hosts[0]["ip"] == "192.168.1.10"
        assert hosts[0]["mac"] == "AA:BB:CC:DD:EE:FF"
        assert hosts[0]["vendor"] == "Axis Communications"
        assert hosts[0]["hostname"] is None

    def test_single_host_without_mac(self, parser):
        """MAC is null when scanning across L2 boundaries (e.g. Docker NAT)."""
        stdout = (
            "Nmap scan report for 192.168.1.10\n"
            "Host is up (0.0012s latency).\n"
            "Nmap done: 1 IP address (1 host up) scanned in 1.23 seconds\n"
        )
        hosts = parser.parse_host_discovery(stdout)
        assert len(hosts) == 1
        assert hosts[0]["ip"] == "192.168.1.10"
        assert hosts[0]["mac"] is None
        assert hosts[0]["vendor"] is None

    def test_host_with_hostname(self, parser):
        stdout = (
            "Nmap scan report for cam-lobby.local (192.168.1.10)\n"
            "Host is up (0.0012s latency).\n"
            "MAC Address: 00:40:8C:12:34:56 (Axis Communications)\n"
        )
        hosts = parser.parse_host_discovery(stdout)
        assert len(hosts) == 1
        assert hosts[0]["ip"] == "192.168.1.10"
        assert hosts[0]["hostname"] == "cam-lobby.local"
        assert hosts[0]["mac"] == "00:40:8C:12:34:56"
        assert hosts[0]["vendor"] == "Axis Communications"

    def test_multiple_hosts_mixed_mac(self, parser):
        """Some hosts have MAC, some don't (common in mixed-segment scans)."""
        stdout = (
            "Nmap scan report for 192.168.1.1\n"
            "Host is up (0.001s latency).\n"
            "Nmap scan report for 192.168.1.10\n"
            "Host is up (0.002s latency).\n"
            "MAC Address: AA:BB:CC:DD:EE:FF (Hikvision)\n"
            "Nmap scan report for 192.168.1.20\n"
            "Host is up (0.003s latency).\n"
        )
        hosts = parser.parse_host_discovery(stdout)
        assert len(hosts) == 3
        # First host: gateway, no MAC (it's the scanner itself)
        assert hosts[0]["ip"] == "192.168.1.1"
        assert hosts[0]["mac"] is None
        # Second host: has MAC
        assert hosts[1]["ip"] == "192.168.1.10"
        assert hosts[1]["mac"] == "AA:BB:CC:DD:EE:FF"
        assert hosts[1]["vendor"] == "Hikvision"
        # Third host: no MAC
        assert hosts[2]["ip"] == "192.168.1.20"
        assert hosts[2]["mac"] is None

    def test_mac_without_vendor(self, parser):
        """MAC line with no vendor parenthetical."""
        stdout = (
            "Nmap scan report for 10.0.0.5\n"
            "Host is up.\n"
            "MAC Address: 11:22:33:44:55:66\n"
        )
        hosts = parser.parse_host_discovery(stdout)
        assert len(hosts) == 1
        assert hosts[0]["mac"] == "11:22:33:44:55:66"
        assert hosts[0]["vendor"] is None

    def test_empty_output(self, parser):
        hosts = parser.parse_host_discovery("")
        assert hosts == []

    def test_no_hosts_found(self, parser):
        stdout = (
            "Starting Nmap 7.94 ( https://nmap.org )\n"
            "Nmap done: 256 IP addresses (0 hosts up) scanned in 5.0 seconds\n"
        )
        hosts = parser.parse_host_discovery(stdout)
        assert hosts == []


class TestParseXml:
    """Tests for parse_xml() — MAC extraction from XML output."""

    def test_xml_with_mac_address(self, parser):
        xml = """<?xml version="1.0"?>
        <nmaprun>
          <host>
            <status state="up"/>
            <address addr="192.168.1.10" addrtype="ipv4"/>
            <address addr="AA:BB:CC:DD:EE:FF" addrtype="mac" vendor="Axis Communications"/>
            <ports>
              <port protocol="tcp" portid="80">
                <state state="open"/>
                <service name="http"/>
              </port>
            </ports>
          </host>
        </nmaprun>"""
        result = parser.parse_xml(xml)
        assert result["mac_address"] == "AA:BB:CC:DD:EE:FF"
        assert result["oui_vendor"] == "Axis Communications"
        assert len(result["hosts"]) == 1
        assert result["hosts"][0]["ip"] == "192.168.1.10"

    def test_xml_without_mac_address(self, parser):
        """No MAC in XML — common when scanning across Docker NAT."""
        xml = """<?xml version="1.0"?>
        <nmaprun>
          <host>
            <status state="up"/>
            <address addr="192.168.1.10" addrtype="ipv4"/>
          </host>
        </nmaprun>"""
        result = parser.parse_xml(xml)
        assert result["mac_address"] is None
        assert result["oui_vendor"] is None

    def test_xml_empty_input(self, parser):
        result = parser.parse_xml("")
        assert result["mac_address"] is None
        assert result["hosts"] == []

    def test_xml_malformed(self, parser):
        result = parser.parse_xml("<broken>xml")
        assert result["mac_address"] is None
        assert result["hosts"] == []

    def test_xml_preserves_port_and_host_script_output(self, parser):
        xml = """<?xml version="1.0"?>
        <nmaprun>
          <host>
            <status state="up"/>
            <address addr="192.168.1.10" addrtype="ipv4"/>
            <script id="host-script" output="host evidence"/>
            <ports>
              <port protocol="udp" portid="47808">
                <state state="open"/>
                <service name="bacnet"/>
                <script id="bacnet-info" output="Vendor Name: Example Controls&#10;Instance Number: 1234">
                  <elem key="Vendor Name">Example Controls</elem>
                  <elem key="Instance Number">1234</elem>
                </script>
              </port>
            </ports>
          </host>
        </nmaprun>"""

        result = parser.parse_xml(xml)

        assert result["scripts"] == [
            {"id": "host-script", "output": "host evidence", "details": {}}
        ]
        assert result["open_ports"][0]["scripts"] == [
            {
                "id": "bacnet-info",
                "output": "Vendor Name: Example Controls\nInstance Number: 1234",
                "details": {
                    "Vendor Name": "Example Controls",
                    "Instance Number": "1234",
                },
            }
        ]
