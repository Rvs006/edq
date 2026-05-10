"""testssl.sh JSON output parser.

Parses the JSON output from testssl.sh to extract TLS versions, cipher suites,
certificate info, and HSTS status.
"""

import base64
import json
import re
from typing import Any


WEAK_TLS_VERSIONS = {"SSLv2", "SSLv3", "TLSv1", "TLSv1.0", "TLSv1.1", "TLS 1", "TLS 1.0", "TLS 1.1"}
WEAK_CIPHER_KEYWORDS = {"rc4", "des", "3des", "null", "export", "anon", "md5"}
WEAK_CIPHER_SEVERITIES = {"LOW", "WARN", "MEDIUM", "HIGH", "CRITICAL"}
PROBLEM_SEVERITIES = {"WARN", "MEDIUM", "HIGH", "CRITICAL"}

_CIPHER_ROW_RE = re.compile(
    r"^(?P<protocol>SSLv2|SSLv3|TLSv1(?:\.\d)?)\s+"
    r"(?P<hexcode>x[0-9a-fA-F]+|0x[0-9a-fA-F]+)\s+"
    r"(?P<openssl_name>\S+)\s+"
    r"(?P<key_exchange>.+?)\s{2,}"
    r"(?P<encryption>\S+)\s+"
    r"(?P<bits>\d+)\s+"
    r"(?P<iana_name>TLS_\S+)\s*$"
)


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
            "cert_has_issue": False,
            "cert_self_signed": False,
            "cert_trust_verified": None,
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

            if self._is_cipher_entry(item_id):
                if self._is_cipher_summary_entry(item_id):
                    if severity in PROBLEM_SEVERITIES:
                        result["vulnerabilities"].append({
                            "id": item_id,
                            "finding": finding,
                            "severity": severity,
                        })
                    continue
                self._process_cipher(item_id, finding, severity, result)
            elif self._is_protocol_entry(item_id):
                self._process_protocol(item_id, finding, severity, result)
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
            "cert_has_issue": False,
            "cert_self_signed": False,
            "cert_trust_verified": None,
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

        current_cipher_protocol: str | None = None
        for line in stdout.splitlines():
            stripped_line = line.strip()
            line_lower = line.lower().strip()
            if stripped_line in {"SSLv2", "SSLv3", "TLSv1", "TLSv1.1", "TLSv1.2", "TLSv1.3"}:
                current_cipher_protocol = stripped_line
                continue
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
            cipher_line = stripped_line
            if current_cipher_protocol and re.match(r"^(?:x|0x)[0-9a-fA-F]+\s+", cipher_line):
                cipher_line = f"{current_cipher_protocol}   {cipher_line}"
            cipher_info = self._parse_cipher_finding(
                f"cipher-stdout-{len(result['ciphers']) + 1}",
                cipher_line,
                "OK",
            )
            if cipher_info:
                protocol = cipher_info.get("protocol")
                if protocol and protocol not in result["tls_versions"]:
                    result["tls_versions"].append(protocol)
                if protocol in {"SSLv2", "SSLv3", "TLSv1", "TLSv1.0", "TLSv1.1"}:
                    weak_protocol = "TLSv1.0" if protocol == "TLSv1" else protocol
                    if weak_protocol not in result["weak_versions"]:
                        result["weak_versions"].append(weak_protocol)
                self._append_cipher(cipher_info, line, result)
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

    def _is_cipher_summary_entry(self, item_id: str) -> bool:
        item_lower = item_id.lower()
        return (
            item_lower.startswith("supportedciphers")
            or item_lower.startswith("pre_")
            or item_lower.startswith("cipher_order")
            or item_lower.startswith("cipherlist")
        )

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
                finding_lower = finding.lower()
                offered = (
                    ("offered" in finding_lower or "yes" in finding_lower or "enabled" in finding_lower)
                    and "not offered" not in finding_lower
                    and "not accepted" not in finding_lower
                    and "disabled" not in finding_lower
                )
                if offered:
                    if version not in result["tls_versions"]:
                        result["tls_versions"].append(version)
                    if version in {"SSLv2", "SSLv3", "TLSv1.0", "TLSv1.1"}:
                        if version not in result["weak_versions"]:
                            result["weak_versions"].append(version)
                break

    def _process_cipher(self, item_id: str, finding: str, severity: str, result: dict) -> None:
        cipher_info = self._parse_cipher_finding(item_id, finding, severity) or {
            "id": item_id,
            "name": finding,
            "severity": severity,
        }
        self._append_cipher(cipher_info, finding, result)

    def _append_cipher(self, cipher_info: dict[str, Any], finding: str, result: dict) -> None:
        result["ciphers"].append(cipher_info)
        if self._is_weak_cipher(cipher_info, finding):
            result["weak_ciphers"].append(cipher_info)

    def _parse_cipher_finding(
        self,
        item_id: str,
        finding: str,
        severity: str,
    ) -> dict[str, Any] | None:
        match = _CIPHER_ROW_RE.match((finding or "").strip())
        if not match:
            return None
        bits_raw = match.group("bits")
        iana_name = match.group("iana_name")
        return {
            "id": item_id,
            "name": iana_name,
            "openssl_name": match.group("openssl_name"),
            "protocol": match.group("protocol"),
            "hexcode": match.group("hexcode"),
            "key_exchange": match.group("key_exchange").strip(),
            "encryption": match.group("encryption"),
            "bits": int(bits_raw) if bits_raw.isdigit() else None,
            "iana_name": iana_name,
            "severity": severity,
        }

    def _is_weak_cipher(self, cipher_info: dict[str, Any], finding: str) -> bool:
        severity = str(cipher_info.get("severity") or "").upper()
        if severity in WEAK_CIPHER_SEVERITIES:
            return True

        fields = [
            finding,
            str(cipher_info.get("name") or ""),
            str(cipher_info.get("openssl_name") or ""),
            str(cipher_info.get("iana_name") or ""),
        ]
        text = " ".join(fields).lower()
        if any(kw in text for kw in WEAK_CIPHER_KEYWORDS):
            return True

        protocol = str(cipher_info.get("protocol") or "")
        if protocol in {"SSLv2", "SSLv3", "TLSv1", "TLSv1.0", "TLSv1.1"}:
            return True

        iana_name = str(cipher_info.get("iana_name") or cipher_info.get("name") or "").upper()
        openssl_name = str(cipher_info.get("openssl_name") or "").upper()
        if "_CBC_" in iana_name or "-CBC-" in openssl_name:
            return True
        if iana_name.startswith("TLS_RSA_WITH_"):
            return True
        if re.search(r"(^|[-_])SHA($|[^0-9])", openssl_name) or re.search(r"_SHA$", iana_name):
            return True

        return False

    def _process_cert(self, item_id: str, finding: str, result: dict) -> None:
        item_lower = item_id.lower()
        finding_lower = (finding or "").lower()
        issue_markers = (
            "self-signed",
            "self signed",
            "untrusted",
            "not trusted",
            "unable to verify",
            "unable to get",
            "verify error",
            "verification error",
            "expired",
            "not valid",
            "invalid",
            "hostname mismatch",
        )
        has_issue = any(marker in finding_lower for marker in issue_markers)
        if has_issue:
            result["cert_has_issue"] = True
            result["cert_valid"] = False
        if "self-signed" in finding_lower or "self signed" in finding_lower:
            result["cert_self_signed"] = True
        if "notbefore" in item_lower or "valid from" in item_lower or "start" in item_lower:
            result["cert_not_before"] = finding.strip()
        if "expir" in item_lower or "notafter" in item_lower:
            result["cert_expiry"] = finding.strip()
            result["cert_not_after"] = finding.strip()
        if "subject" in item_lower and "issuer" not in item_lower:
            result["cert_subject"] = finding.strip()
        if "issuer" in item_lower:
            result["cert_issuer"] = finding.strip()
        if "trust" in item_lower:
            result["cert_trust_verified"] = True
            if not has_issue and ("ok" in finding_lower or "passed" in finding_lower or "trusted" in finding_lower):
                result["cert_valid"] = True
        elif "valid" in item_lower:
            if not has_issue and result.get("cert_trust_verified") is True and (
                "ok" in finding_lower or "passed" in finding_lower or "trusted" in finding_lower
            ):
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
