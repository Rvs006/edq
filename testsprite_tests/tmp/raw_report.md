
# TestSprite AI Testing Report(MCP)

---

## 1️⃣ Document Metadata
- **Project Name:** edq
- **Date:** 2026-04-10
- **Prepared by:** TestSprite AI Team

---

## 2️⃣ Requirement Validation Summary

#### Test TC001 Sign in with valid credentials and land on dashboard
- **Test Code:** [TC001_Sign_in_with_valid_credentials_and_land_on_dashboard.py](./TC001_Sign_in_with_valid_credentials_and_land_on_dashboard.py)
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7ef6159e-1e13-4ff2-b4bc-f0ef3adf3ff3/e47d38b2-9fb3-4476-b2ae-8ef6217bdf30
- **Status:** ✅ Passed
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC002 Reject login with invalid password and show error toast
- **Test Code:** [TC002_Reject_login_with_invalid_password_and_show_error_toast.py](./TC002_Reject_login_with_invalid_password_and_show_error_toast.py)
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7ef6159e-1e13-4ff2-b4bc-f0ef3adf3ff3/8b205e92-2ca8-461d-8450-bed28d8d81c0
- **Status:** ✅ Passed
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC003 Add a static IP device and verify it appears in inventory
- **Test Code:** [TC003_Add_a_static_IP_device_and_verify_it_appears_in_inventory.py](./TC003_Add_a_static_IP_device_and_verify_it_appears_in_inventory.py)
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7ef6159e-1e13-4ff2-b4bc-f0ef3adf3ff3/ee56e3e1-6180-4674-bb49-83bf1433ac4b
- **Status:** ✅ Passed
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC004 Open device detail page and view device info sections
- **Test Code:** [TC004_Open_device_detail_page_and_view_device_info_sections.py](./TC004_Open_device_detail_page_and_view_device_info_sections.py)
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7ef6159e-1e13-4ff2-b4bc-f0ef3adf3ff3/8b496f5d-b29d-4f85-91f6-7b65b2fb5caa
- **Status:** ✅ Passed
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC005 Edit device fields inline on device detail page
- **Test Code:** [TC005_Edit_device_fields_inline_on_device_detail_page.py](./TC005_Edit_device_fields_inline_on_device_detail_page.py)
- **Test Error:** TEST BLOCKED

The test cannot proceed because the application is rate-limited and prevents sign-in and subsequent device edits.

Observations:
- A toast notification is visible saying: 'Too many requests. Please try again later.'
- The login form is present and filled, but submitting is blocked by the rate-limiting response.
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7ef6159e-1e13-4ff2-b4bc-f0ef3adf3ff3/75b971e8-e318-4506-b2a7-770dfb4045f0
- **Status:** BLOCKED
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC006 Search devices by hostname in the devices list
- **Test Code:** [TC006_Search_devices_by_hostname_in_the_devices_list.py](./TC006_Search_devices_by_hostname_in_the_devices_list.py)
- **Test Error:** TEST BLOCKED

The test cannot proceed because the supplied credentials were rejected by the application.

Observations:
- A persistent 'Invalid credentials' notification is shown in the UI after submitting the provided admin username and password.
- The page remains on the Sign In form (username and password fields visible), preventing access to the dashboard or the /devices page.
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7ef6159e-1e13-4ff2-b4bc-f0ef3adf3ff3/aa35c841-9254-4c8f-b6d8-1259275e224a
- **Status:** BLOCKED
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC007 Create a new project with full metadata
- **Test Code:** [TC007_Create_a_new_project_with_full_metadata.py](./TC007_Create_a_new_project_with_full_metadata.py)
- **Test Error:** TEST BLOCKED

Authentication failed and the test cannot proceed — the app remains on the Sign in page with an 'Invalid credentials' message.

Observations:
- The login page displays 'Invalid credentials'.
- The page remains on the Sign in screen with the Username and Password fields filled, and the dashboard is not accessible.

- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7ef6159e-1e13-4ff2-b4bc-f0ef3adf3ff3/3589e745-f331-4e64-97ed-2f40d5d28c15
- **Status:** BLOCKED
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC008 View devices filtered by project
- **Test Code:** [TC008_View_devices_filtered_by_project.py](./TC008_View_devices_filtered_by_project.py)
- **Test Error:** TEST BLOCKED

