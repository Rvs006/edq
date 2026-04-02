"""Tests for the DeviceFingerprinter service.

Covers heuristic classification, port-based skip logic, profile matching,
and auto-learn from completed runs.
"""

import pytest
from httpx import AsyncClient

from tests.conftest import register_and_login
from app.services.device_fingerprinter import DeviceFingerprinter, FingerprintResult


# ---------------------------------------------------------------------------
# Unit tests — no DB needed, test pure logic
# ---------------------------------------------------------------------------

class TestPortSkips:
    """Test _compute_port_skips for every port-based rule."""

    def setup_method(self):
        self.fp = DeviceFingerprinter()

    def test_no_https_skips_tls_tests(self):
        skips = self.fp._compute_port_skips({80})
        assert "U10" in skips
        assert "U11" in skips
        assert "U12" in skips
        assert "U13" in skips

    def test_https_present_keeps_tls_tests(self):
        skips = self.fp._compute_port_skips({80, 443})
        assert "U10" not in skips
        assert "U11" not in skips

    def test_no_ssh_skips_u15(self):
        skips = self.fp._compute_port_skips({80, 443})
        assert "U15" in skips

    def test_ssh_present_keeps_u15(self):
        skips = self.fp._compute_port_skips({22, 80, 443})
        assert "U15" not in skips

    def test_no_rtsp_skips_u37(self):
        skips = self.fp._compute_port_skips({80})
        assert "U37" in skips

    def test_rtsp_present_keeps_u37(self):
        skips = self.fp._compute_port_skips({80, 554})
        assert "U37" not in skips

    def test_no_http_at_all_skips_http_tests(self):
        skips = self.fp._compute_port_skips({22, 554})
        for tid in ["U14", "U16", "U17", "U18", "U35"]:
            assert tid in skips, f"{tid} should be skipped when no HTTP ports"

    def test_http_80_keeps_http_tests(self):
        skips = self.fp._compute_port_skips({80})
        for tid in ["U14", "U16", "U17", "U18", "U35"]:
            assert tid not in skips

    def test_no_snmp_skips_u31(self):
        skips = self.fp._compute_port_skips({80})
        assert "U31" in skips

    def test_snmp_161_keeps_u31(self):
        skips = self.fp._compute_port_skips({80, 161})
        assert "U31" not in skips

    def test_snmp_162_keeps_u31(self):
        skips = self.fp._compute_port_skips({80, 162})
        assert "U31" not in skips

    def test_no_upnp_skips_u32(self):
        skips = self.fp._compute_port_skips({80})
        assert "U32" in skips

    def test_upnp_present_keeps_u32(self):
        skips = self.fp._compute_port_skips({80, 1900})
        assert "U32" not in skips

    def test_no_mdns_skips_u33(self):
        skips = self.fp._compute_port_skips({80})
        assert "U33" in skips

    def test_mdns_present_keeps_u33(self):
        skips = self.fp._compute_port_skips({80, 5353})
        assert "U33" not in skips

    def test_all_ports_present_skips_nothing(self):
        all_ports = {22, 80, 161, 162, 443, 554, 1900, 5353}
        skips = self.fp._compute_port_skips(all_ports)
        assert skips == {}

    def test_empty_ports_skips_everything(self):
        skips = self.fp._compute_port_skips(set())
        expected = {"U10", "U11", "U12", "U13", "U14", "U15", "U16", "U17",
                    "U18", "U31", "U32", "U33", "U35", "U37"}
        assert set(skips) == expected


