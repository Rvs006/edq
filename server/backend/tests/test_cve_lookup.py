"""Tests for the CVE lookup service — unit tests with mocked NVD API."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.cve_lookup import (
    _normalise_product,
    _build_keyword_query,
    lookup_cves_for_services,
    lookup_cves_by_keyword,
)


class TestNormaliseProduct:
    """Tests for _normalise_product()."""

    def test_basic_normalisation(self):
        assert _normalise_product("Apache httpd") == "apache_httpd"

    def test_removes_special_chars(self):
        assert _normalise_product("Open-SSH/2.0") == "open_ssh_2_0"

    def test_lowercase(self):
        assert _normalise_product("NGINX") == "nginx"

    def test_strips_underscores(self):
        result = _normalise_product("  test  ")
        assert not result.startswith("_")
        assert not result.endswith("_")


class TestBuildKeywordQuery:
    """Tests for _build_keyword_query()."""

    def test_service_and_version(self):
        result = _build_keyword_query("http", "Apache httpd 2.4.49")
        assert "http" in result
        assert "2.4.49" in result

    def test_service_only(self):
        result = _build_keyword_query("ssh", "")
        assert result == "ssh"

    def test_version_only(self):
        result = _build_keyword_query("", "2.4.49")
        assert "2.4.49" in result

    def test_empty_inputs(self):
        result = _build_keyword_query("", "")
        assert result == ""

    def test_strips_protocol_suffix(self):
        result = _build_keyword_query("http/ssl", "Apache 2.4")
        assert "http" in result


class TestLookupCvesForServices:
    """Tests for lookup_cves_for_services() with mocked NVD API."""

    @pytest.mark.asyncio
    async def test_skips_services_without_version(self):
        services = [{"port": 80, "service": "http", "version": ""}]
        results = await lookup_cves_for_services(services)
        assert results == []

    @pytest.mark.asyncio
    async def test_skips_unknown_version(self):
        services = [{"port": 22, "service": "ssh", "version": "unknown"}]
        results = await lookup_cves_for_services(services)
        assert results == []

    @pytest.mark.asyncio
    async def test_skips_short_queries(self):
        services = [{"port": 80, "service": "h", "version": "v"}]
        results = await lookup_cves_for_services(services)
        assert results == []

    @pytest.mark.asyncio
    @patch("app.services.cve_lookup._query_nvd")
    async def test_returns_results_for_valid_service(self, mock_query):
        mock_query.return_value = [
            {
                "id": "CVE-2021-41773",
                "description": "Path traversal in Apache",
                "severity": "CRITICAL",
                "cvss_score": 9.8,
                "url": "https://nvd.nist.gov/vuln/detail/CVE-2021-41773",
            }
        ]
        services = [{"port": 80, "service": "http", "version": "Apache httpd 2.4.49"}]
        results = await lookup_cves_for_services(services, max_results_per_service=5)
        assert len(results) == 1
        assert results[0]["port"] == 80
        assert results[0]["cves"][0]["id"] == "CVE-2021-41773"

    @pytest.mark.asyncio
    @patch("app.services.cve_lookup._query_nvd")
    async def test_empty_nvd_response(self, mock_query):
        mock_query.return_value = []
        services = [{"port": 22, "service": "ssh", "version": "OpenSSH 8.9"}]
        results = await lookup_cves_for_services(services)
        assert results == []


class TestLookupCvesByKeyword:
    """Tests for lookup_cves_by_keyword()."""

    @pytest.mark.asyncio
    @patch("app.services.cve_lookup._query_nvd")
    async def test_delegates_to_query_nvd(self, mock_query):
        mock_query.return_value = [{"id": "CVE-2023-1234"}]
        results = await lookup_cves_by_keyword("apache 2.4")
        mock_query.assert_called_once_with("apache 2.4", 10)
        assert len(results) == 1
