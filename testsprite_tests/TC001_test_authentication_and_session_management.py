import requests

BASE_URL = "http://localhost:8000/api/v1"
LOGIN_URL = f"{BASE_URL}/auth/login"
HEALTH_URL = f"{BASE_URL}/health"


def test_authentication_and_session_management():
    session = requests.Session()
    timeout = 30

    # Check health endpoint to ensure backend is up
    health_resp = session.get(HEALTH_URL, timeout=timeout)
    assert health_resp.status_code == 200
    health_json = health_resp.json()
    status_value = health_json.get("status")
    assert status_value is not None and any(s in str(status_value).lower() for s in ("ok", "healthy"))

    # Prepare valid admin credentials
    valid_credentials = {
        "email": "admin",
        "password": "admin"  # Assuming default or known admin password; if unknown, test cannot proceed meaningfully
    }

    # 1) Test login with valid credentials
    headers = {"Content-Type": "application/json"}
    resp = session.post(LOGIN_URL, json=valid_credentials, headers=headers, timeout=timeout)
    assert resp.status_code == 200
    # Expecting JSON response with token or session cookie and possibly user info
    json_resp = resp.json()
    assert "access_token" in json_resp or "token" in json_resp or resp.cookies or resp.headers.get("set-cookie")

    # Extract JWT token from response if present or cookie
    access_token = json_resp.get("access_token") or json_resp.get("token")
    if access_token:
        auth_headers = {"Authorization": f"Bearer {access_token}"}
    else:
        auth_headers = {}

    # Since CSRF protection enabled on mutating requests we try a GET on dashboard 
    # (which should not require CSRF token) to verify session/authentication success
    dashboard_resp = session.get(BASE_URL, headers=auth_headers, timeout=timeout)
    # Accept 200 OK
    assert dashboard_resp.status_code == 200

    # 2) Test login with invalid credentials
    invalid_credentials = {
        "email": "admin",
        "password": "wrongpassword123!"
    }
    invalid_resp = session.post(LOGIN_URL, json=invalid_credentials, headers=headers, timeout=timeout)
    assert invalid_resp.status_code in (400, 401, 403)
    invalid_json = invalid_resp.json()
    # Check for validation error message about invalid credentials
    errors = invalid_json.get("detail") or invalid_json.get("error") or invalid_json.get("message")
    assert errors is not None
    invalid_msgs = [
        "invalid credentials",
        "incorrect username or password",
        "authentication failed",
        "unauthorized"
    ]
    assert any(msg.lower() in str(errors).lower() for msg in invalid_msgs)


test_authentication_and_session_management()
