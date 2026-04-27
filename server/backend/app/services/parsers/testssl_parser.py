"""testssl.sh JSON output parser.

Parses the JSON output from testssl.sh to extract TLS versions, cipher suites,
certificate info, and HSTS status.
"""

import json
import base64
from typing import Any


WEAK_TLS_VERSIONS = {"SSLv2", "SSLv3", "TLSv1", "TLSv1.0", "TLSv1.1", "TLS 1", "TLS 1.0", "TLS 1.1"}
WEAK_CIPHER_KEYWORDS = {"rc4", "des", "3des", "null", "export", "anon", "md5"}


class TestsslParser:
    def parse(self, output_file_b64: str) -> dict[str, Any]:
        """Parse testssl.sh JSON output (base64-encoded).

        Returns:
            {
                "tls_versions": ["TLSv1.2", "TLSv1.3"],
                "weak_versions": [],
                "ciphers": [...],
                "weak_ciphers": [...],
                "cert_valid": True,
                "cert_expiry": "2026-01-01",
                "cert_subject": "...",
                "cert_issuer": "...",
                "hsts": True,
                "hsts_max_age": 31536000,
                "vulnerabilities": [...],
            }
        """
        result: dict[str, Any] = {
            "tls_versions": [],
            "weak_versions": [],
            "ciphers": [],
            "weak_ciphers": [],
            "cert_valid": False,
            "cert_not_before": None,
            "cert_not_after": None,
            "cert_expiry": None,
            "cert_subject": None,
            "cert_issuer": None,
            "hsts": False,
            "hsts_max_age": None,
            "vulnerabilities": [],
        }

        if not output_file_b64:
            return result

        try:
            decoded = base64.b64decode(output_file_b64)
            data = json.loads(decoded)
        except Exception:
            try:
                data = json.loads(output_file_b64)
            except Exception:
                return result

        findings = data if isinstance(data, list) else data.get("scanResult", data.get("findings", []))
        if isinstance(findings, dict):
            findings = findings.get("serverDefaults", []) + findings.get("protocols", []) + findings.get("ciphers", [])

        if not isinstance(findings, list):
            return result

        for item in findings:
            if not isinstance(item, dict):
                continue
            item_id = item.get("id", "")
            finding = item.get("finding", "")
            severity = item.get("severity", "").upper()

            if self._is_protocol_entry(item_id):
                self._process_protocol(item_id, finding, severity, result)
            elif self._is_cipher_entry(item_id):
                self._process_cipher(item_id, finding, severity, result)
            elif self._is_cert_entry(item_id):
                self._process_cert(item_id, finding, result)
            elif item_id.lower() in ("hsts", "hsts_(http_strict_transport_security)"):
                result["hsts"] = self._hsts_is_present(finding, severity)
                if "max-age" in finding.lower():
                    self._extract_hsts_max_age(finding, result)
            elif severity in ("WARN", "HIGH", "CRITICAL", "MEDIUM"):
                result["vulnerabilities"].append({
                    "id": item_id,
                    "finding": finding,
                    "severity": severity,
                })

        return result

    def parse_from_stdout(self, stdout: str) -> dict[str, Any]:
        """Fallback parser for testssl.sh stdout text output."""
        result: dict[str, Any] = {
            "tls_versions": [],
            "weak_versions": [],
            "ciphers": [],
            "weak_ciphers": [],
            "cert_valid": False,
            "cert_not_before": None,
            "cert_not_after": None,
            "cert_expiry": None,
            "cert_subject": None,
            "cert_issuer": None,
            "hsts": False,
            "hsts_max_age": None,
            "vulnerabilities": [],
        }

        if not stdout:
            return result

        for line in stdout.splitlines():
            line_lower = line.lower().strip()
            if "tls 1.2" in line_lower and "offered" in line_lower:
                result["tls_versions"].append("TLSv1.2")
            if "tls 1.3" in line_lower and "offered" in line_lower:
                result["tls_versions"].append("TLSv1.3")
            if "tls 1.0" in line_lower and "offered" in line_lower:
                result["tls_versions"].append("TLSv1.0")
                result["weak_versions"].append("TLSv1.0")
            if "tls 1.1" in line_lower and "offered" in line_lower:
                result["tls_versions"].append("TLSv1.1")
                result["weak_versions"].append("TLSv1.1")
            if "sslv3" in line_lower and "offered" in line_lower:
                result["tls_versions"].append("SSLv3")
                result["weak_versions"].append("SSLv3")
            if "sslv2" in line_lower and "offered" in line_lower:
                result["tls_versions"].append("SSLv2")
                result["weak_versions"].append("SSLv2")
            if "hsts" in line_lower and self._hsts_is_present(line, ""):
                result["hsts"] = True
            if "not valid after" in line_lower or "certificate expires" in line_lower:
                parts = line.strip().split()
                if parts:
                    result["cert_expiry"] = parts[-1]
                    result["cert_not_after"] = line.strip()
            if "not valid before" in line_lower:
                result["cert_not_before"] = line.strip()
            if line_lower.startswith("subject:"):
                result["cert_subject"] = line.split(":", 1)[1].strip()
            if line_lower.startswith("issuer:"):
                result["cert_issuer"] = line.split(":", 1)[1].strip()

        return result

    def _is_protocol_entry(self, item_id: str) -> bool:
        item_lower = item_id.lower()
        return any(p in item_lower for p in ("sslv2", "sslv3", "tls1", "tls_1"))

    def _is_cipher_entry(self, item_id: str) -> bool:
        item_lower = item_id.lower()
        return "cipher" in item_lower or "cipherlist" in item_lower

    def _is_cert_entry(self, item_id: str) -> bool:
        item_lower = item_id.lower()
        return "cert" in item_lower

    def _process_protocol(self, item_id: str, finding: str, severity: str, result: dict) -> None:
        version_map = {
            "tls1_3": "TLSv1.3",
            "tls1_2": "TLSv1.2",
            "tls1_1": "TLSv1.1",
            "tls1_0": "TLSv1.0",
            "tls1": "TLSv1.0",
            "sslv3": "SSLv3",
            "sslv2": "SSLv2",
        }
        item_lower = item_id.lower().replace(" ", "_")
        for key, version in version_map.items():
            if key in item_lower:
                offered = "offered" in finding.lower() or "yes" in finding.lower()
                if offered:
                    if version not in result["tls_versions"]:
                        result["tls_versions"].append(version)
                    if version in {"SSLv2", "SSLv3", "TLSv1.0", "TLSv1.1"}:
                        if version not in result["weak_versions"]:
                            result["weak_versions"].append(version)
                break

    def _process_cipher(self, item_id: str, finding: str, severity: str, result: dict) -> None:
        cipher_info = {"id": item_id, "name": finding, "severity": severity}
        result["ciphers"].append(cipher_info)
        if severity in ("WARN", "HIGH", "CRITICAL", "MEDIUM"):
            result["weak_ciphers"].append(cipher_info)
        elif any(kw in finding.lower() for kw in WEAK_CIPHER_KEYWORDS):
            result["weak_ciphers"].append(cipher_info)

    def _process_cert(self, item_id: str, finding: str, result: dict) -> None:
        item_lower = item_id.lower()
        if "notbefore" in item_lower or "valid from" in item_lower or "start" in item_lower:
            result["cert_not_before"] = finding.strip()
        if "expir" in item_lower or "notafter" in item_lower:
            result["cert_expiry"] = finding.strip()
            result["cert_not_after"] = finding.strip()
        if "subject" in item_lower and "issuer" not in item_lower:
            result["cert_subject"] = finding.strip()
        if "issuer" in item_lower:
            result["cert_issuer"] = finding.strip()
        if "trust" in item_lower or "valid" in item_lower:
            finding_lower = finding.lower()
            if "ok" in finding_lower or "passed" in finding_lower or "trusted" in finding_lower:
                result["cert_valid"] = True

    def _extract_hsts_max_age(self, finding: str, result: dict) -> None:
        import re
        match = re.search(r"max-age[=:]\s*(\d+)", finding, re.IGNORECASE)
        if match:
            result["hsts_max_age"] = int(match.group(1))

    def _hsts_is_present(self, finding: str, severity: str) -> bool:
        lowered = (finding or "").lower()
        if any(marker in lowered for marker in ("not offered", "not present", "missing", "disabled", "max-age=0", "max-age: 0")):
            return False
        if severity.upper() in ("WARN", "HIGH", "CRITICAL", "MEDIUM"):
            return False
        return "yes" in lowered or "offered" in lowered or "max-age" in lowered or severity.upper() in ("OK", "INFO", "LOW")


testssl_parser = TestsslParser()
