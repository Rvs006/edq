"""Nessus .nessus XML file parser.

Parses Tenable vulnerability scan output per CLAUDE.md Section 11.
Uses defusedxml for safe XML parsing.
"""

from typing import Any
from defusedxml import ElementTree

SEVERITY_MAP = {0: "info", 1: "low", 2: "medium", 3: "high", 4: "critical"}


class NessusParser:
    def parse(self, file_path: str) -> list[dict[str, Any]]:
        """Parse .nessus XML file, return list of finding dicts.

        Args:
            file_path: Absolute path to the .nessus XML file.

        Returns:
            List of dicts with keys: plugin_id, plugin_name, severity, port,
            protocol, description, solution, risk_factor, cvss_score, cve_ids,
            plugin_output.
        """
        tree = ElementTree.parse(file_path)
        findings: list[dict[str, Any]] = []

        for report_host in tree.findall(".//ReportHost"):
            host_ip = report_host.get("name", "")
            for item in report_host.findall("ReportItem"):
                severity_int = int(item.get("severity", "0"))
                cvss_text = item.findtext("cvss_base_score", "0") or "0"
                try:
                    cvss = float(cvss_text)
                except (ValueError, TypeError):
                    cvss = 0.0

                findings.append({
                    "host_ip": host_ip,
                    "plugin_id": int(item.get("pluginID", "0")),
                    "plugin_name": item.get("pluginName", ""),
                    "severity": SEVERITY_MAP.get(severity_int, "info"),
                    "port": int(item.get("port", "0")),
                    "protocol": item.get("protocol", ""),
                    "description": item.findtext("description", ""),
                    "solution": item.findtext("solution", ""),
                    "risk_factor": item.findtext("risk_factor", ""),
                    "cvss_score": cvss,
                    "cve_ids": [
                        cve.text for cve in item.findall("cve") if cve.text
                    ],
                    "plugin_output": item.findtext("plugin_output", ""),
                })

        return findings

    def parse_string(self, xml_content: str) -> list[dict[str, Any]]:
        """Parse .nessus XML from a string (for testing)."""
        root = ElementTree.fromstring(xml_content)
        findings: list[dict[str, Any]] = []

        for report_host in root.findall(".//ReportHost"):
            host_ip = report_host.get("name", "")
            for item in report_host.findall("ReportItem"):
                severity_int = int(item.get("severity", "0"))
                cvss_text = item.findtext("cvss_base_score", "0") or "0"
                try:
                    cvss = float(cvss_text)
                except (ValueError, TypeError):
                    cvss = 0.0

                findings.append({
                    "host_ip": host_ip,
                    "plugin_id": int(item.get("pluginID", "0")),
                    "plugin_name": item.get("pluginName", ""),
                    "severity": SEVERITY_MAP.get(severity_int, "info"),
                    "port": int(item.get("port", "0")),
                    "protocol": item.get("protocol", ""),
                    "description": item.findtext("description", ""),
                    "solution": item.findtext("solution", ""),
                    "risk_factor": item.findtext("risk_factor", ""),
                    "cvss_score": cvss,
                    "cve_ids": [
                        cve.text for cve in item.findall("cve") if cve.text
                    ],
                    "plugin_output": item.findtext("plugin_output", ""),
                })

        return findings


nessus_parser = NessusParser()
