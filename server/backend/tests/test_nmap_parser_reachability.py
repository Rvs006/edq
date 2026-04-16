"""Regression tests: dead hosts must not be reported as found."""

import pytest
from app.services.parsers.nmap_parser import NmapParser


@pytest.fixture
def parser():
    return NmapParser()


def test_parse_xml_skips_down_host(parser):
    xml = """<?xml version="1.0"?>
    <nmaprun>
      <host>
        <status state="down"/>
        <address addr="192.168.1.10" addrtype="ipv4"/>
        <ports>
          <port protocol="tcp" portid="80">
            <state state="open"/>
            <service name="http"/>
          </port>
        </ports>
      </host>
    </nmaprun>"""
    result = parser.parse_xml(xml)
    assert result["hosts"] == []
    assert result["open_ports"] == []


def test_parse_host_discovery_drops_seems_down(parser):
    stdout = "Nmap scan report for 192.168.1.10\nHost seems down.\n"
    assert parser.parse_host_discovery(stdout) == []
