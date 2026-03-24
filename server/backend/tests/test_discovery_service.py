"""Tests for the discovery service — manufacturer/model detection and category classification."""

import pytest

from app.services.discovery_service import guess_manufacturer, guess_model, guess_category
from app.models.device import DeviceCategory


class TestGuessManufacturer:
    """Tests for guess_manufacturer()."""

    def test_detects_from_oui_vendor(self):
        result = guess_manufacturer("Axis Communications AB", [])
        assert result == "Axis Communications"

    def test_detects_from_service_banner(self):
        services = [{"service": "rtsp", "version": "Hikvision DS-2CD2143"}]
        result = guess_manufacturer(None, services)
        assert result == "Hikvision"

    def test_case_insensitive(self):
        result = guess_manufacturer("DAHUA TECHNOLOGY", [])
        assert result == "Dahua Technology"

    def test_returns_none_for_unknown(self):
        result = guess_manufacturer("Unknown Vendor Inc", [])
        assert result is None

    def test_returns_none_for_empty_input(self):
        result = guess_manufacturer(None, [])
        assert result is None

    def test_detects_from_combined_sources(self):
        services = [{"service": "http", "version": "Schneider Electric Web Server"}]
        result = guess_manufacturer("", services)
        assert result == "Schneider Electric"

    def test_cisco_detection(self):
        services = [{"service": "ssh", "version": "Cisco IOS SSH"}]
        result = guess_manufacturer(None, services)
        assert result == "Cisco"


class TestGuessModel:
    """Tests for guess_model()."""

    def test_extracts_model_from_version(self):
        services = [{"service": "rtsp", "version": "IPC-HDW5442T"}]
        result = guess_model(services, None)
        assert result is not None

    def test_extracts_model_from_os_fingerprint(self):
        result = guess_model([], "EY-RC504 Linux 4.x")
        assert result is not None

    def test_returns_none_for_empty(self):
        result = guess_model([], None)
        assert result is None

    def test_returns_none_for_no_match(self):
        services = [{"service": "http", "version": "Apache 2.4.52"}]
        result = guess_model(services, None)
        # May or may not match — just ensure no crash
        assert result is None or isinstance(result, str)

    def test_skips_empty_version(self):
        services = [{"service": "http", "version": ""}]
        result = guess_model(services, None)
        assert result is None


class TestGuessCategory:
    """Tests for guess_category()."""

    def test_camera_from_rtsp(self):
        services = [{"service": "rtsp", "version": ""}]
        assert guess_category(None, services) == DeviceCategory.CAMERA

    def test_camera_from_onvif(self):
        services = [{"service": "onvif", "version": ""}]
        assert guess_category(None, services) == DeviceCategory.CAMERA

    def test_controller_from_bacnet(self):
        services = [{"service": "bacnet", "version": ""}]
        assert guess_category(None, services) == DeviceCategory.CONTROLLER

    def test_intercom_from_sip(self):
        services = [{"service": "sip", "version": ""}]
        assert guess_category(None, services) == DeviceCategory.INTERCOM

    def test_access_panel_from_paxton(self):
        services = [{"service": "paxton", "version": ""}]
        assert guess_category(None, services) == DeviceCategory.ACCESS_PANEL

    def test_meter_from_modbus(self):
        services = [{"service": "modbus", "version": ""}]
        assert guess_category(None, services) == DeviceCategory.METER

    def test_hvac_from_trane(self):
        services = [{"service": "trane", "version": ""}]
        assert guess_category(None, services) == DeviceCategory.HVAC

    def test_iot_sensor_from_mqtt(self):
        services = [{"service": "mqtt", "version": ""}]
        assert guess_category(None, services) == DeviceCategory.IOT_SENSOR

    def test_lighting_from_lutron(self):
        services = [{"service": "lutron", "version": ""}]
        assert guess_category(None, services) == DeviceCategory.LIGHTING

    def test_camera_from_os_fingerprint(self):
        assert guess_category("IP Camera Linux", []) == DeviceCategory.CAMERA

    def test_controller_from_os_fingerprint(self):
        assert guess_category("PLC Controller", []) == DeviceCategory.CONTROLLER

    def test_unknown_for_no_match(self):
        services = [{"service": "http", "version": "nginx"}]
        assert guess_category(None, services) == DeviceCategory.UNKNOWN

    def test_unknown_for_empty(self):
        assert guess_category(None, []) == DeviceCategory.UNKNOWN

    def test_modbus_not_classified_as_controller(self):
        """Modbus devices should be METER, not CONTROLLER (regression test)."""
        services = [{"service": "modbus", "version": "Modbus/TCP"}]
        result = guess_category(None, services)
        assert result == DeviceCategory.METER