Could not log in with the provided admin credentials, so the Projects and Devices pages could not be reached.

Observations:
- The login page displays 'Invalid credentials'.
- The Sign In form is visible and submitting does not grant access.
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7ef6159e-1e13-4ff2-b4bc-f0ef3adf3ff3/182bd89a-0eef-4050-99a6-62918a84bcbf
- **Status:** BLOCKED
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC009 Create a test run and select device and template
- **Test Code:** [TC009_Create_a_test_run_and_select_device_and_template.py](./TC009_Create_a_test_run_and_select_device_and_template.py)
- **Test Error:** TEST BLOCKED

Unable to proceed because the admin login is not succeeding. The UI shows an 'Invalid credentials' message and the app remains on the login form after multiple sign-in attempts, so the authenticated workflow to reach Test Runs and create a test run cannot be executed.

Observations:
- The login page displays 'Invalid credentials'.
- The username and password fields are pre-filled with the provided admin credentials but signing in returns to the login screen.
- Because authentication fails, the Test Runs page and the Create Run workflow cannot be reached.
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7ef6159e-1e13-4ff2-b4bc-f0ef3adf3ff3/2f2e4a95-051d-44ee-a5c2-f249f9a58dc0
- **Status:** BLOCKED
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC010 View completed test run detail with test results
- **Test Code:** [TC010_View_completed_test_run_detail_with_test_results.py](./TC010_View_completed_test_run_detail_with_test_results.py)
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7ef6159e-1e13-4ff2-b4bc-f0ef3adf3ff3/e3cd8eaf-7c1c-47c6-950b-9588bf4617b2
- **Status:** ✅ Passed
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC011 Filter test runs by status (Active, Review, Done)
- **Test Code:** [TC011_Filter_test_runs_by_status_Active_Review_Done.py](./TC011_Filter_test_runs_by_status_Active_Review_Done.py)
- **Test Error:** TEST BLOCKED

Login could not be completed — the test cannot reach the Test Runs page because authentication is failing.

Observations:
- The login page shows the message 'Invalid credentials'.
- The username and password fields are pre-filled with the provided admin credentials.
- The application remains on the sign-in screen and does not redirect to the dashboard.
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7ef6159e-1e13-4ff2-b4bc-f0ef3adf3ff3/8cf408b2-b5e0-4016-860e-bc6672c184b0
- **Status:** BLOCKED
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC012 Browse test template library and create a new template
- **Test Code:** [TC012_Browse_test_template_library_and_create_a_new_template.py](./TC012_Browse_test_template_library_and_create_a_new_template.py)
- **Test Error:** TEST BLOCKED

The test cannot continue because the admin credentials are being rejected at sign-in.

Observations:
- The login page displays 'Invalid credentials' after submitting the admin password.
- The username and password fields are visible and prefilled, but signing in returns to the login screen.
- Three sign-in attempts were made and all failed.
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7ef6159e-1e13-4ff2-b4bc-f0ef3adf3ff3/fc906c42-55b3-4bc2-b97f-375193da3010
- **Status:** BLOCKED
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC013 Create a port whitelist with entries
- **Test Code:** [TC013_Create_a_port_whitelist_with_entries.py](./TC013_Create_a_port_whitelist_with_entries.py)
- **Test Error:** TEST BLOCKED

The feature cannot be reached because authentication is failing with the provided admin credentials.

Observations:
- The login page displays 'Invalid credentials' after submitting the admin username and password.
- A partially-filled 'New Whitelist' (Name='Lab Whitelist' with Port 443 entry) was not saved when the session expired earlier.
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7ef6159e-1e13-4ff2-b4bc-f0ef3adf3ff3/e25bdd31-f178-481e-9785-cb25879c5b68
- **Status:** BLOCKED
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC014 Duplicate an existing whitelist
- **Test Code:** [TC014_Duplicate_an_existing_whitelist.py](./TC014_Duplicate_an_existing_whitelist.py)
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7ef6159e-1e13-4ff2-b4bc-f0ef3adf3ff3/ec911b56-542a-4039-bfdc-fca7c97814ff
- **Status:** ✅ Passed
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC015 Admin creates a new user with engineer role
- **Test Code:** [TC015_Admin_creates_a_new_user_with_engineer_role.py](./TC015_Admin_creates_a_new_user_with_engineer_role.py)
- **Test Error:** TEST BLOCKED

