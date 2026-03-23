"""ssh-audit JSON output parser.

Parses ssh-audit output to extract key exchange, cipher, MAC, and host key algorithms,
flagging weak or deprecated ones.
"""

import json
from typing import Any


WEAK_KEX = {
    "diffie-hellman-group1-sha1",
    "diffie-hellman-group14-sha1",
    "diffie-hellman-group-exchange-sha1",
}

WEAK_CIPHERS = {
    "3des-cbc",
    "aes128-cbc",
    "aes192-cbc",
    "aes256-cbc",
    "blowfish-cbc",
    "cast128-cbc",
    "arcfour",
    "arcfour128",
    "arcfour256",
}

WEAK_MACS = {
    "hmac-md5",
    "hmac-md5-96",
    "hmac-sha1",
    "hmac-sha1-96",
    "hmac-ripemd160",
}

WEAK_HOST_KEYS = {
    "ssh-dss",
}


class SshAuditParser:
    def parse(self, raw_output: dict[str, Any]) -> dict[str, Any]:
        """Parse ssh-audit output.

        Accepts either the raw sidecar response (with stdout/output_file) or
        direct JSON from ssh-audit.

        Returns:
            {
                "ssh_version": "OpenSSH_8.9p1",
                "kex_algorithms": [...],
                "ciphers": [...],
                "macs": [...],
                "host_keys": [...],
                "weak_kex": [...],
                "weak_ciphers": [...],
                "weak_macs": [...],
                "weak_host_keys": [...],
                "recommendations": [...],
                "overall_score": "good" | "warning" | "fail",
            }
        """
        result: dict[str, Any] = {
            "ssh_version": None,
            "kex_algorithms": [],
            "ciphers": [],
            "macs": [],
            "host_keys": [],
            "weak_kex": [],
            "weak_ciphers": [],
            "weak_macs": [],
            "weak_host_keys": [],
            "recommendations": [],
            "overall_score": "good",
        }

        json_data = self._extract_json(raw_output)
        if json_data:
            return self._parse_json(json_data, result)
        return self._parse_text(raw_output.get("stdout", ""), result)

    def _extract_json(self, raw_output: dict[str, Any]) -> dict | None:
        """Try to extract JSON data from the sidecar response."""
        import base64
        output_file = raw_output.get("output_file", "")
        if output_file:
            try:
                decoded = base64.b64decode(output_file)
                return json.loads(decoded)
            except Exception:
                pass

        stdout = raw_output.get("stdout", "")
        if stdout:
            try:
                return json.loads(stdout)
            except Exception:
                pass
        return None

    def _parse_json(self, data: dict, result: dict[str, Any]) -> dict[str, Any]:
        """Parse structured JSON output from ssh-audit."""
        banner = data.get("banner", {})
        if isinstance(banner, dict):
            result["ssh_version"] = banner.get("raw", banner.get("software", ""))
        elif isinstance(banner, str):
            result["ssh_version"] = banner

        for kex in data.get("kex", []):
            name = kex.get("algorithm", kex) if isinstance(kex, dict) else str(kex)
            result["kex_algorithms"].append(name)
            if name.lower() in WEAK_KEX:
                result["weak_kex"].append(name)

        for enc in data.get("enc", []):
            name = enc.get("algorithm", enc) if isinstance(enc, dict) else str(enc)
            result["ciphers"].append(name)
            if name.lower() in WEAK_CIPHERS:
                result["weak_ciphers"].append(name)

        for mac in data.get("mac", []):
            name = mac.get("algorithm", mac) if isinstance(mac, dict) else str(mac)
            result["macs"].append(name)
            if name.lower() in WEAK_MACS:
                result["weak_macs"].append(name)

        for key in data.get("key", data.get("host_keys", [])):
            name = key.get("algorithm", key) if isinstance(key, dict) else str(key)
            result["host_keys"].append(name)
            if name.lower() in WEAK_HOST_KEYS:
                result["weak_host_keys"].append(name)

        for rec in data.get("recommendations", data.get("cves", [])):
            if isinstance(rec, dict):
                result["recommendations"].append(rec.get("description", str(rec)))
            else:
                result["recommendations"].append(str(rec))

        total_weak = (
            len(result["weak_kex"])
            + len(result["weak_ciphers"])
            + len(result["weak_macs"])
            + len(result["weak_host_keys"])
        )
        if total_weak > 3:
            result["overall_score"] = "fail"
        elif total_weak > 0:
            result["overall_score"] = "warning"
        else:
            result["overall_score"] = "good"

        return result

    def _parse_text(self, stdout: str, result: dict[str, Any]) -> dict[str, Any]:
        """Fallback: parse ssh-audit text output."""
        if not stdout:
            return result

        section = None
        for line in stdout.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            if "banner:" in stripped.lower() or "ssh-" in stripped.lower():
                if result["ssh_version"] is None:
                    result["ssh_version"] = stripped

            if "key exchange algorithms" in stripped.lower():
                section = "kex"
                continue
            elif "encryption algorithms" in stripped.lower() or "ciphers" in stripped.lower():
                section = "enc"
                continue
            elif "mac algorithms" in stripped.lower():
                section = "mac"
                continue
            elif "host key algorithms" in stripped.lower() or "host-key" in stripped.lower():
                section = "hostkey"
                continue
            elif "recommendations" in stripped.lower():
                section = "rec"
                continue

            if stripped.startswith("(") or stripped.startswith("[") or stripped.startswith("--"):
                continue

            if section == "kex" and stripped.startswith("`"):
                alg = stripped.strip("`- ")
                if alg:
                    result["kex_algorithms"].append(alg)
                    if alg.lower() in WEAK_KEX:
                        result["weak_kex"].append(alg)
            elif section == "enc" and stripped.startswith("`"):
                alg = stripped.strip("`- ")
                if alg:
                    result["ciphers"].append(alg)
                    if alg.lower() in WEAK_CIPHERS:
                        result["weak_ciphers"].append(alg)
            elif section == "mac" and stripped.startswith("`"):
                alg = stripped.strip("`- ")
                if alg:
                    result["macs"].append(alg)
                    if alg.lower() in WEAK_MACS:
                        result["weak_macs"].append(alg)
            elif section == "hostkey" and stripped.startswith("`"):
                alg = stripped.strip("`- ")
                if alg:
                    result["host_keys"].append(alg)
                    if alg.lower() in WEAK_HOST_KEYS:
                        result["weak_host_keys"].append(alg)
            elif section == "rec":
                result["recommendations"].append(stripped)

            if "(warn)" in stripped.lower() or "(fail)" in stripped.lower():
                name = stripped.split("--")[0].strip().strip("`")
                if name:
                    if section == "kex":
                        result["weak_kex"].append(name)
                    elif section == "enc":
                        result["weak_ciphers"].append(name)
                    elif section == "mac":
                        result["weak_macs"].append(name)

        total_weak = (
            len(result["weak_kex"])
            + len(result["weak_ciphers"])
            + len(result["weak_macs"])
            + len(result["weak_host_keys"])
        )
        if total_weak > 3:
            result["overall_score"] = "fail"
        elif total_weak > 0:
            result["overall_score"] = "warning"
        else:
            result["overall_score"] = "good"

        return result


ssh_audit_parser = SshAuditParser()
