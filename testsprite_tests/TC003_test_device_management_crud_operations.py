import requests

BASE_URL = "http://localhost:8000/api/v1"
ADMIN_EMAIL = "admin"
ADMIN_PASSWORD = "adminadmin"  # Password updated to meet minimum length requirement


def test_device_management_crud_operations():
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})
    timeout = 30

    # 1. Login to get JWT cookie and CSRF token
    login_payload = {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    login_resp = session.post(f"{BASE_URL}/auth/login", json=login_payload, timeout=timeout)
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"

    # The server should set cookies including the csrf token in a cookie, extract it for header usage
    csrf_token = session.cookies.get("csrf_access_token") or session.cookies.get("csrf_refresh_token") or ""
    assert csrf_token, "CSRF token cookie not found after login"

    # Add CSRF token to headers for mutating requests
    session.headers.update({"X-CSRF-Token": csrf_token})

    created_device_id = None
    created_profile_id = None
    try:
        # 2. Add a new device
        new_device_payload = {
            "name": "Test Device TC003",
            "ip": "192.168.100.100",
            "mac": "00:11:22:33:44:55",
            "type": "sensor",
            "location": "Test Lab",
            "description": "Device added by test_device_management_crud_operations",
        }
        device_create_resp = session.post(f"{BASE_URL}/devices", json=new_device_payload, timeout=timeout)
        assert device_create_resp.status_code == 201, f"Failed to create device: {device_create_resp.text}"
        device_data = device_create_resp.json()
        created_device_id = device_data.get("id")
        assert created_device_id, "Created device id missing"

        # 3. View device details including fingerprint and history
        device_detail_resp = session.get(f"{BASE_URL}/devices/{created_device_id}", timeout=timeout)
        assert device_detail_resp.status_code == 200, f"Failed to get device details: {device_detail_resp.text}"
        device_detail = device_detail_resp.json()
        # Validate basic fields returned
        assert device_detail.get("id") == created_device_id
        assert device_detail.get("name") == new_device_payload["name"]
        # Fingerprint and history expected in detail
        assert "fingerprint" in device_detail, "Fingerprint missing in device details"
        assert "history" in device_detail, "History missing in device details"

        # 4. Create a device profile
        new_profile_payload = {
            "name": "Test Profile TC003",
            "description": "Profile created by test_device_management_crud_operations",
            "settings": {
                "scan_interval": 3600,
                "alert_threshold": 5,
                "enabled": True
            }
        }
        profile_create_resp = session.post(f"{BASE_URL}/device_profiles", json=new_profile_payload, timeout=timeout)
        assert profile_create_resp.status_code == 201, f"Failed to create device profile: {profile_create_resp.text}"
        profile_data = profile_create_resp.json()
        created_profile_id = profile_data.get("id")
        assert created_profile_id, "Created profile id missing"

        # 5. Edit the device profile
        edit_profile_payload = {
            "name": "Test Profile TC003 Edited",
            "description": "Edited profile description",
            "settings": {
                "scan_interval": 7200,
                "alert_threshold": 3,
                "enabled": False
            }
        }
        profile_edit_resp = session.put(f"{BASE_URL}/device_profiles/{created_profile_id}", json=edit_profile_payload, timeout=timeout)
        assert profile_edit_resp.status_code == 200, f"Failed to edit device profile: {profile_edit_resp.text}"
        edited_profile = profile_edit_resp.json()
        assert edited_profile.get("name") == edit_profile_payload["name"]
        assert edited_profile.get("description") == edit_profile_payload["description"]

    finally:
        # Cleanup: delete created device and profile to keep environment clean
        if created_device_id:
            del_dev_resp = session.delete(f"{BASE_URL}/devices/{created_device_id}", headers={"X-CSRF-Token": csrf_token}, timeout=timeout)
            assert del_dev_resp.status_code in (200, 204), f"Failed to delete device: {del_dev_resp.text}"
        if created_profile_id:
            del_prof_resp = session.delete(f"{BASE_URL}/device_profiles/{created_profile_id}", headers={"X-CSRF-Token": csrf_token}, timeout=timeout)
            assert del_prof_resp.status_code in (200, 204), f"Failed to delete device profile: {del_prof_resp.text}"


test_device_management_crud_operations()
