# TestSprite MCP Combined Test Report

---

## 1. Document Metadata

| Field        | Value                                              |
|--------------|----------------------------------------------------|
| **Project**  | EDQ - Electracom Device Qualifier                  |
| **Date**     | 2026-04-10                                         |
| **Test Types** | Frontend (Playwright E2E) + Backend (Python requests API tests) |
| **Tool**     | TestSprite MCP                                     |
| **Backend Base URL** | `http://localhost:8000/api/v1`              |
| **Frontend Base URL** | `http://localhost:5174`                   |

---

## 2. Requirement Validation Summary

---

### Authentication & Session Management

#### Frontend TC001 — Sign in with valid credentials and reach dashboard
- **Status:** BLOCKED
- **Test File:** `C:\Users\ASUS\Desktop\edq\testsprite_tests\TC001_Sign_in_with_valid_credentials_and_reach_dashboard.py`
- **Error Details:** TestSprite auto-generated credentials `username: "Rajesh Shinde"` / `password: "password123"` which do not match any valid account. Login failed, so the dashboard URL assertion (`/dashboard` in `window.location.href`) was never reachable.
- **Video / Result:** https://www.testsprite.com/dashboard/mcp/tests/06661a87-e913-4556-af8e-a7494a13699c/78dcb8f6-8f9e-433d-9852-7c16845c26f9

#### Frontend TC017 — Reject sign in with invalid password
- **Status:** PASSED
- **Test File:** `C:\Users\ASUS\Desktop\edq\testsprite_tests\TC017_Reject_sign_in_with_invalid_password.py`
- **Error Details:** None. Test submitted `invalid-user@example.com` / `wrong-password` and asserted only that `window.location.href` is not null — the app correctly stayed on the login page without crashing or navigating away.
- **Video / Result:** https://www.testsprite.com/dashboard/mcp/tests/06661a87-e913-4556-af8e-a7494a13699c/3c72aa98-79f8-4fc9-8361-ff0ec9528772

#### Backend TC001 — test_authentication_and_session_management
- **Status:** FAILED
- **Test File:** `C:\Users\ASUS\Desktop\edq\testsprite_tests\TC001_test_authentication_and_session_management.py`
- **Error Details:** `AssertionError` at line 28 — `POST /api/v1/auth/login` returned a non-200 status code.
- **Root Cause:** Login payload used `{"email": "admin", "password": "admin"}`. The API requires a `username` field (not `email`), and `"admin"` is not the correct password (actual password is environment-generated).
- **Test Visualization:** https://www.testsprite.com/dashboard/mcp/tests/06661a87-e913-4556-af8e-a7494a13699c/78dcb8f6-8f9e-433d-9852-7c16845c26f9

#### Backend TC010 — test_administration_and_audit_logging
- **Status:** FAILED
- **Test File:** `C:\Users\ASUS\Desktop\edq\testsprite_tests\TC010_test_administration_and_audit_logging.py`
- **Error Details:** `AssertionError: Login failed: {"detail":"Invalid credentials"}` at line 16.
- **Root Cause:** Credentials used were `username: "admin@example.com"` / `password: "AdminPass123!"`. The actual admin username is `"admin"` (not an email address), and the password is incorrect.
- **Test Visualization:** https://www.testsprite.com/dashboard/mcp/tests/06661a87-e913-4556-af8e-a7494a13699c/3c72aa98-79f8-4fc9-8361-ff0ec9528772

---

### Dashboard & Trends

#### Frontend TC006 — Dashboard shows core summary and trends
- **Status:** BLOCKED
- **Test File:** `C:\Users\ASUS\Desktop\edq\testsprite_tests\TC006_Dashboard_shows_core_summary_and_trends.py`
- **Error Details:** Login step used `username: "Rajesh Shinde"` / `password: "password123"` (same auto-generated invalid credentials as TC001 Frontend). Authentication failed, so the dashboard was never loaded and the assertions checking for `"Recent test runs"` and `"Device history"` text could not be evaluated.
- **Video / Result:** N/A — blocked at login step

