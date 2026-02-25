# ELECTRACOM DEVICE QUALIFIER — Product Requirements Document

**V1.0 — Launch Edition**

| Field | Value |
|---|---|
| **Document Version** | 1.0.0 |
| **Status** | Draft for Engineering Review |
| **Classification** | Internal — Confidential |
| **Product Owner** | Platform Engineering |
| **Last Updated** | 2026-02-23 |
| **Target Release** | V1.0 — 12 Weeks from Approval |

*Electracom Projects Ltd — A Sauter Group Company*
**CONFIDENTIAL — Internal Use Only**

---

## Version History

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0.0 | 2026-02-23 | Platform Engineering | Initial V1.0 Launch PRD — consolidated from V6.0 Enterprise PRD, architectural review, and modular device-agnostic redesign |

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Target Users](#2-target-users)
3. [System Architecture](#3-system-architecture)
4. [Auto-Discovery & Device Fingerprinting](#4-auto-discovery--device-fingerprinting)
5. [Three-Tier Test Engine](#5-three-tier-test-engine)
6. [Universal Test Library & Device Profiles](#6-universal-test-library--device-profiles)
7. [AI-Assisted Draft Synopsis Generator](#7-ai-assisted-draft-synopsis-generator)
8. [Reporting & Compliance Engine](#8-reporting--compliance-engine)
9. [Security Architecture & Threat Model](#9-security-architecture--threat-model)
10. [Offline Architecture](#10-offline-architecture)
11. [Database Schema](#11-database-schema)
12. [Deployment & Infrastructure](#12-deployment--infrastructure)
13. [Phased Delivery Plan](#13-phased-delivery-plan)
14. [Risk Register](#14-risk-register)
15. [Deferred Features (V2.0+ Roadmap)](#15-deferred-features-v20-roadmap)

---

## 1. Executive Summary

The Electracom Device Qualifier (EDQ) is an automated network security testing platform purpose-built to qualify smart building devices for enterprise network deployment. It supports any IP-connected device — cameras, HVAC controllers, intercoms, access panels, lighting controllers, sensors, meters, and any future device type — through a modular, device-agnostic testing architecture.

The platform addresses a critical operational bottleneck: each device qualification currently requires a full working day of manual testing by a security engineer, involving repetitive command-line tool execution, manual result transcription into Excel spreadsheets, and hand-written narrative reports. With 30+ devices requiring qualification per month across a team of 10 engineers working from multiple office locations, this manual process is unsustainable, error-prone, and unauditable.

EDQ V1.0 reduces device qualification time from one full working day to approximately 1–2 hours through three mechanisms: a zero-input auto-discovery pipeline that fingerprints devices automatically, a three-tier test engine that maximises automation while preserving human judgment only where genuinely required, and template-based report generation that produces pixel-perfect client deliverables in Excel, Word, and PDF formats mapping to ISO 27001, SOC2, and Cyber Essentials compliance frameworks.

**Key Design Principle: Zero Unnecessary Input.** The engineer plugs in a device with a Cat6 cable and clicks one button. The system discovers the device, identifies the manufacturer and category, determines which tests apply, auto-stamps inapplicable tests as N/A, runs all automated assessments, and presents only the genuinely manual tests as structured single-click decisions — not free-form text. The AI-assisted draft synopsis generator then writes the narrative security assessment from the structured results, which the engineer reviews and approves.

**Key Architectural Decision:** EDQ operates as a central web application with a lightweight desktop agent on each engineer's laptop. The agent executes scanning tools locally over a direct Cat6 ethernet connection to the device, providing full Layer 2 network access. The agent operates fully offline when internet is unavailable, syncing results when connectivity is restored.

---

## 2. Target Users

### 2.1 Security Test Engineer (10 users)

Conducts daily device qualification testing from multiple locations (main office, coworking spaces, client sites). Connects devices directly to their laptop via Cat6 ethernet. Currently spends an entire working day per device running CLI tools manually and transcribing results. V1.0 benefit: plugs in a device, clicks one button, automated tests run while they handle other work, completes structured manual checks in minutes, downloads a finished report. Total time: 1–2 hours. Full offline capability.

### 2.2 Reviewing Manager / QA Lead (2–3 users)

Reviews test evidence, validates engineering judgments, overrides automated verdicts with documented justification, approves final reports before client delivery. Accesses the web dashboard from any browser — no agent required. Sees real-time status of all tests across the entire team. No more aggregating results from individual laptops.

### 2.3 Platform Developer / Admin (1 user)

Maintains the platform, manages users, creates test templates for new device types via the admin UI (no code changes required), monitors agent connectivity and sync status, deploys updates.

---

## 3. System Architecture

### 3.1 Overview

EDQ V1.0 has two physical components: a central server accessible over the internet, and lightweight desktop agents on engineer laptops. The control plane (coordination, storage, UI, reporting) is separated from the execution plane (network scanning), enabling portable testing from any location with centralised data management.

### 3.2 Architecture Diagram

```
┌─────────────────────────────────────────────┐
│  CENTRAL SERVER (Azure VM / On-Prem)        │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌──────┐ │
│  │ Nginx  │ │FastAPI │ │SQLite  │ │Redis │ │
│  │ +React │ │Backend │ │  /PG   │ │Queue │ │
│  └────────┘ └────────┘ └────────┘ └──────┘ │
└─────────────────────────────────────────────┘
              HTTPS │         │
    ┌──────────────┼─────────┼─────────┐
 ┌──┴─────┐  ┌────┴────┐  ┌─┴────────┐
 │ Agent  │  │ Agent   │  │ Reviewer │
 │ Eng #1 │  │ Eng #2  │  │ (Browser)│
 └──┬─────┘  └──┬──────┘  └──────────┘
    │ Cat6      │ Cat6
 ┌──┴─────┐  ┌──┴──────┐
 │ Camera │  │ Contrlr │  (Any IP Device)
 └────────┘  └─────────┘
```

### 3.3 Central Server

Hosted on an Azure B2s VM (or equivalent). Runs four containerised services via Docker Compose:

- **Nginx reverse proxy:** Serves React frontend, terminates TLS, enforces rate limiting, proxies API requests to backend.
- **FastAPI backend (Python 3.12):** Auth, REST API, WebSocket, database, report generation, agent coordination.
- **SQLite database:** V1.0. Migration path to PostgreSQL for V2.0 when concurrent write contention emerges.
- **Redis 7:** Job queuing and WebSocket pub/sub for real-time terminal streaming.

### 3.4 Laptop Scanning Agent

A lightweight desktop application installed on each engineer's Windows or Mac laptop. Bundles all scanning tool binaries (nmap, testssl.sh, ssh-audit, nikto) within its installation package — no dependencies on the engineer having any tools pre-installed.

#### 3.4.1 Online Mode

Agent connects to central server via HTTPS. Engineer initiates tests from the web UI. Server pushes job to Redis queue. Agent polls queue, executes tools on the local ethernet interface connected to the device via Cat6, streams results back to the server. Web UI shows real-time progress via WebSocket.

#### 3.4.2 Offline Mode

When the agent cannot reach the central server, it switches to fully autonomous operation. The agent serves a lightweight local UI at `https://localhost:8433` for test execution and manual assessments. All data is stored in an AES-256 encrypted local SQLite database. When connectivity is restored, results automatically sync to the central server with conflict detection and resolution.

#### 3.4.3 System Tray Behaviour

- **Grey:** Idle, no server connection.
- **Green:** Connected to server, ready.
- **Blue (pulsing):** Actively scanning a device.
- **Orange:** Unsynced offline results pending upload.
- **Red:** Error (connection failed, scan error, sync conflict).

### 3.5 Network Architecture

The fundamental constraint: many security tests (MAC discovery, ARP scanning, switch negotiation, IPv6 SLAAC) require Layer 2 access — the scanner must be on the same physical network segment as the device. When an engineer connects a device directly via Cat6, the laptop's ethernet interface and the device form a two-node network. The agent scans on this interface while communicating with the server over WiFi or a separate connection.

**Security constraint:** The agent must never route traffic between the test network interface and the corporate/internet interface. OS-level routing isolation is enforced during active scans.

---

## 4. Auto-Discovery & Device Fingerprinting

Auto-discovery is the mandatory first step of every test session. The engineer provides nothing except the device's IP address (or clicks "Scan Network" for automatic detection). The system determines everything else.

### 4.1 Discovery Sequence

The following sequence executes automatically in under 60 seconds:

1. **ARP Resolution:** Obtain the device's MAC address via ARP request. Map MAC to manufacturer using the IEEE OUI database (e.g., `00:04:7D` → Motorola Solutions / Pelco).
2. **Port Scan:** Full TCP SYN scan of all 65,535 ports (`nmap -sS`). UDP scan of top 100 common ports. Identify all open ports and running services with version detection.
3. **Service Fingerprinting:** Banner grabbing on all open services. HTTP server identification (headers, response patterns). TLS certificate extraction (subject, issuer, validity, SANs).
4. **Device Category Inference:** Rules-based classification from discovered services:
   - RTSP (554) or ONVIF (80/8080 with ONVIF endpoint) → **IP Camera**
   - BACnet (47808) or Modbus (502) → **Building Controller**
   - SIP (5060/5061) → **Intercom / VoIP Device**
   - MQTT (1883/8883) or CoAP (5683) → **IoT Sensor**
   - HTTP/HTTPS only → **Generic Network Device**
5. **Template Matching:** Cross-reference manufacturer + category against the template database. If an exact match exists (e.g., Pelco + Camera → "Pelco Camera Qualification Rev 2"), auto-select it. If no match, use the closest category template or the Universal Security Assessment template.

### 4.2 Discovery Output

The auto-discovery produces a **Device Fingerprint Card** displayed to the engineer:

| Field | Example Value |
|---|---|
| IP Address | 192.168.1.50 |
| MAC Address | 00:04:7D:D7:D1:58 |
| Manufacturer | Motorola Solutions Inc. (Pelco) |
| Device Category | IP Camera (auto-detected: RTSP on port 554) |
| Open Ports | 22 (SSH), 80 (HTTP), 443 (HTTPS), 554 (RTSP) |
| TLS Version | TLS 1.2 / TLS 1.3 supported |
| SSH Version | OpenSSH 8.2 |
| Web Server | lighttpd/1.4.55 |
| Matched Template | Pelco Camera Qualification Rev 2 |

The engineer reviews this card and either confirms ("Start Testing") or corrects the category/template selection. In the majority of cases, the auto-detection is correct and the engineer simply clicks one button.

**If no template matches:** The system uses the Universal Security Assessment template, which runs all device-agnostic tests. The admin can create a device-specific template later and retroactively map the existing results to it — no re-testing required.

---

## 5. Three-Tier Test Engine

Every test in every template falls into exactly one of three tiers. The tier determines how the test executes and what (if any) engineer input is required.

### 5.1 Tier 1: Fully Automatic (60–65% of tests)

The engineer does nothing. The system executes the test, evaluates the result against deterministic rules, assigns a verdict (Pass/Fail/Advisory), and generates the report comment text — all without any human input.

**Execution:** The agent runs the mapped scanning tool (nmap, testssl.sh, ssh-audit, nikto) via subprocess. Raw stdout is captured and persisted. A structured parser extracts specific findings. A rule engine evaluates findings against pass/fail criteria defined in the template.

**Example — Test T5 (MAC Address):** nmap ARP scan → discovers MAC `00:04:7D:D7:D1:58` → OUI lookup returns "Motorola Solutions Inc." → vendor is registered → **PASS**. Auto-generated comment: "MAC: 00:04:7D:D7:D1:58. Vendor: Motorola Solutions Inc. Company Address: 500 W Monroe Street, Chicago IL US 60661. Last Update: 2021-01-28."

**Example — Test T16 (TLS Assessment):** testssl.sh runs against port 443 → finds TLS 1.2 with CBC cipher suites → rule: if TLS < 1.3 AND weak ciphers present → **ADVISORY**. Auto-generated comment lists all weak cipher suites found.

### 5.2 Tier 2: Guided Manual (25–30% of tests)

The system cannot make the final determination, but it does as much work as possible and asks the engineer for the minimum input — a single-click structured decision, not free-form text.

**Design principle:** Every manual test presents the engineer with predefined outcome options. The system auto-generates the report comment text based on which option the engineer selects. The engineer never writes a sentence unless they choose to add optional supplementary notes.

Examples of structured manual test interactions:

| Test | What System Shows | Engineer Action |
|---|---|---|
| Network Disconnection | "Disconnect the Cat6 cable for 30 seconds, then reconnect. What happened?" | Selects: [Resumed normally] [Did not resume] [Device lost power (PoE)] [Other] |
| Web Password Change | "Log into the web interface. Can the admin password be changed?" | Selects: [Yes — password changed] [Yes — but requires reboot] [No — no option found] [Cannot access web UI] |
| Firmware Update | "Does the web interface provide a firmware update mechanism?" | Selects: [Yes — manual upload] [Yes — auto-update] [No mechanism found] [N/A] |
| Physical Tamper | "Is the device's reset button / USB port physically accessible without tools?" | Selects: [Accessible] [Requires tools] [No reset mechanism] [N/A] |
| Documentation | "Does the manufacturer provide a security hardening guide?" | Selects: [Yes — comprehensive] [Yes — basic] [No documentation found] [Link: ___] |

Each selection maps to a predefined verdict and auto-generated comment. For example, if the engineer selects "Device lost power (PoE)" for the Network Disconnection test, the system auto-assigns **N/A** with the comment: "Device is Power over Ethernet (PoE). Without the ethernet connection, the device loses power and cannot operate. Test not applicable."

**Evidence capture:** For manual tests, the system prompts for optional screenshot or photo upload. The agent can trigger an automatic screenshot of the device's web interface (if accessible) to pre-attach as evidence.

### 5.3 Tier 3: Auto N/A (5–15% of tests)

Tests that are provably inapplicable based on the auto-discovery results. The system stamps them as N/A automatically with a generated explanation. Zero engineer involvement.

**Rules engine:** Each test in each template has prerequisite conditions defined:

- SSH tests require SSH service detected on at least one port. If no SSH → all SSH tests = N/A ("SSH service not detected on any port").
- RTSP tests require RTSP service detected. If no RTSP → RTSP tests = N/A.
- IPv6 tests require "Essential Pass = NO" AND no IPv6 stack detected. If the template marks IPv6 as non-essential and the device has no IPv6 → N/A.
- BACnet/Modbus tests on a camera → N/A ("Building automation protocols not applicable to this device category").
- Nessus-specific tests without a .nessus file uploaded → N/A ("Nessus scan not performed for this assessment").

**Percentage varies by device:** A camera might have 5% auto-N/A tests (most network tests apply). A simple temperature sensor might have 30% auto-N/A tests (no web interface, no SSH, no TLS). This is correct behaviour — the system intelligently scopes the assessment to what's actually present on the device.

### 5.4 Wobbly Cable Resilience Handler

Between each major test module, the agent performs a connectivity check (ICMP ping + TCP SYN to a known open port). If the device is unreachable: the UI shows a warning, the current test pauses (not fails), the agent enters exponential backoff polling (2s → 4s → 8s → up to 60s, max 15 minutes). Upon reconnection, testing resumes from exactly where it stopped. If unreachable after 15 minutes, the run pauses indefinitely with an engineer notification.

### 5.5 Nessus Integration

Engineers run Nessus vulnerability scans separately (Nessus has its own licensing and scanning infrastructure). They export the results as a `.nessus` XML file and upload it to EDQ. The system parses the XML using `defusedxml` (preventing XXE attacks), maps each finding to the template's Nessus results sheet by plugin ID and severity, and auto-populates the corresponding test rows. The engineer reviews the mapped results and confirms.

---

## 6. Universal Test Library & Device Profiles

### 6.1 Universal Tests (Apply to Every Device)

These tests execute regardless of device type. They form the base layer of every qualification:

| # | Test | Tool | Tier | Compliance Map |
|---|---|---|---|---|
| U01 | Ping response | nmap | Automatic | Baseline |
| U02 | MAC address vendor lookup | nmap + OUI DB | Automatic | ISO 27001 A.12.6 |
| U03 | Switch negotiation (speed/duplex) | nmap + ethtool | Automatic | Baseline |
| U04 | DHCP behaviour | nmap + dhclient | Automatic | Baseline |
| U05 | IPv6 support detection | nmap | Automatic | Baseline |
| U06 | Full TCP port scan | nmap | Automatic | CE Boundary |
| U07 | UDP top-100 port scan | nmap | Automatic | CE Boundary |
| U08 | Service version detection | nmap | Automatic | SOC2 CC7.1 |
| U09 | Protocol whitelist compliance | nmap + rules | Automatic | CE Secure Config |
| U10 | TLS version assessment | testssl.sh | Automatic | ISO 27001 A.14.1 |
| U11 | Cipher suite strength | testssl.sh | Automatic | ISO 27001 A.14.1 |
| U12 | Certificate validity | testssl.sh | Automatic | ISO 27001 A.14.1 |
| U13 | HSTS header presence | testssl.sh | Automatic | CE Secure Config |
| U14 | HTTP security headers | nikto | Automatic | CE Secure Config |
| U15 | SSH algorithm assessment | ssh-audit | Automatic | ISO 27001 A.14.1 |
| U16 | Default credential check | custom + hydra | Automatic | SOC2 CC6.1 |
| U17 | Brute force protection | custom | Automatic | SOC2 CC6.1 |
| U18 | HTTP vs HTTPS availability | nmap + curl | Automatic | CE Secure Config |
| U19 | OS fingerprinting | nmap | Automatic | SOC2 CC8.1 |
| U20 | Network disconnection behaviour | — | Guided Manual | Baseline |
| U21 | Web interface password change | — | Guided Manual | SOC2 CC6.1 |
| U22 | Firmware update mechanism | — | Guided Manual | CE Patch Mgmt |
| U23 | Session timeout validation | — | Guided Manual | ISO 27001 A.14.1 |
| U24 | Physical security (reset/USB) | — | Guided Manual | CE Secure Config |
| U25 | Manufacturer documentation | — | Guided Manual | Baseline |

### 6.2 Device Category Profiles (Extensions)

Each profile adds tests specific to that device category. Profiles are auto-selected based on discovery results and can be overridden by the engineer.

#### 6.2.1 IP Camera Profile

- RTSP port detection and encryption assessment
- ONVIF service discovery and authentication check
- Video stream encryption validation (SRTP vs RTP)
- Multicast traffic analysis
- RTSP credential exposure check

#### 6.2.2 Building Controller Profile (BACnet/HVAC)

- BACnet service detection (port 47808)
- BACnet authentication and encryption check
- Modbus TCP exposure detection (port 502)
- Control protocol segmentation assessment

#### 6.2.3 Intercom / Access Control Profile

- SIP protocol detection and encryption (SRTP, TLS-SIP)
- Door relay / control API exposure
- Audio stream encryption check

#### 6.2.4 IoT Sensor Profile

- MQTT broker detection and authentication
- CoAP endpoint discovery
- Telemetry data encryption assessment

#### 6.2.5 Generic / Unknown Device

Universal tests only. No category-specific extensions. Used when the device type is unknown or doesn't match any existing profile. This is the safe default — it never skips tests that might be relevant.

### 6.3 Template Import System

When a new device type or client format needs supporting, the admin uploads the client's Excel template and uses the admin UI to:

- Map each row in the template to a test from the Universal Library or a Device Profile.
- Define the cell positions for each result and comment column.
- Configure pass/fail rules for any device-specific tests.
- Set prerequisite conditions for auto-N/A stamping.

This configuration is stored as JSON in the database. No code changes or redeployment needed.

---

## 7. AI-Assisted Draft Synopsis Generator

### 7.1 Purpose and Scope

After all tests are complete and verdicts are final, the system can draft a professional security assessment narrative — the "Test Synopsis" section of the report. This is the one area where an LLM adds genuine value: synthesising structured test results into coherent, client-facing prose with specific remediation recommendations.

**This is a writing assistant, not a decision maker.** The AI never determines pass/fail verdicts. It receives the finalised structured results and writes a human-readable summary. The engineer reviews, edits, and approves the draft before it enters any report.

### 7.2 How It Works

1. Engineer clicks "Draft Synopsis" after all tests are complete.
2. The system compiles all test results, verdicts, and auto-generated comments into a structured prompt.
3. The prompt is sent to the LLM API (Claude API) with strict instructions: write a professional security assessment referencing specific test findings, list remediation steps in priority order, use Electracom's standard technical language, do not invent findings not present in the data.
4. The draft appears in an editable rich text field. The engineer reviews it, makes any corrections, and clicks "Approve."
5. The approved text is saved as the test synopsis and included in reports.

### 7.3 Guardrails

- **No hallucinated findings:** The prompt explicitly constrains the LLM to reference only test results present in the input data. The system validates that every test number cited in the synopsis exists in the actual results.
- **Human always in the loop:** The synopsis is never auto-inserted into a report. It requires explicit engineer approval.
- **Audit trail:** The database stores both the AI draft and the final approved version, with a flag indicating AI assistance was used.
- **Offline:** Synopsis generation is unavailable offline (requires API access). Engineers can write the synopsis manually or generate it after syncing.
- **Optional:** This feature can be deferred to V1.1 without blocking V1.0 launch. Engineers can write synopses manually as they do today.

---

## 8. Reporting & Compliance Engine

### 8.1 Template-Based Excel Generation

Client deliverables must be pixel-perfect replicas of existing manually-created reports. The system opens the actual client `.xlsx` template file and writes results into specific cells. It does NOT generate Excel files from scratch. This preserves all formatting, merged cells, conditional formatting, formulas, column widths, print areas, and page breaks exactly as designed.

Each template has a cell mapping stored as JSON: which cell receives which data point. This mapping is configured via the admin UI when importing a template.

### 8.2 Word Report Generation

Executive summary `.docx` reports generated via `python-docx` and Jinja2 against an actual `.docx` template file. Includes: cover page with client logo, colour-coded risk matrix, individual findings with severity and remediation, compliance control mapping, and the AI-drafted (or manually written) synopsis.

### 8.3 PDF Export

All reports exportable as PDF via LibreOffice headless conversion. Generated on-demand, not stored permanently.

### 8.4 Client Branding

Each client project can have: custom logo (PNG/JPG, max 2MB, SVG forbidden), branding colours for report headers, applicable compliance standards (ISO 27001, SOC2, Cyber Essentials, or custom), and custom header/footer text.

### 8.5 Compliance Mapping

| Standard | Control | Requirement | EDQ Implementation |
|---|---|---|---|
| ISO 27001 | A.12.6.1 | Technical Vulnerability Mgmt | Automated scanning, Nessus import, structured remediation tracking |
| ISO 27001 | A.14.1.2 | Securing App Services | TLS assessment, cipher validation, certificate chain verification |
| ISO 27001 | A.14.1.3 | Protecting Transactions | Session testing, brute force validation, auth mechanism assessment |
| SOC2 | CC6.1 | Logical Access Security | Default credential testing, password policy, access control verification |
| SOC2 | CC7.1 | System Monitoring | Port scan analysis, service enumeration, protocol whitelist compliance |
| SOC2 | CC8.1 | Change Management | Firmware tracking, config baseline, template versioning |
| Cyber Essentials | Boundary | Network perimeter | Open port analysis, unnecessary service detection, exposure assessment |
| Cyber Essentials | Secure Config | Device hardening | Default settings, unnecessary protocols, HTTP/HTTPS configuration |
| Cyber Essentials | Patching | Software currency | Firmware version recording, CVE cross-referencing via Nessus |
| Cyber Essentials | Access Control | Authentication | Brute force testing, session timeout, credential strength |

---

## 9. Security Architecture & Threat Model

### 9.1 Threat Landscape

EDQ processes highly sensitive data: network vulnerability assessments, device weaknesses, firmware versions, network topology, and authentication details. A breach provides an attacker with a precise roadmap for exploiting every qualified device across all client deployments. EDQ's security posture must exceed that of a typical internal tool.

### 9.2 Threat Vectors & Mitigations

#### 9.2.1 Agent–Server Interception

Scan results transit the internet between agent and server. Mitigation: mandatory TLS 1.3, no TLS 1.2 fallback, certificate pinning on agent.

#### 9.2.2 Stolen Laptop with Offline Data

Offline agent stores vulnerability data locally. Mitigation: AES-256-GCM encryption at rest, key derived via PBKDF2 (100K iterations), auto-purge after sync, maximum 7-day offline retention.

#### 9.2.3 Malicious Nessus File

Crafted `.nessus` XML could exploit XXE vulnerabilities. Mitigation: `defusedxml` parsing, external entity resolution disabled, 50MB file limit, sandboxed parsing context.

#### 9.2.4 Terminal Output Injection

Compromised device returns malicious HTML/JS in service banners. Mitigation: server-side sanitisation before WebSocket broadcast, `textContent` insertion in React (never `innerHTML`).

#### 9.2.5 Cross-Site Request Forgery

Malicious webpage triggers state-changing API calls. Mitigation: double-submit CSRF cookie pattern, `X-CSRF-Token` header on all POST/PUT/DELETE, `SameSite=Strict` cookies.

#### 9.2.6 Network Cross-Contamination

Agent bridges test network and corporate network. Mitigation: OS-level routing isolation, no IP forwarding, interface binding verification on scan startup.

### 9.3 Security Controls Matrix

| ID | Control | Implementation | Priority |
|---|---|---|---|
| **SEC-01** | Transport Encryption | All agent–server over TLS 1.3. Certificate pinning on agent. | **Critical** |
| **SEC-02** | Authentication | bcrypt (cost 12). httpOnly, Secure, SameSite=Strict cookies. | **Critical** |
| **SEC-03** | CSRF Protection | Double-submit cookie. X-CSRF-Token on mutating requests. | **Critical** |
| **SEC-04** | Input Validation | Server-side on all inputs. Parameterised queries only. | **Critical** |
| **SEC-05** | File Upload Security | Magic byte validation. SVG forbidden. MIME whitelist. Nginx size limits. | **High** |
| **SEC-06** | Terminal Sanitisation | Strip HTML/script/ANSI from tool output before WebSocket broadcast. | **High** |
| **SEC-07** | Offline Encryption | AES-256-GCM for local database. PBKDF2 key derivation. | **High** |
| **SEC-08** | Session Management | 15-min idle timeout. Max 3 concurrent sessions. Invalidation on password change. | **Medium** |
| **SEC-09** | Rate Limiting | Nginx: 100 req/min API, 10 req/min auth. Client exponential backoff. | **Medium** |
| **SEC-10** | Audit Logging | All security events logged: logins, test runs, overrides, report generation. | **High** |
| **SEC-11** | Content Security Policy | Strict CSP via Nginx. No inline scripts. | **Medium** |
| **SEC-12** | Agent Integrity | Code-signed installer. Checksum verification of bundled tool binaries. | **High** |
| **SEC-13** | Data Classification | Scan results = CONFIDENTIAL. No vuln data in URLs or localStorage. | **High** |
| **SEC-14** | Network Isolation | Test interface isolated from corporate interface. No routing between them. | **Critical** |
| **SEC-15** | Nessus File Handling | defusedxml. XXE disabled. Size limits. Sandboxed parsing. | **High** |

---

## 10. Offline Architecture

### 10.1 Design Principle

Offline is not degraded. An engineer at a construction site with no internet has the same testing capability as one in the office. The only difference is that results sync later.

### 10.2 Local Data Store

Encrypted SQLite database with: template snapshots (synced on last server contact), pending/completed test runs, raw tool output and evidence files, user credential hash for local auth. AES-256-GCM encryption, PBKDF2 key derivation, random salt.

### 10.3 Offline UI

Lightweight local web UI at `https://localhost:8433`. Provides: device registration, full test execution with real-time terminal output, structured manual test forms, result viewing. Does NOT provide: report generation (requires server), team dashboard, user management.

### 10.4 Sync Protocol

On connectivity restoration: authenticate, upload unsynced runs chronologically, upload evidence files, server validates and stores, mark as synced. Conflicts (same device tested by another engineer while offline) flagged for manual review. Sync is resumable — continues from last checkpoint if connectivity drops mid-sync.

### 10.5 Offline Limitations

Clearly communicated to engineers: report generation (Excel/Word/PDF) requires the server, new templates unavailable until reconnection, reviewer overrides only via central UI, AI synopsis generation requires API access.

---

## 11. Database Schema

### 11.1 Server Schema

| Table | Columns |
|---|---|
| **users** | id (UUID PK), email (unique), full_name, password_hash (bcrypt), role (enum: admin/tester/reviewer), is_active, last_login, created_at |
| **devices** | id (UUID PK), name, ip_address, mac_address, vendor, model, firmware_version, serial_number, device_category, fingerprint (JSON), created_by (FK), created_at, deleted_at |
| **test_templates** | id (UUID PK), name, version, device_category, manufacturer_match, source_xlsx_hash, test_definitions (JSON), cell_mappings (JSON), profile_extensions (JSON), prereq_rules (JSON), is_active, created_at |
| **test_runs** | id (UUID PK), device_id (FK), user_id (FK), agent_id (FK), template_id (FK), template_version, status (enum), start_time, end_time, overall_verdict, synopsis_text, synopsis_ai_drafted (bool), sync_status, created_offline (bool) |
| **test_results** | id (UUID PK), run_id (FK), test_number, test_name, tier (enum: auto/guided/auto_na), tool_used, raw_stdout, parsed_findings (JSON), verdict, auto_comment, engineer_selection, engineer_notes, is_overridden, override_reason, overridden_by (FK) |
| **attachments** | id (UUID PK), result_id (FK), file_name, mime_type, file_path, file_size_bytes, sha256_hash, upload_time |
| **agents** | id (UUID PK), name, user_id (FK), os_type, os_version, agent_version, last_heartbeat, status (enum), ip_address |
| **audit_logs** | id (UUID PK), timestamp, user_id (FK), action, resource_type, resource_id, ip_address, details (JSON) |
| **report_configs** | id (UUID PK), client_name, logo_path, compliance_standards (JSON), branding_colours (JSON) |
| **sync_queue** | id (UUID PK), agent_id (FK), run_id (FK), payload (JSON), created_at, synced_at, retry_count, status (enum) |
| **device_profiles** | id (UUID PK), name, category, detection_rules (JSON), additional_tests (JSON), is_active |

---

## 12. Deployment & Infrastructure

### 12.1 Central Server

Azure B2s VM (2 vCPU, 4GB RAM, 30GB SSD, ~£30/month). Docker Compose: Nginx (443), FastAPI (8000), Redis (6379), report worker. SQLite on persistent volume. Daily backups to Azure Blob. TLS via Let's Encrypt or corporate cert.

### 12.2 Agent Distribution

- **Windows:** NSIS/MSI installer. Bundles nmap.exe, MSYS2 runtime (testssl.sh, ssh-audit), nikto (Perl), Python agent (PyInstaller). ~200MB installed.
- **Mac:** .dmg with .app bundle. Native nmap, bash tools, Python agent. ~150MB installed.

Auto-update check on startup (when online). Updates prompted, never forced during active testing.

### 12.3 Agent System Tray

Right-click menu: Open Dashboard (browser to server or localhost if offline), Force Sync, View Local Results, Check for Updates, Quit.

---

## 13. Phased Delivery Plan

12 weeks from PRD approval. Phases overlap — independent workstreams proceed in parallel.

| Phase | Timeline | Deliverables |
|---|---|---|
| **Phase 1: Core Platform** | Weeks 1–4 | Central server, web UI, database, auth, device CRUD, agent protocol, auto-discovery pipeline, universal test library |
| **Phase 2: Scanning Agent** | Weeks 3–6 | Windows + Mac installer, tool bundling, scan execution, three-tier test engine, Wobbly Cable Handler, offline queue |
| **Phase 3: Manual + Templates** | Weeks 5–8 | Guided manual test workflow, template import system, device profiles, Nessus parser, cell mapping admin UI |
| **Phase 4: Reports** | Weeks 7–10 | Template-based Excel generation, Word reports, PDF export, compliance mapping, client branding, AI synopsis generator |
| **Phase 5: Hardening** | Weeks 9–12 | All 15 security controls verified, cross-platform testing, offline sync stress testing, penetration testing, documentation |

### 13.1 Definition of Done

V1.0 ships when ALL of the following pass:

1. At least one real device fully qualified through the complete pipeline (discovery → auto tests → manual tests → review → report) with output validated against a manually-created report for the same device.
2. Agent installs and operates on at least one Windows 10/11 and one macOS machine.
3. Offline testing validated: agent disconnected, full test executed, reconnected, results synced.
4. Generated Excel reports for both Pelco and EasyIO templates confirmed as client-deliverable quality by the lead security engineer.
5. All 15 security controls (Section 9.3) implemented and verified.
6. A completely new device type (not Pelco or EasyIO) has been tested using only the auto-discovery and universal test library, confirming device-agnostic operation.
7. PDF export produces accurate representations of both Excel and Word reports.

---

## 14. Risk Register

| ID | Level | Risk | Mitigation |
|---|---|---|---|
| **R-001** | **High** | Offline sync conflicts when multiple agents sync for same device | Last-write-wins with conflict detection queue for manual review |
| **R-002** | **High** | Scanning tools behave differently on Windows vs Mac vs Linux | Cross-platform test matrix; WSL fallback on Windows |
| **R-003** | Medium | Excel template pixel-fidelity vs hand-crafted originals | Template-based filling (edit actual .xlsx); 2–3 iteration rounds |
| **R-004** | Medium | Agent installer blocked by corporate antivirus | Code-sign installer; IT whitelisting docs; portable mode |
| **R-005** | Medium | New device types don't map to existing automated tools | Graceful degradation to manual; template supports custom mappings |
| **R-006** | Low | Server connection failures under 10 concurrent agents | Connection pooling, health checks, exponential backoff |
| **R-007** | **High** | Vulnerability data intercepted agent–server | TLS 1.3 mandatory; certificate pinning |
| **R-008** | Medium | Stolen laptop exposes offline scan data | AES-256 encryption; auto-purge after sync; 7-day max retention |
| **R-009** | Medium | AI synopsis hallucinates findings not in test data | Structured prompt with explicit constraints; human approval required; validation check |
| **R-010** | Low | Auto-discovery misidentifies device category | Engineer confirms/corrects before testing begins; universal tests run regardless |

---

## 15. Deferred Features (V2.0+ Roadmap)

| Feature | Target | Rationale |
|---|---|---|
| **Microsoft Entra ID SSO** | V2.0+ | Not needed until >15 users or external mandate |
| **PostgreSQL migration** | V2.0 | SQLite adequate for V1.0; migrate on write contention |
| **S3/MinIO object storage** | V2.0+ | Local file storage adequate for V1.0 evidence volumes |
| **Raspberry Pi station mode** | V2.0 | Laptop agent covers V1.0; Pi for permanent labs |
| **OpenTelemetry SIEM** | V3.0 | Database audit table sufficient for V1.0 |
| **Kubernetes / Helm** | V3.0+ | Docker Compose adequate until multi-region needed |
| **CI/CD pipeline** | V2.0 | Manual deployment acceptable for V1.0 |
| **Geographic replication** | V3.0+ | Single-region covers V1.0 team distribution |
| **Comparison view between runs** | V1.1 | Useful for retests but not day-one critical |
| **Browser notifications** | V1.1 | Nice-to-have; tray icon covers status awareness |

The V6.0 Enterprise PRD remains the authoritative long-term architectural reference. This V1.0 PRD defines the minimum viable product required to deliver immediate production value.

---

*END OF DOCUMENT*
