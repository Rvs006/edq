# EDQ - Electracom Device Qualifier - PRD

## Overview
EDQ is an automated network security testing platform for smart building IP devices. It provides comprehensive device qualification through network scanning, vulnerability assessment, and compliance testing.

## Core Features

### Authentication & Security
- User login/logout with session management
- CSRF protection
- Two-factor authentication (TOTP)
- OIDC/SSO integration (Google, Microsoft, custom)
- Role-based access control (admin, user)
- Account lockout after failed attempts
- Secure cookie handling

### Dashboard
- Overview of devices, projects, test runs
- Recent activity
- Statistics and trends via Recharts

### Device Management
- Add/edit/delete devices
- Device profiles
- Device fingerprinting
- Authorized networks management

### Project Management
- Create/edit/delete projects
- Assign devices to projects

### Testing
- Test templates management
- Test plans creation
- Test run execution
- Test results viewing
- Automated scanning (nmap, testssl, ssh-audit, hydra)
- CVE correlation

### Network Scanning
- Network discovery
- Port scanning
- Service detection
- OS fingerprinting
- Scheduled scans

### Reporting
- Generate PDF/DOCX/XLSX reports
- AI-powered synopsis generation
- Report configuration

### Administration
- User management
- Branding/settings
- Audit logging
- Protocol whitelists

### Agent System
- Remote agent management
- Agent heartbeat monitoring
- WebSocket-based real-time terminal

## Technical Architecture
- Frontend: React 19 + Vite + TypeScript + Tailwind CSS
- Backend: Python FastAPI + SQLAlchemy + PostgreSQL
- Real-time: WebSocket connections
- Container: Docker + Docker Compose