The test cannot proceed because admin login is failing and access to the /admin user-creation UI is blocked.

Observations:
- The login attempt shows an 'Invalid credentials' notification on the page.
- The login form is still visible with the username and password fields (username='admin').
- No access to /admin or the Create User modal is available, so the user creation step cannot be performed.
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7ef6159e-1e13-4ff2-b4bc-f0ef3adf3ff3/33569edd-04a6-4ea4-bf0e-50dfdaedb68f
- **Status:** BLOCKED
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC016 Admin changes a user role via inline select
- **Test Code:** [TC016_Admin_changes_a_user_role_via_inline_select.py](./TC016_Admin_changes_a_user_role_via_inline_select.py)
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7ef6159e-1e13-4ff2-b4bc-f0ef3adf3ff3/37a81ec4-39d2-46e6-ac1d-6d35e0f0527d
- **Status:** ✅ Passed
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC017 Admin views system status tab
- **Test Code:** [TC017_Admin_views_system_status_tab.py](./TC017_Admin_views_system_status_tab.py)
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7ef6159e-1e13-4ff2-b4bc-f0ef3adf3ff3/12ee2874-2aa3-46a7-974a-13a4aa2b48ab
- **Status:** ✅ Passed
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC018 View audit log and filter by action type
- **Test Code:** [TC018_View_audit_log_and_filter_by_action_type.py](./TC018_View_audit_log_and_filter_by_action_type.py)
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7ef6159e-1e13-4ff2-b4bc-f0ef3adf3ff3/75383aee-448a-4658-8133-77c07d38355a
- **Status:** ✅ Passed
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC019 Export audit log as CSV
- **Test Code:** [TC019_Export_audit_log_as_CSV.py](./TC019_Export_audit_log_as_CSV.py)
- **Test Error:** TEST FAILURE

Exporting the audit log to CSV failed and no download started.

Observations:
- Clicking the 'Export CSV' button produced a toast notification: 'Failed to export CSV'.
- No file download was triggered after clicking Export CSV.

- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7ef6159e-1e13-4ff2-b4bc-f0ef3adf3ff3/f4c692b9-dc34-47c9-8303-fd370ac291d5
- **Status:** ❌ Failed
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC020 Generate an Excel report from a completed test run
- **Test Code:** [TC020_Generate_an_Excel_report_from_a_completed_test_run.py](./TC020_Generate_an_Excel_report_from_a_completed_test_run.py)
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7ef6159e-1e13-4ff2-b4bc-f0ef3adf3ff3/f0c30fae-80c5-4cca-923e-ec2772b0986f
- **Status:** ✅ Passed
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC021 Settings - Edit profile name and email
- **Test Code:** [TC021_Settings___Edit_profile_name_and_email.py](./TC021_Settings___Edit_profile_name_and_email.py)
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7ef6159e-1e13-4ff2-b4bc-f0ef3adf3ff3/547d74dc-7dc0-44a0-aa6b-9162b79caaa4
- **Status:** ✅ Passed
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC022 Settings - Change password with complexity validation
- **Test Code:** [TC022_Settings___Change_password_with_complexity_validation.py](./TC022_Settings___Change_password_with_complexity_validation.py)
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7ef6159e-1e13-4ff2-b4bc-f0ef3adf3ff3/2ed50094-a511-43e2-9d6b-ba1f163ad927
- **Status:** ✅ Passed
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC023 Settings - Toggle dark/light theme
- **Test Code:** [TC023_Settings___Toggle_darklight_theme.py](./TC023_Settings___Toggle_darklight_theme.py)
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7ef6159e-1e13-4ff2-b4bc-f0ef3adf3ff3/7cc15b1d-06ee-4387-aaf4-86d1f6d33700
- **Status:** ✅ Passed
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC024 Settings - Update report branding company name
- **Test Code:** [TC024_Settings___Update_report_branding_company_name.py](./TC024_Settings___Update_report_branding_company_name.py)
- **Test Error:** TEST BLOCKED

The test cannot continue because the application is preventing access due to authentication failure.

