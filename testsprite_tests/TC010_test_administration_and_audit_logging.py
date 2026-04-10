import requests

BASE_URL = "http://localhost:8000/api/v1"
ADMIN_USERNAME = "admin@example.com"
ADMIN_PASSWORD = "AdminPass123!"  # Updated to meet password policy
TIMEOUT = 30


def test_administration_and_audit_logging():
    session = requests.Session()
    try:
        # Step 1: Login as admin to get session cookies and CSRF token
        login_url = f"{BASE_URL}/auth/login"
        login_payload = {"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD}
        login_resp = session.post(login_url, json=login_payload, timeout=TIMEOUT)
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"

        # Extract CSRF token cookie and prepare header for mutating requests
        csrf_token = None
        for cookie in session.cookies:
            if cookie.name == "csrf_access_token" or cookie.name == "csrf_refresh_token":
                csrf_token = cookie.value
                break
        # If csrf_access_token not found, check header or other cookies
        if not csrf_token:
            # Try to get from response header (common for double-submit)
            csrf_token = login_resp.headers.get("x-csrf-token")
        assert csrf_token, "CSRF token not found after login"

        csrf_header = {"X-CSRF-Token": csrf_token}

        # Step 2: Create a new admin user with role assignment
        # User creation endpoint, assuming /admin/users
        create_user_url = f"{BASE_URL}/admin/users"
        new_user_payload = {
            "username": "test_admin_user",
            "password": "SecurePass123!",
            "roles": ["admin"]
        }
        create_resp = session.post(create_user_url, json=new_user_payload, headers=csrf_header, timeout=TIMEOUT)
        assert create_resp.status_code == 201, f"User creation failed: {create_resp.text}"
        created_user = create_resp.json()
        created_user_id = created_user.get("id")
        assert created_user_id, "Created user ID not returned"

        # Step 3: View audit logs with filters
        # Assume audit logs endpoint supports query params e.g. ?user=test_admin_user
        audit_logs_url = f"{BASE_URL}/audit_logs"
        params = {"user": "test_admin_user", "limit": 5}
        audit_resp = session.get(audit_logs_url, params=params, timeout=TIMEOUT)
        assert audit_resp.status_code == 200, f"Audit log fetch failed: {audit_resp.text}"
        logs = audit_resp.json()
        assert isinstance(logs, list), "Audit logs response is not a list"
        if logs:
            first_log = logs[0]
            audit_log_id = first_log.get("id")
            assert audit_log_id, "Audit log entry missing id"

            # Step 4: View detailed audit log entry
            detail_url = f"{audit_logs_url}/{audit_log_id}"
            detail_resp = session.get(detail_url, timeout=TIMEOUT)
            assert detail_resp.status_code == 200, f"Audit log detail fetch failed: {detail_resp.text}"
            detail_data = detail_resp.json()
            assert detail_data.get("id") == audit_log_id, "Audit log detail id mismatch"
        else:
            # No logs returned - this can be valid if system just created user with logs delayed
            audit_log_id = None

        # Step 5: Export filtered audit logs as CSV
        # Assuming /audit_logs/export supports filters and format param
        export_url = f"{BASE_URL}/audit_logs/export"
        export_params = {"user": "test_admin_user", "format": "csv"}
        export_resp = session.get(export_url, params=export_params, timeout=TIMEOUT)
        assert export_resp.status_code == 200, f"Audit log CSV export failed: {export_resp.text}"
        content_type = export_resp.headers.get("Content-Type", "")
        assert "text/csv" in content_type or "application/csv" in content_type, "Exported file is not CSV"
        content_disposition = export_resp.headers.get("Content-Disposition", "")
        assert "filename=" in content_disposition, "Content-Disposition header missing filename"

    finally:
        # Cleanup: Delete the created user if created_user_id is set
        if 'created_user_id' in locals():
            delete_user_url = f"{BASE_URL}/admin/users/{created_user_id}"
            try:
                del_resp = session.delete(delete_user_url, headers=csrf_header, timeout=TIMEOUT)
                # Allow 204 No Content or 200 OK for successful deletion
                assert del_resp.status_code in (200, 204), f"User deletion failed: {del_resp.text}"
            except Exception as e:
                print(f"Cleanup failed: could not delete user {created_user_id}: {e}")


test_administration_and_audit_logging()