class TestHeuristicClassification:
    """Test _heuristic_classify for each device category."""

    def setup_method(self):
        self.fp = DeviceFingerprinter()

    def test_bacnet_port_classified_as_controller(self):
        result = self.fp._heuristic_classify({47808, 80}, {}, "")
        assert result.category == "controller"
        assert result.confidence == "high"

    def test_easyio_vendor_classified_as_controller(self):
        result = self.fp._heuristic_classify({80}, {}, "EasyIO Corporation")
        assert result.category == "controller"
        assert result.confidence == "high"

    def test_honeywell_vendor_classified_as_controller(self):
        result = self.fp._heuristic_classify({80}, {}, "Honeywell International")
        assert result.category == "controller"

    def test_rtsp_port_classified_as_camera(self):
        result = self.fp._heuristic_classify({554, 80}, {}, "")
        assert result.category == "camera"
        assert result.confidence == "high"

    def test_hikvision_vendor_classified_as_camera(self):
        result = self.fp._heuristic_classify({80}, {}, "Hangzhou Hikvision")
        assert result.category == "camera"

    def test_axis_vendor_classified_as_camera(self):
        result = self.fp._heuristic_classify({80, 443}, {}, "Axis Communications")
        assert result.category == "camera"

    def test_rtsp_service_classified_as_camera(self):
        result = self.fp._heuristic_classify({8554}, {8554: "rtsp"}, "")
        assert result.category == "camera"

    def test_sip_port_classified_as_intercom(self):
        result = self.fp._heuristic_classify({5060, 80}, {}, "")
        assert result.category == "intercom"
        assert result.confidence == "high"

    def test_2n_vendor_classified_as_intercom(self):
        result = self.fp._heuristic_classify({80}, {}, "2N Telekomunikace")
        assert result.category == "intercom"

    def test_hid_vendor_classified_as_access_panel(self):
        result = self.fp._heuristic_classify({80}, {}, "HID Global")
        assert result.category == "access_panel"
        assert result.confidence == "high"

    def test_gallagher_vendor_classified_as_access_panel(self):
        result = self.fp._heuristic_classify({80}, {}, "Gallagher Group")
        assert result.category == "access_panel"

    def test_mqtt_port_classified_as_iot_sensor(self):
        result = self.fp._heuristic_classify({1883}, {}, "")
        assert result.category == "iot_sensor"
        assert result.confidence == "medium"

    def test_mqtts_port_classified_as_iot_sensor(self):
        result = self.fp._heuristic_classify({8883}, {}, "")
        assert result.category == "iot_sensor"

    def test_generic_http_device_fallback(self):
        result = self.fp._heuristic_classify({80}, {}, "Unknown Vendor Inc")
        assert result.category == "unknown"
        assert result.confidence == "low"

    def test_https_only_device_fallback(self):
        result = self.fp._heuristic_classify({443}, {}, "")
        assert result.category == "unknown"
        assert result.confidence == "low"

    def test_no_matching_ports_or_vendor(self):
        result = self.fp._heuristic_classify({12345}, {}, "Obscure Corp")
        # Should still match the generic fallback (port 80/443) — won't match
        # since 12345 is not 80 or 443. Falls through all rules.
        assert result.category == "unknown"
        assert result.confidence == "low"

    def test_vendor_match_is_case_insensitive(self):
        result = self.fp._heuristic_classify({80}, {}, "HIKVISION DIGITAL")
        assert result.category == "camera"

    def test_priority_bacnet_over_generic(self):
        """BACnet port should match controller, not fall through to generic."""
        result = self.fp._heuristic_classify({47808, 80, 443}, {}, "")
        assert result.category == "controller"


class TestExtractHelpers:
    """Test _extract_ports and _extract_services."""

    def setup_method(self):
        self.fp = DeviceFingerprinter()

    def test_extract_ports_normal(self):
        data = {"open_ports": [{"port": 80, "service": "http"}, {"port": 443, "service": "https"}]}
        assert self.fp._extract_ports(data) == {80, 443}

    def test_extract_ports_empty(self):
        assert self.fp._extract_ports({}) == set()
        assert self.fp._extract_ports({"open_ports": []}) == set()

    def test_extract_ports_malformed(self):
        data = {"open_ports": [{"port": "not_a_number"}, {}, {"port": 22}]}
        assert self.fp._extract_ports(data) == {22}

    def test_extract_services_normal(self):
        data = {"open_ports": [
            {"port": 80, "service": "http"},
            {"port": 22, "service": "ssh"},
            {"port": 554, "name": "rtsp"},
        ]}
        services = self.fp._extract_services(data)
        assert services == {80: "http", 22: "ssh", 554: "rtsp"}

    def test_extract_services_empty(self):
        assert self.fp._extract_services({}) == {}

    def test_extract_services_no_service_field(self):
        data = {"open_ports": [{"port": 80}]}
        assert self.fp._extract_services(data) == {}


# ---------------------------------------------------------------------------
# Integration tests — need DB via client fixture
# ---------------------------------------------------------------------------

