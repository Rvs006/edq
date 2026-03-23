"""Nmap XML output parser.

Parses nmap's XML output (-oX) into structured dicts with host/port/service/OS data.
"""

from typing import Any
from defusedxml import ElementTree


class NmapParser:
    def parse_xml(self, xml_output: str) -> dict[str, Any]:
        """Parse nmap XML output into structured dict.

        Returns:
            {
                "hosts": [{"ip": ..., "status": ..., "ports": [...], "os": ...}],
                "open_ports": [{"port": 22, "protocol": "tcp", "service": "ssh", "version": "..."}],
                "os_fingerprint": "Linux 4.x",
                "mac_address": "AA:BB:CC:DD:EE:FF",
                "oui_vendor": "Axis Communications",
                "scan_info": {...},
            }
        """
        result: dict[str, Any] = {
            "hosts": [],
            "open_ports": [],
            "os_fingerprint": None,
            "mac_address": None,
            "oui_vendor": None,
            "scan_info": {},
        }

        if not xml_output or not xml_output.strip():
            return result

        try:
            root = ElementTree.fromstring(xml_output)
        except Exception:
            return result

        scaninfo = root.find("scaninfo")
        if scaninfo is not None:
            result["scan_info"] = {
                "type": scaninfo.get("type", ""),
                "protocol": scaninfo.get("protocol", ""),
                "numservices": scaninfo.get("numservices", ""),
            }

        for host_elem in root.findall("host"):
            host_data: dict[str, Any] = {
                "ip": None,
                "status": "unknown",
                "ports": [],
                "os": None,
            }

            status = host_elem.find("status")
            if status is not None:
                host_data["status"] = status.get("state", "unknown")

            for addr in host_elem.findall("address"):
                addr_type = addr.get("addrtype", "")
                if addr_type == "ipv4" or addr_type == "ipv6":
                    host_data["ip"] = addr.get("addr")
                elif addr_type == "mac":
                    result["mac_address"] = addr.get("addr")
                    result["oui_vendor"] = addr.get("vendor", "")

            ports_elem = host_elem.find("ports")
            if ports_elem is not None:
                for port_elem in ports_elem.findall("port"):
                    port_info = self._parse_port(port_elem)
                    if port_info:
                        host_data["ports"].append(port_info)
                        state = port_elem.find("state")
                        if state is not None and state.get("state") in ("open", "open|filtered"):
                            result["open_ports"].append(port_info)

            os_elem = host_elem.find("os")
            if os_elem is not None:
                osmatch = os_elem.find("osmatch")
                if osmatch is not None:
                    host_data["os"] = osmatch.get("name", "")
                    result["os_fingerprint"] = osmatch.get("name", "")

            result["hosts"].append(host_data)

        return result

    def _parse_port(self, port_elem) -> dict[str, Any] | None:
        """Parse a single <port> element."""
        port_id = port_elem.get("portid")
        protocol = port_elem.get("protocol", "tcp")
        if port_id is None:
            return None

        service_name = ""
        service_version = ""
        service_product = ""
        service_elem = port_elem.find("service")
        if service_elem is not None:
            service_name = service_elem.get("name", "")
            service_product = service_elem.get("product", "")
            service_version = service_elem.get("version", "")

        state_str = "unknown"
        state_elem = port_elem.find("state")
        if state_elem is not None:
            state_str = state_elem.get("state", "unknown")

        version_str = service_product
        if service_version:
            version_str = f"{service_product} {service_version}".strip()

        return {
            "port": int(port_id),
            "protocol": protocol,
            "state": state_str,
            "service": service_name,
            "version": version_str,
        }

    def parse_ping(self, raw_output: dict[str, Any]) -> dict[str, Any]:
        """Parse ping/nmap -sn result for reachability."""
        stdout = raw_output.get("stdout", "")
        exit_code = raw_output.get("exit_code", 1)

        reachable = exit_code == 0 or " 0% packet loss" in stdout or "1 received" in stdout
        return {"reachable": reachable, "raw": stdout}

    def parse_ipv6(self, raw_output: dict[str, Any]) -> dict[str, Any]:
        """Parse nmap -6 result for IPv6 support."""
        stdout = raw_output.get("stdout", "")
        exit_code = raw_output.get("exit_code", 1)

        ipv6_supported = exit_code == 0 and "Host is up" in stdout
        return {"ipv6_supported": ipv6_supported, "raw": stdout}

    def parse_os_fingerprint(self, xml_output: str) -> dict[str, Any]:
        """Extract OS fingerprint from nmap -O XML output."""
        parsed = self.parse_xml(xml_output)
        return {
            "os_fingerprint": parsed.get("os_fingerprint"),
            "hosts": parsed.get("hosts", []),
        }


nmap_parser = NmapParser()