Observations:
- A toast reading 'Invalid credentials' is visible on the login page.
- The page remains on the Sign in form and cannot reach the dashboard or Settings to verify the branding change.
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7ef6159e-1e13-4ff2-b4bc-f0ef3adf3ff3/92f0b2f5-7000-4c66-8d88-c86fd475e4b9
- **Status:** BLOCKED
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC025 Create a device profile with fingerprint rules
- **Test Code:** [TC025_Create_a_device_profile_with_fingerprint_rules.py](./TC025_Create_a_device_profile_with_fingerprint_rules.py)
- **Test Error:** TEST BLOCKED

The test cannot proceed because the application is rate-limiting requests. I could not authenticate, so I cannot reach the Device Profiles page to create the profile.

Observations:
- A toast message on the page states: 'Too many requests. Please try again later.'
- The Sign in form remains visible with credentials filled and multiple submit attempts did not redirect to the dashboard.

- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7ef6159e-1e13-4ff2-b4bc-f0ef3adf3ff3/b9426922-5f1e-4334-a853-7267743de0ba
- **Status:** BLOCKED
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC026 View the landing page as unauthenticated user
- **Test Code:** [TC026_View_the_landing_page_as_unauthenticated_user.py](./TC026_View_the_landing_page_as_unauthenticated_user.py)
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7ef6159e-1e13-4ff2-b4bc-f0ef3adf3ff3/fe1c856e-0f00-430d-8d24-e308b0e60630
- **Status:** ✅ Passed
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC027 Navigate through all main sidebar links
- **Test Code:** [TC027_Navigate_through_all_main_sidebar_links.py](./TC027_Navigate_through_all_main_sidebar_links.py)
- **Test Error:** TEST BLOCKED

The test cannot proceed because signing in as the admin user is failing and I cannot reach the dashboard to continue sidebar navigation.

Observations:
- Submitting the provided admin credentials shows an "Invalid credentials" message.
- The login page remains visible and the app did not redirect to the dashboard, so sidebar pages cannot be verified.

- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7ef6159e-1e13-4ff2-b4bc-f0ef3adf3ff3/aac17c81-fba5-4151-a33b-4e3a1fdc9902
- **Status:** BLOCKED
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC028 Add an authorized network CIDR range
- **Test Code:** [TC028_Add_an_authorized_network_CIDR_range.py](./TC028_Add_an_authorized_network_CIDR_range.py)
- **Test Error:** TEST BLOCKED

The feature could not be reached because authentication failed — the provided admin credentials are not being accepted, so I cannot access /authorized-networks to add the authorized network.

Observations:
- The page shows an 'Invalid credentials' notification.
- The sign-in form remains visible with the username 'admin' and the password populated after multiple attempts.
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7ef6159e-1e13-4ff2-b4bc-f0ef3adf3ff3/1a9b91e2-94c9-4eca-b51c-6b089acc1c94
- **Status:** BLOCKED
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC029 Dashboard shows KPI cards with correct data types
- **Test Code:** [TC029_Dashboard_shows_KPI_cards_with_correct_data_types.py](./TC029_Dashboard_shows_KPI_cards_with_correct_data_types.py)
- **Test Error:** TEST FAILURE

The Pass Rate KPI did not display a percentage as required.

Observations:
- The Pass Rate card shows a placeholder dash (—) instead of a percentage.
- The Total Devices card shows 534, Active Test Runs shows 0, and Completed This Week shows 0.
- The Recent Test Sessions table and its columns (Device, IP, Status, Verdict, Date) are visible.
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7ef6159e-1e13-4ff2-b4bc-f0ef3adf3ff3/1b410a3d-7b86-4114-9805-174fbd57f42a
- **Status:** ❌ Failed
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC030 View review queue page as admin
- **Test Code:** [TC030_View_review_queue_page_as_admin.py](./TC030_View_review_queue_page_as_admin.py)
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/7ef6159e-1e13-4ff2-b4bc-f0ef3adf3ff3/9879b613-3f44-48b7-a5e7-ec5ec85cf5ad
- **Status:** ✅ Passed
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---


## 3️⃣ Coverage & Matching Metrics

- **50.00** of tests passed

| Requirement        | Total Tests | ✅ Passed | ❌ Failed  |
|--------------------|-------------|-----------|------------|
| ...                | ...         | ...       | ...        |
---


## 4️⃣ Key Gaps / Risks
{AI_GNERATED_KET_GAPS_AND_RISKS}
---