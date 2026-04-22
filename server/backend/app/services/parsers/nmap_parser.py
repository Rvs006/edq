"""Nmap XML output parser.

Parses nmap's XML output (-oX) into structured dicts with host/port/service/OS data.
"""

import logging
from typing import Any
from defusedxml import ElementTree

logger = logging.getLogger("edq.parsers.nmap")


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
            "os_details": None,
            "device_type": None,
            "running": [],
            "os_cpe": [],
            "mac_address": None,
            "oui_vendor": None,
            "scan_info": {},
            "scripts": [],
        }

        if not xml_output or not xml_output.strip():
            logger.warning("Empty XML output received for nmap scan")
            return result

        try:
            root = ElementTree.fromstring(xml_output)
        except Exception:
            logger.error("Failed to parse nmap XML: %s", xml_output[:200])
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
                "hostname": None,
                "scripts": [],
            }

            status = host_elem.find("status")
            if status is not None:
                host_data["status"] = status.get("state", "unknown")

            # Skip hosts that are not explicitly "up" — dead hosts must not
            # appear in the returned result, otherwise EDQ would report a
            # device as found after its cable is unplugged.
            if host_data["status"] != "up":
                continue

            for addr in host_elem.findall("address"):
                addr_type = addr.get("addrtype", "")
                if addr_type == "ipv4" or addr_type == "ipv6":
                    host_data["ip"] = addr.get("addr")
                elif addr_type == "mac":
                    host_data["mac_address"] = addr.get("addr")
                    host_data["oui_vendor"] = addr.get("vendor", "")
                    # Also store at top level for single-host scans
                    result["mac_address"] = addr.get("addr")
                    result["oui_vendor"] = addr.get("vendor", "")

            hostnames_elem = host_elem.find("hostnames")
            if hostnames_elem is not None:
                for hostname_elem in hostnames_elem.findall("hostname"):
                    hostname = hostname_elem.get("name")
                    if hostname:
                        host_data["hostname"] = hostname
                        break

            ports_elem = host_elem.find("ports")
            if ports_elem is not None:
                for port_elem in ports_elem.findall("port"):
                    port_info = self._parse_port(port_elem)
                    if port_info:
                        host_data["ports"].append(port_info)
                        state = port_elem.find("state")
                        if state is not None and state.get("state") in ("open", "open|filtered"):
                            result["open_ports"].append(port_info)

            for script_elem in host_elem.findall("script"):
                script_info = self._parse_script(script_elem)
                if script_info:
                    host_data["scripts"].append(script_info)
                    result["scripts"].append(script_info)

            os_elem = host_elem.find("os")
            if os_elem is not None:
                osmatch = os_elem.find("osmatch")
                if osmatch is not None:
                    host_data["os"] = osmatch.get("name", "")
                    result["os_fingerprint"] = osmatch.get("name", "")
                    result["os_details"] = osmatch.get("name", "")
                running: list[str] = []
                device_types: list[str] = []
                cpes: list[str] = []
                for osclass in os_elem.findall("osclass"):
                    device_type = (osclass.get("type", "") or "").strip()
                    vendor = (osclass.get("vendor", "") or "").strip()
                    family = (osclass.get("osfamily", "") or "").strip()
                    generation = (osclass.get("osgen", "") or "").strip()
                    if device_type and device_type not in device_types:
                        device_types.append(device_type)
                    running_label = " ".join(part for part in (vendor, family, generation) if part).strip()
                    if running_label and running_label not in running:
                        running.append(running_label)
                    for cpe_elem in osclass.findall("cpe"):
                        cpe_value = (cpe_elem.text or "").strip()
                        if cpe_value and cpe_value not in cpes:
                            cpes.append(cpe_value)
                if device_types:
                    result["device_type"] = "|".join(device_types)
                if running:
                    result["running"] = running
                if cpes:
                    result["os_cpe"] = cpes

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
        service_extra_info = ""
        service_elem = port_elem.find("service")
        if service_elem is not None:
            service_name = service_elem.get("name", "")
            service_product = service_elem.get("product", "")
            service_version = service_elem.get("version", "")
            service_extra_info = service_elem.get("extrainfo", "")

        state_str = "unknown"
        state_elem = port_elem.find("state")
        if state_elem is not None:
            state_str = state_elem.get("state", "unknown")

        scripts = []
        for script_elem in port_elem.findall("script"):
            script_info = self._parse_script(script_elem)
            if script_info:
                scripts.append(script_info)

        version_str = service_product
        if service_version:
            version_str = f"{service_product} {service_version}".strip()

        return {
            "port": int(port_id),
            "protocol": protocol,
            "state": state_str,
            "service": service_name,
            "version": version_str,
            "product": service_product,
            "extra_info": service_extra_info,
            "scripts": scripts,
        }

    def _parse_script(self, script_elem) -> dict[str, Any] | None:
        script_id = script_elem.get("id", "")
        output = script_elem.get("output", "") or ""
        if not script_id and not output:
            return None
        details = self._parse_script_children(script_elem)
        return {
            "id": script_id,
            "output": output,
            "details": details,
        }

    def _parse_script_children(self, elem) -> dict[str, Any]:
        details: dict[str, Any] = {}
        for child in list(elem):
            key = child.get("key") or child.tag
            if child.tag == "elem":
                details[key] = (child.text or "").strip()
            elif child.tag == "table":
                nested = self._parse_script_children(child)
                existing = details.get(key)
                if existing is None:
                    details[key] = nested
                elif isinstance(existing, list):
                    existing.append(nested)
                else:
                    details[key] = [existing, nested]
        return details

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

    def parse_host_discovery(self, stdout: str) -> list[dict[str, Any]]:
        """Parse nmap -sn stdout for discovered hosts (IP, MAC, vendor, hostname)."""
        import re

        hosts: list[dict[str, Any]] = []
        current_ip = None
        current_mac = None
        current_vendor = None
        current_hostname = None
        current_is_up = False
        current_is_down = False

        port_line_re = re.compile(r"^\d+/(?:tcp|udp)\s+\S+\s+\S+")

        def finalize():
            # Append pending host only if marked up and not explicitly down.
            if current_ip and current_is_up and not current_is_down:
                hosts.append({
                    "ip": current_ip,
                    "mac": current_mac,
                    "vendor": current_vendor,
                    "hostname": current_hostname,
                })

        for line in stdout.splitlines():
            line = line.strip()
            if "Nmap scan report for" in line:
                finalize()
                current_mac = None
                current_vendor = None
                current_hostname = None
                current_is_up = False
                current_is_down = False

                parts = line.replace("Nmap scan report for ", "")
                if "(" in parts and ")" in parts:
                    hostname_part = parts.split("(")[0].strip()
                    ip_part = parts.split("(")[1].rstrip(")")
                    current_ip = ip_part
                    current_hostname = hostname_part
                else:
                    current_ip = parts.strip()
                    current_hostname = None

            elif "Host is up" in line:
                current_is_up = True

            elif "Host seems down" in line or "0 hosts up" in line:
                current_is_down = True

            elif "MAC Address:" in line:
                mac_part = line.replace("MAC Address: ", "")
                if " " in mac_part:
                    current_mac = mac_part.split(" ")[0].strip()
                    current_vendor = mac_part.split("(", 1)[1].rstrip(")") if "(" in mac_part else None
                else:
                    current_mac = mac_part.strip()
                # MAC Address line corroborates the host is reachable
                current_is_up = True

            elif port_line_re.match(line):
                # An open-port line (e.g. "80/tcp open http") also corroborates.
                current_is_up = True

        finalize()
        return hosts

    def parse_arp_cache(self, stdout: str) -> dict[str, Any]:
        """Parse `ip neigh show` output for MAC address.

        Example output: '192.168.1.10 dev eth0 lladdr aa:bb:cc:dd:ee:ff REACHABLE'
        """
        import re
        mac_match = re.search(r"lladdr\s+([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})", stdout)
        if mac_match:
            return {"mac_address": mac_match.group(1).upper()}
        return {"mac_address": None}

    def parse_dhcp_discover(self, xml_output: str) -> dict[str, Any]:
        """Parse nmap dhcp-discover script output from XML."""
        result: dict[str, Any] = {
            "dhcp_detected": None,
            "dhcp_server": None,
            "offered_ip": None,
            "script_output": "",
            "details": {},
        }

        if not xml_output or not xml_output.strip():
            return result

        try:
            root = ElementTree.fromstring(xml_output)
        except Exception:
            # Fallback: check raw text for DHCP indicators
            lower = xml_output.lower()
            if "dhcpack" in lower or "dhcpoffer" in lower or "ip offered" in lower or "dhcp message type" in lower:
                result["dhcp_detected"] = True
            else:
                result["dhcp_detected"] = False
            return result

        # Look for dhcp-discover script output in XML
        for script in root.iter("script"):
            if script.get("id") == "dhcp-discover":
                output = script.get("output", "")
                if output:
                    result["dhcp_detected"] = True
                    result["script_output"] = output
                    result["details"] = self._parse_script_children(script)
                    # Extract DHCP server IP
                    for elem in script.iter("elem"):
                        key = elem.get("key", "")
                        if key == "Server Identifier":
                            result["dhcp_server"] = elem.text
                        elif key == "IP Offered":
                            result["offered_ip"] = elem.text
                    return result

        # No dhcp-discover script found in output
        result["dhcp_detected"] = False
        return result


nmap_parser = NmapParser()
