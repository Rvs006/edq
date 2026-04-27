"""Hydra credential-testing output parser.

Parses hydra stdout to extract found credentials and attempt statistics.
"""

import re
from typing import Any


class HydraParser:
    def parse(self, raw_output: dict[str, Any]) -> dict[str, Any]:
        """Parse hydra stdout output.

        Returns:
            {
                "found_credentials": [{"login": "admin", "password": "admin", "service": "http-get", "host": "..."}],
                "attempts": 100,
                "successful": 1,
                "service": "http-get",
                "raw": "...",
            }
        """
        result: dict[str, Any] = {
            "found_credentials": [],
            "attempts": 0,
            "successful": 0,
            "service": None,
            "raw": "",
            "stderr": raw_output.get("stderr", ""),
            "exit_code": raw_output.get("exit_code"),
            "check_ran": False,
        }

        stdout = raw_output.get("stdout", "")
        result["raw"] = stdout

        if not stdout:
            return result
        result["check_ran"] = True

        cred_pattern = re.compile(
            r"\[(\d+)\]\[([^\]]+)\]\s+host:\s+(\S+)\s+login:\s+(\S+)\s+password:\s+(\S*)",
            re.IGNORECASE,
        )
        for match in cred_pattern.finditer(stdout):
            port, service, host, login, password = match.groups()
            result["found_credentials"].append({
                "port": int(port),
                "service": service,
                "host": host,
                "login": login,
                "password": password,
            })
            result["service"] = service

        alt_pattern = re.compile(
            r"\[\d+\]\[([^\]]+)\].*?login:\s*(\S+)\s+password:\s*(\S*)",
            re.IGNORECASE,
        )
        if not result["found_credentials"]:
            for match in alt_pattern.finditer(stdout):
                service, login, password = match.groups()
                result["found_credentials"].append({
                    "service": service,
                    "login": login,
                    "password": password,
                })
                result["service"] = service

        result["successful"] = len(result["found_credentials"])

        attempts_match = re.search(
            r"(\d+)\s+(?:valid password|of \d+ target)",
            stdout,
            re.IGNORECASE,
        )
        if attempts_match:
            result["attempts"] = int(attempts_match.group(1))

        total_match = re.search(r"(\d+)\s+tries", stdout, re.IGNORECASE)
        if total_match:
            result["attempts"] = int(total_match.group(1))

        return result


hydra_parser = HydraParser()