class TestFingerprintEndToEnd:
    """Test full fingerprint flow against the database."""

    @pytest.mark.asyncio
    async def test_fingerprint_easyio_device(self, db_session):
        """Simulate fingerprinting an EasyIO FW-14 (the test device)."""
        from app.models.device import Device, DeviceCategory

        device = Device(
            ip_address="192.168.1.10",
            mac_address="AA:BB:CC:DD:EE:FF",
            oui_vendor="EasyIO",
            category=DeviceCategory.UNKNOWN,
        )
        db_session.add(device)
        await db_session.flush()
        await db_session.refresh(device)

        fp = DeviceFingerprinter()
        u08_data = {
            "open_ports": [
                {"port": 80, "service": "http", "version": "nginx 1.29.7"},
                {"port": 135, "service": "msrpc"},
                {"port": 139, "service": "netbios-ssn"},
                {"port": 445, "service": "microsoft-ds"},
                {"port": 5432, "service": "postgresql"},
            ]
        }
        u02_data = {"oui_vendor": "EasyIO", "mac_address": "AA:BB:CC:DD:EE:FF"}

        result = await fp.fingerprint(db_session, device.id, u08_data, u02_data)

        assert result.category == "controller"
        assert result.confidence == "high"
        assert "U10" in result.skip_test_ids  # No HTTPS
        assert "U15" in result.skip_test_ids  # No SSH
        assert "U37" in result.skip_test_ids  # No RTSP

        # Device should be updated
        await db_session.refresh(device)
        assert device.category == DeviceCategory.CONTROLLER

    @pytest.mark.asyncio
    async def test_fingerprint_ip_camera(self, db_session):
        """Simulate fingerprinting a Hikvision camera."""
        from app.models.device import Device, DeviceCategory

        device = Device(
            ip_address="192.168.1.20",
            oui_vendor="Hikvision",
            category=DeviceCategory.UNKNOWN,
        )
        db_session.add(device)
        await db_session.flush()
        await db_session.refresh(device)

        fp = DeviceFingerprinter()
        u08_data = {
            "open_ports": [
                {"port": 80, "service": "http"},
                {"port": 443, "service": "https"},
                {"port": 554, "service": "rtsp"},
                {"port": 8000, "service": "http-alt"},
            ]
        }
        u02_data = {"oui_vendor": "Hikvision", "mac_address": "11:22:33:44:55:66"}

        result = await fp.fingerprint(db_session, device.id, u08_data, u02_data)

        assert result.category == "camera"
        assert result.confidence == "high"
        assert "U37" not in result.skip_test_ids  # RTSP present, keep U37
        assert "U10" not in result.skip_test_ids  # HTTPS present, keep TLS tests
        assert "U15" in result.skip_test_ids       # No SSH

        await db_session.refresh(device)
        assert device.category == DeviceCategory.CAMERA

    @pytest.mark.asyncio
    async def test_fingerprint_unknown_device(self, db_session):
        """Unknown vendor with only HTTP — classified as unknown/low."""
        from app.models.device import Device, DeviceCategory

        device = Device(
            ip_address="192.168.1.30",
            oui_vendor="",
            category=DeviceCategory.UNKNOWN,
        )
        db_session.add(device)
        await db_session.flush()
        await db_session.refresh(device)

        fp = DeviceFingerprinter()
        u08_data = {"open_ports": [{"port": 80, "service": "http"}]}
        u02_data = {"oui_vendor": "", "mac_address": ""}

        result = await fp.fingerprint(db_session, device.id, u08_data, u02_data)

        assert result.category == "unknown"
        assert result.confidence == "low"


class TestAutoLearnEndpoint:
    """Test the POST /device-profiles/auto-learn API endpoint."""

    @pytest.mark.asyncio
    async def test_auto_learn_no_run_returns_404(self, client: AsyncClient):
        headers = await register_and_login(client, "autolearn", role="admin")
        resp = await client.post(
            "/api/device-profiles/auto-learn",
            json={"test_run_id": "nonexistent-id"},
            headers=headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_auto_learn_requires_auth(self, client: AsyncClient):
        resp = await client.post(
            "/api/device-profiles/auto-learn",
            json={"test_run_id": "some-id"},
        )
        assert resp.status_code == 401


class TestProfileMatchingWithDB:
    """Test profile matching against saved DeviceProfiles."""

    @pytest.mark.asyncio
    async def test_matches_saved_profile(self, db_session):
        """A saved profile with matching vendor + ports should match."""
        from app.models.device import Device, DeviceCategory
        from app.models.device_profile import DeviceProfile

        profile = DeviceProfile(
            name="Test Camera Profile",
            manufacturer="Axis",
            category="camera",
            fingerprint_rules={
                "required_ports": [80, 554],
                "vendors": ["axis"],
                "services": ["rtsp"],
            },
        )
        db_session.add(profile)
        await db_session.flush()

        device = Device(
            ip_address="192.168.1.40",
            oui_vendor="Axis Communications",
            category=DeviceCategory.UNKNOWN,
        )
        db_session.add(device)
        await db_session.flush()
        await db_session.refresh(device)

        fp = DeviceFingerprinter()
        u08_data = {
            "open_ports": [
                {"port": 80, "service": "http"},
                {"port": 554, "service": "rtsp"},
            ]
        }
        u02_data = {"oui_vendor": "Axis Communications"}

        result = await fp.fingerprint(db_session, device.id, u08_data, u02_data)

        assert result.matched_profile_id == profile.id
        assert result.matched_profile_name == "Test Camera Profile"
        assert result.confidence in ("high", "medium")