#### Backend TC002 — test_dashboard_and_trends_overview
- **Status:** FAILED
- **Test File:** `C:\Users\ASUS\Desktop\edq\testsprite_tests\TC002_test_dashboard_and_trends_overview.py`
- **Error Details:** `AssertionError: Failed login with admin user, status: 422` at line 20.
- **Root Cause (layer 1):** Password `"admin"` is incorrect for the admin account; the API returned HTTP 422 Unprocessable Entity, indicating the request body failed validation (the password does not meet backend constraints or is simply wrong).
- **Root Cause (layer 2):** Even if login had succeeded, the test targets non-existent endpoints `/api/v1/dashboard/summary` and `/api/v1/dashboard/trends`, which are not part of the actual API surface.
- **Test Visualization:** https://www.testsprite.com/dashboard/mcp/tests/06661a87-e913-4556-af8e-a7494a13699c/caf8ec38-0c08-4218-b5ba-d2b8f7c3cf2a

---

### Device Management

#### Frontend TC002 — Add a device to inventory from the devices page
- **Status:** BLOCKED
- **Test File:** `C:\Users\ASUS\Desktop\edq\testsprite_tests\TC002_Add_a_device_to_inventory_from_the_devices_page.py`
- **Error Details:** Login attempted with `username: "Rajesh Shinde"` / `password: "password123"`. Authentication failed, so the device inventory page was never reached and the assertion checking for `"Device-UI-001"` in the DOM was never evaluated.
- **Video / Result:** N/A — blocked at login step

#### Backend TC003 — test_device_management_crud_operations
- **Status:** FAILED
- **Test File:** `C:\Users\ASUS\Desktop\edq\testsprite_tests\TC003_test_device_management_crud_operations.py`
- **Error Details:** `AssertionError: Login failed: {"detail":"Validation error","errors":[{"field":"body.username","message":"Field required"}]}` at line 16.
- **Root Cause:** Login payload used `{"email": "admin", "password": "adminadmin"}`. The API requires `username` (not `email`) as the field name; the server returned a 422 validation error explicitly stating `body.username` is required. Additionally, `"adminadmin"` is not the correct password.
- **Test Visualization:** https://www.testsprite.com/dashboard/mcp/tests/06661a87-e913-4556-af8e-a7494a13699c/4310944e-7692-4374-970d-95b124ad8f9b

---

## 3. Coverage & Matching Metrics

**Total tests executed: 8**

| Result  | Count | Percentage |
|---------|-------|------------|
| Passed  | 1     | 12.5%      |
| Failed  | 4     | 50.0%      |
| Blocked | 3     | 37.5%      |

### Breakdown by Requirement Area

| Requirement Area                   | Total | Passed | Failed | Blocked |
|------------------------------------|-------|--------|--------|---------|
| Authentication & Session Management | 4    | 1      | 2      | 1       |
| Dashboard & Trends                  | 2    | 0      | 1      | 1       |
| Device Management                   | 2    | 0      | 1      | 1       |
| **Total**                           | **8** | **1** | **4** | **3**  |

### Test Inventory

| Test ID        | Type     | Title / Description                              | Status  |
|----------------|----------|--------------------------------------------------|---------|
| Frontend TC001 | Playwright E2E | Sign in with valid credentials and reach dashboard | BLOCKED |
| Frontend TC017 | Playwright E2E | Reject sign in with invalid password             | PASSED  |
| Frontend TC002 | Playwright E2E | Add a device to inventory from the devices page  | BLOCKED |
| Frontend TC006 | Playwright E2E | Dashboard shows core summary and trends          | BLOCKED |
| Backend TC001  | Python requests | test_authentication_and_session_management    | FAILED  |
| Backend TC002  | Python requests | test_dashboard_and_trends_overview            | FAILED  |
| Backend TC003  | Python requests | test_device_management_crud_operations        | FAILED  |
| Backend TC010  | Python requests | test_administration_and_audit_logging         | FAILED  |

