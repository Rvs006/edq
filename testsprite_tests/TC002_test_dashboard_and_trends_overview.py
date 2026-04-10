import requests

BASE_URL = "http://localhost:8000/api/v1"
USERNAME = "admin"
PASSWORD = "admin"  # assuming password 'admin' for test; adjust if needed


def test_dashboard_and_trends_overview():
    session = requests.Session()
    timeout = 30

    # Step 1: Health check to ensure backend is up
    health_resp = session.get(f"{BASE_URL}/health", timeout=timeout)
    assert health_resp.status_code == 200, "Health check failed"

    # Step 2: Login to get authentication cookies/session and CSRF token
    login_payload = {"username": USERNAME, "password": PASSWORD}
    login_headers = {"Content-Type": "application/json"}
    login_resp = session.post(f"{BASE_URL}/auth/login", json=login_payload, headers=login_headers, timeout=timeout)
    assert login_resp.status_code == 200, f"Failed login with admin user, status: {login_resp.status_code}"

    # Extract CSRF token from cookies for subsequent requests (CSRF double-submit)
    csrf_token = None
    for cookie in session.cookies:
        if cookie.name == "csrf_access_token":
            csrf_token = cookie.value
            break
    assert csrf_token is not None, "CSRF token cookie not found after login"

    # Prepare headers for GET requests that might require CSRF token (GET usually doesn't mutate but safe to send)
    headers = {"X-CSRF-Token": csrf_token}

    # Step 3: Access dashboard summary counts endpoint(s)
    dashboard_summary_resp = session.get(f"{BASE_URL}/dashboard/summary", headers=headers, timeout=timeout)
    assert dashboard_summary_resp.status_code == 200, "Failed to get dashboard summary counts"
    dashboard_summary = dashboard_summary_resp.json()

    # Validate summary keys and that counts are integers >= 0
    for key in ("devices_count", "projects_count", "recent_test_runs_count"):
        assert key in dashboard_summary, f"{key} missing in dashboard summary"
        count = dashboard_summary[key]
        assert isinstance(count, int), f"{key} is not an integer"
        assert count >= 0, f"{key} count is negative"

    # Step 4: Access trend chart data endpoint, likely with optional time range filters
    trends_resp = session.get(f"{BASE_URL}/dashboard/trends", headers=headers, timeout=timeout)
    assert trends_resp.status_code == 200, "Failed to get dashboard trend charts"
    trends_data = trends_resp.json()
    assert isinstance(trends_data, dict), "Trend charts data is not a dict"
    assert "device_history" in trends_data, "device_history missing in trends data"
    assert isinstance(trends_data["device_history"], list), "device_history is not a list"
    assert "test_run_history" in trends_data, "test_run_history missing in trends data"
    assert isinstance(trends_data["test_run_history"], list), "test_run_history is not a list"

    # Step 5: Apply time range filter (e.g., last 7 days), verify updated trend charts
    import datetime

    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=7)
    params = {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}

    filtered_trends_resp = session.get(f"{BASE_URL}/dashboard/trends", headers=headers, params=params, timeout=timeout)
    assert filtered_trends_resp.status_code == 200, "Failed to get filtered dashboard trend charts"
    filtered_trends_data = filtered_trends_resp.json()

    assert isinstance(filtered_trends_data, dict), "Filtered trend charts data is not a dict"
    assert "device_history" in filtered_trends_data, "device_history missing in filtered trends data"
    assert isinstance(filtered_trends_data["device_history"], list), "device_history in filtered data is not a list"
    assert "test_run_history" in filtered_trends_data, "test_run_history missing in filtered trends data"
    assert isinstance(filtered_trends_data["test_run_history"], list), "test_run_history in filtered data is not a list"

    # Optionally validate filtered data length is <= unfiltered data length (assuming filtered is a subset)
    assert len(filtered_trends_data["device_history"]) <= len(trends_data["device_history"]), "Filtered device_history unexpectedly larger than unfiltered"
    assert len(filtered_trends_data["test_run_history"]) <= len(trends_data["test_run_history"]), "Filtered test_run_history unexpectedly larger than unfiltered"


test_dashboard_and_trends_overview()
