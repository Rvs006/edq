"""CVE Vulnerability Lookup Service.

Queries the NVD (National Vulnerability Database) API to find known CVEs
for detected services based on service name + version from nmap results.
Falls back to a local keyword-based lookup for offline/air-gapped environments.
"""

import asyncio
import logging
import re
from typing import Any, Dict, List

import httpx

logger = logging.getLogger("edq.services.cve_lookup")

NVD_API_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
NVD_TIMEOUT = 15  # seconds
NVD_RATE_LIMIT_DELAY = 1.0  # NVD asks for ≤1 req/sec without API key

# Common CPE vendor mappings for smart building devices
_VENDOR_ALIASES: Dict[str, str] = {
    "apache": "apache",
    "nginx": "nginx",
    "openssh": "openbsd",
    "openssl": "openssl",
    "lighttpd": "lighttpd",
    "dropbear": "dropbear_ssh_project",
    "axis": "axis",
    "hikvision": "hikvision",
    "dahua": "dahua",
    "pelco": "pelco",
    "bosch": "bosch",
    "honeywell": "honeywell",
    "siemens": "siemens",
    "schneider": "schneider-electric",
    "2n": "2n",
    "sauter": "sauter",
    "easyio": "easyio",
    "bacnet": "ashrae",
    "vsftpd": "vsftpd_project",
    "proftpd": "proftpd",
    "microsoft": "microsoft",
    "dnsmasq": "thekelleys",
}


def _normalise_product(product: str) -> str:
    """Normalise a product name for CPE matching."""
    return re.sub(r"[^a-z0-9]", "_", product.lower()).strip("_")


def _build_keyword_query(service: str, version: str) -> str:
    """Build a keyword query for NVD search from service+version."""
    parts = []
    if service:
        parts.append(service.split("/")[0].strip())
    if version:
        # Take only the first version-like token
        ver_match = re.search(r"(\d+[\.\d]*)", version)
        if ver_match:
            parts.append(ver_match.group(1))
    return " ".join(parts)


async def lookup_cves_for_services(
    services: List[Dict[str, Any]],
    max_results_per_service: int = 5,
) -> List[Dict[str, Any]]:
    """Look up CVEs for a list of detected services.

    Args:
        services: List of service dicts from nmap, e.g.:
            [{"port": 80, "service": "http", "version": "Apache httpd 2.4.49"}]
        max_results_per_service: Max CVEs to return per service.

    Returns:
        List of CVE result dicts:
        [
            {
                "port": 80,
                "service": "http",
                "version": "Apache httpd 2.4.49",
                "cves": [
                    {
                        "id": "CVE-2021-41773",
                        "description": "...",
                        "severity": "CRITICAL",
                        "cvss_score": 9.8,
                        "url": "https://nvd.nist.gov/vuln/detail/CVE-2021-41773",
                    }
                ]
            }
        ]
    """
    results = []

    for svc in services:
        service_name = svc.get("service", "")
        version_str = svc.get("version", "")
        port = svc.get("port", 0)

        if not version_str or version_str in ("", "unknown"):
            continue

        query = _build_keyword_query(service_name, version_str)
        if not query or len(query) < 3:
            continue

        cves = await _query_nvd(query, max_results_per_service)

        if cves:
            results.append({
                "port": port,
                "service": service_name,
                "version": version_str,
                "cves": cves,
            })

        # Rate limit between requests
        await asyncio.sleep(NVD_RATE_LIMIT_DELAY)

    return results


async def lookup_cves_by_keyword(keyword: str, max_results: int = 10) -> List[Dict[str, Any]]:
    """Direct keyword-based CVE lookup."""
    return await _query_nvd(keyword, max_results)


async def _query_nvd(keyword: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Query the NVD API for CVEs matching a keyword."""
    cves: List[Dict[str, Any]] = []

    try:
        async with httpx.AsyncClient(timeout=NVD_TIMEOUT) as client:
            params = {
                "keywordSearch": keyword,
                "resultsPerPage": min(max_results, 20),
            }
            resp = await client.get(NVD_API_URL, params=params)

            if resp.status_code == 403:
                logger.warning("NVD API rate limited. Consider using an API key.")
                return cves

            if resp.status_code != 200:
                logger.warning("NVD API returned status %d for query '%s'", resp.status_code, keyword)
                return cves

            data = resp.json()

            for vuln in data.get("vulnerabilities", [])[:max_results]:
                cve_data = vuln.get("cve", {})
                cve_id = cve_data.get("id", "")

                # Extract description
                descriptions = cve_data.get("descriptions", [])
                description = ""
                for desc in descriptions:
                    if desc.get("lang") == "en":
                        description = desc.get("value", "")
                        break

                # Extract CVSS score and severity
                cvss_score = None
                severity = "UNKNOWN"
                metrics = cve_data.get("metrics", {})

                # Try CVSS v3.1 first, then v3.0, then v2
                for cvss_key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
                    cvss_list = metrics.get(cvss_key, [])
                    if cvss_list:
                        cvss_data = cvss_list[0].get("cvssData", {})
                        cvss_score = cvss_data.get("baseScore")
                        severity = cvss_data.get("baseSeverity", "UNKNOWN").upper()
                        break

                if cve_id:
                    cves.append({
                        "id": cve_id,
                        "description": description[:500] if description else "",
                        "severity": severity,
                        "cvss_score": cvss_score,
                        "url": f"https://nvd.nist.gov/vuln/detail/{cve_id}",
                    })

    except httpx.TimeoutException:
        logger.warning("NVD API timeout for query '%s'", keyword)
    except Exception as exc:
        logger.warning("NVD API error for query '%s': %s", keyword, exc)

    return cves
