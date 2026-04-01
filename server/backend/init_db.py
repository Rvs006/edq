"""Initialize the database and create default admin user.

NOTE: For schema changes after the initial release, use Alembic migrations:
    cd server/backend
    alembic revision --autogenerate -m "describe_change"
    alembic upgrade head

This script remains as a fallback for fresh installs where Base.metadata.create_all()
is used to bootstrap the schema before seeding default data.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.models.database import sync_engine, Base, SessionLocal
from app.models.user import User
from app.models.device import Device
from app.models.device_profile import DeviceProfile
from app.models.test_template import TestTemplate
from app.models.test_run import TestRun
from app.models.test_result import TestResult
from app.models.attachment import Attachment
from app.models.agent import Agent
from app.models.audit_log import AuditLog
from app.models.report_config import ReportConfig
from app.models.sync_queue import SyncQueue
from app.models.protocol_whitelist import ProtocolWhitelist
from app.security.auth import hash_password
from app.services.test_library import UNIVERSAL_TESTS
from sqlalchemy import text
from sqlalchemy.orm import Session
import uuid
import json


DEVICE_PROFILES = [
    {
        "name": "IoT Gateway",
        "manufacturer": "Generic",
        "category": "iot_gateway",
        "description": "Devices with BACnet, MQTT, CoAP, or Modbus — controllers, gateways, BMS systems",
        "additional_tests": [],
        "safe_mode": {"intensity": "safe", "nmap_rate_limit": "--max-rate 100", "parallel_probes": 1},
        "fingerprint_rules": {
            "port_hints": [47808, 1883, 8883, 5683, 502, 4911],
            "service_hints": ["bacnet", "mqtt", "coap", "modbus"],
            "oui_vendors": ["EasyIO", "Distech", "Johnson Controls", "Schneider Electric", "Sauter"],
        },
    },
    {
        "name": "Standard Device",
        "manufacturer": "Generic",
        "category": "standard_device",
        "description": "All other IP devices — cameras, intercoms, sensors, access control panels",
        "additional_tests": [],
        "safe_mode": {"intensity": "safe", "nmap_rate_limit": "--max-rate 200", "parallel_probes": 2},
        "fingerprint_rules": {},
    },
]

ELECTRACOM_WHITELIST_ENTRIES = [
    {"port": 22, "protocol": "TCP", "service": "sFTP/SSH", "required_version": "OpenSSH 8.0+"},
    {"port": 68, "protocol": "UDP", "service": "DHCP Client", "required_version": ""},
    {"port": 53, "protocol": "UDP", "service": "DNS", "required_version": ""},
    {"port": 443, "protocol": "TCP", "service": "HTTPS", "required_version": "TLS 1.2+"},
    {"port": 123, "protocol": "UDP", "service": "NTP", "required_version": "NTPv4"},
    {"port": 161, "protocol": "UDP", "service": "SNMPv3", "required_version": "v3 only"},
    {"port": 636, "protocol": "TCP", "service": "LDAPS", "required_version": "TLS 1.2+"},
    {"port": 989, "protocol": "TCP", "service": "FTPS Data", "required_version": "TLS 1.2+"},
    {"port": 990, "protocol": "TCP", "service": "FTPS Control", "required_version": "TLS 1.2+"},
    {"port": 8883, "protocol": "TCP", "service": "MQTTS", "required_version": "TLS 1.2+"},
    {"port": 47808, "protocol": "UDP", "service": "BACnet/IP", "required_version": ""},
]

DISCOURAGED_PORTS = [
    {"port": 21, "reason": "FTP — cleartext credentials"},
    {"port": 23, "reason": "Telnet — cleartext protocol"},
    {"port": 80, "reason": "HTTP — unencrypted web traffic"},
    {"port": 69, "reason": "TFTP — no authentication"},
    {"port": 110, "reason": "POP3 — cleartext email"},
    {"port": 143, "reason": "IMAP — cleartext email"},
    {"port": 161, "reason": "SNMP v1/v2 — community string auth (v3 only is acceptable)"},
    {"port": 445, "reason": "SMB — high attack surface"},
    {"port": 1900, "reason": "UPnP/SSDP — network discovery exposure"},
    {"port": 5353, "reason": "mDNS — device information leakage"},
    {"port": 8080, "reason": "HTTP-alt — unencrypted web traffic"},
]


def init_db() -> None:
    """Create all tables and seed default data."""
    print("Creating database tables...")
    Base.metadata.create_all(bind=sync_engine)
    print("Tables created successfully.")

    db = SessionLocal()
    try:
        _run_migrations(db)
        admin = _seed_admin_user(db)
        whitelist = _seed_protocol_whitelist(db, admin)
        _seed_device_profiles(db, admin, whitelist)
        _seed_test_templates(db, admin, whitelist)
        _seed_report_config(db, admin)

        db.commit()
        print("\nDatabase initialization complete!")

    except Exception as e:
        db.rollback()
        print(f"Error during initialization: {e}")
        raise
    finally:
        db.close()


def _run_migrations(db: Session) -> None:
    """Add columns that may be missing from existing databases."""
    migrations = [
        "ALTER TABLE report_configs ADD COLUMN client_name TEXT",
        "ALTER TABLE report_configs ADD COLUMN logo_path TEXT",
        "ALTER TABLE report_configs ADD COLUMN compliance_standards TEXT",
        "ALTER TABLE report_configs ADD COLUMN branding_colours TEXT",
        "ALTER TABLE test_runs ADD COLUMN connection_scenario TEXT DEFAULT 'direct'",
        "ALTER TABLE test_results ADD COLUMN engineer_notes TEXT",
        "ALTER TABLE test_results ADD COLUMN override_reason TEXT",
        "ALTER TABLE test_results ADD COLUMN override_verdict TEXT",
        "ALTER TABLE test_results ADD COLUMN overridden_by_user_id TEXT",
        "ALTER TABLE test_results ADD COLUMN overridden_by_username TEXT",
        "ALTER TABLE test_results ADD COLUMN overridden_at DATETIME",
    ]
    for sql in migrations:
        try:
            db.execute(text(sql))
        except Exception:
            pass
    db.commit()

    # Fix any templates with duplicate test_ids (e.g. U20 appearing twice)
    _dedup_template_test_ids(db)


def _dedup_template_test_ids(db: Session) -> None:
    """Remove duplicate entries from test_ids JSON arrays in all templates."""
    templates = db.query(TestTemplate).all()
    for tmpl in templates:
        raw = tmpl.test_ids
        if isinstance(raw, str):
            raw = json.loads(raw)
        if not raw:
            continue
        seen: set = set()
        deduped = []
        for tid in raw:
            if tid not in seen:
                seen.add(tid)
                deduped.append(tid)
        if len(deduped) != len(raw):
            print(f"  Fixed duplicate test_ids in template '{tmpl.name}': {len(raw)} → {len(deduped)}")
            tmpl.test_ids = deduped
    db.commit()


def _seed_admin_user(db: Session) -> User:
    admin = db.query(User).filter(User.username == "admin").first()
    if not admin:
        from app.config import settings
        initial_password = settings.INITIAL_ADMIN_PASSWORD
        admin = User(
            id=str(uuid.uuid4()),
            username="admin",
            email="admin@electracom.co.uk",
            password_hash=hash_password(initial_password),
            full_name="System Administrator",
            role="admin",
            is_active=True,
        )
        db.add(admin)
        db.flush()
        print(f"Created default admin user. Set INITIAL_ADMIN_PASSWORD in .env before first run.")
    return admin


def _seed_protocol_whitelist(db: Session, admin: User) -> ProtocolWhitelist:
    old_wl = db.query(ProtocolWhitelist).filter(ProtocolWhitelist.name == "Electracom Default").first()
    if old_wl:
        old_wl.name = "Electracom Standard"
        old_wl.description = "Standard Electracom protocol whitelist for smart building devices (from EasyIO template)"
        old_wl.entries = ELECTRACOM_WHITELIST_ENTRIES
        db.flush()
        print("Updated existing 'Electracom Default' whitelist → 'Electracom Standard'")
        return old_wl

    existing = db.query(ProtocolWhitelist).filter(ProtocolWhitelist.name == "Electracom Standard").first()
    if existing:
        existing.entries = ELECTRACOM_WHITELIST_ENTRIES
        existing.description = "Standard Electracom protocol whitelist for smart building devices (from EasyIO template)"
        db.flush()
        return existing

    whitelist = ProtocolWhitelist(
        id=str(uuid.uuid4()),
        name="Electracom Standard",
        description="Standard Electracom protocol whitelist for smart building devices (from EasyIO template)",
        entries=ELECTRACOM_WHITELIST_ENTRIES,
        is_default=True,
        created_by=admin.id,
    )
    db.add(whitelist)
    db.flush()
    print("Created 'Electracom Standard' protocol whitelist with 11 entries")
    return whitelist


def _seed_device_profiles(db: Session, admin: User, whitelist: ProtocolWhitelist) -> None:
    created = 0
    for profile_data in DEVICE_PROFILES:
        existing = db.query(DeviceProfile).filter_by(category=profile_data["category"]).first()
        if existing:
            continue
        profile = DeviceProfile(
            id=str(uuid.uuid4()),
            name=profile_data["name"],
            manufacturer=profile_data["manufacturer"],
            category=profile_data["category"],
            description=profile_data["description"],
            default_whitelist_id=whitelist.id,
            additional_tests=profile_data["additional_tests"],
            safe_mode=profile_data["safe_mode"],
            fingerprint_rules=profile_data["fingerprint_rules"],
            is_active=True,
            created_by=admin.id,
        )
        db.add(profile)
        created += 1
    if created:
        db.flush()
        print(f"Created {created} device profile(s)")


def _seed_test_templates(db: Session, admin: User, whitelist: ProtocolWhitelist) -> None:
    all_test_ids = [t["test_id"] for t in UNIVERSAL_TESTS]
    essential_ids = [t["test_id"] for t in UNIVERSAL_TESTS if t.get("is_essential")]

    full_tmpl = db.query(TestTemplate).filter(TestTemplate.name == "Full Security Assessment").first()
    if full_tmpl:
        full_tmpl.test_ids = all_test_ids
        full_tmpl.description = f"Complete {len(all_test_ids)}-test qualification suite covering all security domains"
    else:
        db.add(TestTemplate(
            id=str(uuid.uuid4()),
            name="Full Security Assessment",
            description=f"Complete {len(all_test_ids)}-test qualification suite covering all security domains",
            test_ids=all_test_ids,
            whitelist_id=whitelist.id,
            report_config={"template_key": "generic", "device_category": "generic"},
            is_default=True,
            created_by=admin.id,
        ))
    print(f"Seeded 'Full Security Assessment' template with {len(all_test_ids)} tests")

    essential_tmpl = db.query(TestTemplate).filter(TestTemplate.name == "Essential Tests Only").first()
    if essential_tmpl:
        essential_tmpl.test_ids = essential_ids
        essential_tmpl.description = f"Minimum required tests for device qualification ({len(essential_ids)} essential tests)"
    else:
        db.add(TestTemplate(
            id=str(uuid.uuid4()),
            name="Essential Tests Only",
            description=f"Minimum required tests for device qualification ({len(essential_ids)} essential tests)",
            test_ids=essential_ids,
            whitelist_id=whitelist.id,
            report_config={"template_key": "generic", "device_category": "generic"},
            is_default=False,
            created_by=admin.id,
        ))
    print(f"Seeded 'Essential Tests Only' template with {len(essential_ids)} tests")

    pelco_tmpl = db.query(TestTemplate).filter(TestTemplate.name == "Pelco Camera Assessment").first()
    if pelco_tmpl:
        pelco_tmpl.test_ids = all_test_ids
        pelco_tmpl.description = f"Full {len(all_test_ids)}-test qualification for Pelco camera devices (Rev 2 format)"
    else:
        db.add(TestTemplate(
            id=str(uuid.uuid4()),
            name="Pelco Camera Assessment",
            description=f"Full {len(all_test_ids)}-test qualification for Pelco camera devices (Rev 2 format)",
            test_ids=all_test_ids,
            whitelist_id=whitelist.id,
            report_config={"template_key": "pelco_camera", "device_category": "camera"},
            is_default=False,
            created_by=admin.id,
        ))
    print("Seeded 'Pelco Camera Assessment' template")

    easyio_tmpl = db.query(TestTemplate).filter(TestTemplate.name == "EasyIO Controller Assessment").first()
    if easyio_tmpl:
        easyio_tmpl.test_ids = all_test_ids
        easyio_tmpl.description = f"Full {len(all_test_ids)}-test qualification for EasyIO building controllers (v1.1 format)"
    else:
        db.add(TestTemplate(
            id=str(uuid.uuid4()),
            name="EasyIO Controller Assessment",
            description=f"Full {len(all_test_ids)}-test qualification for EasyIO building controllers (v1.1 format)",
            test_ids=all_test_ids,
            whitelist_id=whitelist.id,
            report_config={"template_key": "easyio_controller", "device_category": "controller"},
            is_default=False,
            created_by=admin.id,
        ))
    print("Seeded 'EasyIO Controller Assessment' template")

    db.flush()


def _seed_report_config(db: Session, admin: User) -> None:
    existing = db.query(ReportConfig).filter(ReportConfig.client_name == "Electracom Projects Ltd").first()
    if existing:
        return

    config = ReportConfig(
        id=str(uuid.uuid4()),
        name="Electracom Default Report",
        description="Default report configuration for Electracom Projects Ltd",
        client_name="Electracom Projects Ltd",
        logo_path="/app/templates/cropped-Electracom-Group-GREY (1).png",
        report_type="excel",
        compliance_standards=["ISO 27001", "Cyber Essentials", "SOC2"],
        branding_colours={"primary": "#1F4E79", "accent": "#f59e0b"},
        branding={
            "logo_url": "/app/templates/cropped-Electracom-Group-GREY (1).png",
            "company_name": "Electracom Projects Ltd",
            "colors": {"primary": "#1F4E79", "accent": "#f59e0b"},
        },
        is_active=True,
        created_by=admin.id,
    )
    db.add(config)
    db.flush()
    print("Created Electracom default report config")


if __name__ == "__main__":
    init_db()