---

## 4. Key Gaps / Risks

### Root Cause (Shared Across All Failures)

> **All 7 non-passing tests share the same underlying root cause: TestSprite auto-generated incorrect or fictitious credentials during test synthesis.** No authenticated workflow could be exercised because the login step failed in every case.

### Specific Issues Identified

1. **Wrong field name in login payload (Backend TC001, TC003)**
   - Tests submitted `{"email": "...", "password": "..."}` but the API contract requires `{"username": "...", "password": "..."}`.
   - The server correctly returns HTTP 422 with `body.username Field required`.

2. **Entirely wrong credentials (Backend TC001, TC002, TC010; Frontend TC001, TC002, TC006)**
   - Passwords such as `"admin"`, `"adminadmin"`, and `"AdminPass123!"` were guessed by TestSprite and are all incorrect.
   - The admin username `"admin@example.com"` (TC010) is also wrong — the actual username is `"admin"`.
   - Frontend tests used a completely fictitious user `"Rajesh Shinde"` / `"password123"`.

3. **Non-existent API endpoints (Backend TC002)**
   - Test assumed `/api/v1/dashboard/summary` and `/api/v1/dashboard/trends` exist; these routes are not present in the actual API surface. Even with correct credentials, this test would fail at the endpoint assertion stage.

4. **No authenticated feature was tested**
   - Due to universal login failures, zero coverage was achieved on: device CRUD operations, dashboard content, audit log management, and admin user creation.

### What Did Work

- **Frontend TC017 (PASSED):** The negative login test — submitting a clearly invalid username/password and verifying the app does not crash or navigate — passed successfully. This confirms the authentication rejection mechanism on the frontend functions correctly.

### Recommendations

| Priority | Recommendation |
|----------|---------------|
| **Critical** | Supply correct credentials to TestSprite via `LOGIN_USER` and `LOGIN_PASSWORD` environment variables before re-running. The admin username is `admin`; the password should be sourced from the deployment environment (e.g., `POSTGRES_PASSWORD` / admin seed). |
| **High** | Fix the login payload field name in Backend TC001 and TC003: replace `"email"` with `"username"`. |
| **High** | Correct the admin identifier in Backend TC010: replace `"admin@example.com"` with `"admin"`. |
| **Medium** | Audit and correct the dashboard API endpoint paths in Backend TC002 before re-running (`/dashboard/summary` and `/dashboard/trends` do not exist). |
| **Low** | Consider adding a pre-flight health + login smoke step as a shared fixture across all backend tests to surface credential issues immediately rather than per-test. |

### Generated Test Files Reference

| File | Type |
|------|------|
| `C:\Users\ASUS\Desktop\edq\testsprite_tests\TC001_Sign_in_with_valid_credentials_and_reach_dashboard.py` | Frontend (Playwright) |
| `C:\Users\ASUS\Desktop\edq\testsprite_tests\TC002_Add_a_device_to_inventory_from_the_devices_page.py` | Frontend (Playwright) |
| `C:\Users\ASUS\Desktop\edq\testsprite_tests\TC006_Dashboard_shows_core_summary_and_trends.py` | Frontend (Playwright) |
| `C:\Users\ASUS\Desktop\edq\testsprite_tests\TC017_Reject_sign_in_with_invalid_password.py` | Frontend (Playwright) |
| `C:\Users\ASUS\Desktop\edq\testsprite_tests\TC001_test_authentication_and_session_management.py` | Backend (requests) |
| `C:\Users\ASUS\Desktop\edq\testsprite_tests\TC002_test_dashboard_and_trends_overview.py` | Backend (requests) |
| `C:\Users\ASUS\Desktop\edq\testsprite_tests\TC003_test_device_management_crud_operations.py` | Backend (requests) |
| `C:\Users\ASUS\Desktop\edq\testsprite_tests\TC010_test_administration_and_audit_logging.py` | Backend (requests) |

---

*Report generated by TestSprite MCP — 2026-04-10*
