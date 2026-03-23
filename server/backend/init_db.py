"""Initialize the database and create default admin user."""
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
import uuid
import json


DEVICE_PROFILES = [
    {
        "name": "Network Camera",
        "manufacturer": "Generic",
        "category": "camera",
        "description": "IP cameras, PTZ cameras, fixed dome cameras",
        "additional_tests": [],
        "safe_mode": {"intensity": "safe", "nmap_rate_limit": "--max-rate 200", "parallel_probes": 2},
        "fingerprint_rules": {
            "port_hints": [554, 8554, 80, 443, 8080],
            "service_hints": ["rtsp", "http", "https"],
            "oui_vendors": ["Axis", "Pelco", "Hikvision", "Dahua", "Bosch"],
        },
    },
    {
        "name": "Building Controller",
        "manufacturer": "Generic",
        "category": "controller",
        "description": "HVAC controllers, BMS controllers, DDC controllers",
        "additional_tests": [],
        "safe_mode": {"intensity": "safe", "nmap_rate_limit": "--max-rate 100", "parallel_probes": 1},
        "fingerprint_rules": {
            "port_hints": [47808, 502, 4911, 1911],
            "service_hints": ["bacnet", "modbus", "niagara"],
            "oui_vendors": ["EasyIO", "Distech", "Johnson Controls", "Schneider Electric", "Sauter"],
        },
    },
    {
        "name": "IP Intercom",
        "manufacturer": "Generic",
        "category": "intercom",
        "description": "Door stations, video intercoms, access panels",
        "additional_tests": [],
        "safe_mode": {"intensity": "safe", "nmap_rate_limit": "--max-rate 150", "parallel_probes": 2},
        "fingerprint_rules": {
            "port_hints": [5060, 5061, 80, 443],
            "service_hints": ["sip", "http", "https"],
            "oui_vendors": ["2N", "Aiphone", "Comelit", "Doorbird"],
        },
    },
    {
        "name": "IoT Sensor",
        "manufacturer": "Generic",
        "category": "iot_sensor",
        "description": "Environmental sensors, occupancy sensors, energy meters",
        "additional_tests": [],
        "safe_mode": {"intensity": "safe", "nmap_rate_limit": "--max-rate 50", "parallel_probes": 1},
        "fingerprint_rules": {
            "port_hints": [1883, 8883, 5683, 161],
            "service_hints": ["mqtt", "coap", "snmp"],
            "oui_vendors": [],
        },
    },
    {
        "name": "Generic IP Device",
        "manufacturer": "Generic",
        "category": "unknown",
        "description": "Default profile for unclassified IP devices",
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


def init_db():
    """Create all tables and seed default data."""
    print("Creating database tables...")
    Base.metadata.create_all(bind=sync_engine)
    print("Tables created successfully.")

    db = SessionLocal()
    try:
        admin = _seed_admin_user(db)
        whitelist = _seed_protocol_whitelist(db, admin)
        _seed_device_profiles(db, admin, whitelist)
        _seed_test_templates(db, admin, whitelist)
        _seed_report_config(db, admin)

        db.commit()
        print("\nDatabase initialization complete!")
        print("Default credentials: admin / admin123")

    except Exception as e:
        db.rollback()
        print(f"Error during initialization: {e}")
        raise
    finally:
        db.close()


def _seed_admin_user(db):
    admin = db.query(User).filter(User.username == "admin").first()
    if not admin:
        admin = User(
            id=str(uuid.uuid4()),
            username="admin",
            email="admin@electracom.co.uk",
            password_hash=hash_password("Admin123!"),
            full_name="System Administrator",
            role="admin",
            is_active=True,
        )
        db.add(admin)
        db.flush()
        print("Created default admin user (admin / Admin123!)")
    return admin


def _seed_protocol_whitelist(db, admin):
    old_wl = db.query(ProtocolWhitelist).filter(ProtocolWhitelist.name == "Electracom Default").first()
    if old_wl:
        old_wl.name = "Electracom Standard"
        old_wl.description = "Standard Electracom protocol whitelist for smart building devices (from EasyIO template)"
        old_wl.entries = json.dumps(ELECTRACOM_WHITELIST_ENTRIES)
        db.flush()
        print("Updated existing 'Electracom Default' whitelist → 'Electracom Standard'")
        return old_wl

    existing = db.query(ProtocolWhitelist).filter(ProtocolWhitelist.name == "Electracom Standard").first()
    if existing:
        return existing

    whitelist = ProtocolWhitelist(
        id=str(uuid.uuid4()),
        name="Electracom Standard",
        description="Standard Electracom protocol whitelist for smart building devices (from EasyIO template)",
        entries=json.dumps(ELECTRACOM_WHITELIST_ENTRIES),
        is_default=True,
        created_by=admin.id,
    )
    db.add(whitelist)
    db.flush()
    print("Created 'Electracom Standard' protocol whitelist with 11 entries")
    return whitelist


def _seed_device_profiles(db, admin, whitelist):
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
            additional_tests=json.dumps(profile_data["additional_tests"]),
            safe_mode=json.dumps(profile_data["safe_mode"]),
            fingerprint_rules=json.dumps(profile_data["fingerprint_rules"]),
            is_active=True,
            created_by=admin.id,
        )
        db.add(profile)
        created += 1
    if created:
        db.flush()
        print(f"Created {created} device profile(s)")


def _seed_test_templates(db, admin, whitelist):
    all_test_ids = [t["test_id"] for t in UNIVERSAL_TESTS]
    essential_ids = [t["test_id"] for t in UNIVERSAL_TESTS if t.get("is_essential")]

    if not db.query(TestTemplate).filter(TestTemplate.name == "Full Security Assessment").first():
        db.add(TestTemplate(
            id=str(uuid.uuid4()),
            name="Full Security Assessment",
            description="Complete 30-test qualification suite covering all security domains",
            test_ids=json.dumps(all_test_ids),
            whitelist_id=whitelist.id,
            report_config=json.dumps({"template_key": "generic", "device_category": "generic"}),
            is_default=True,
            created_by=admin.id,
        ))
        print(f"Created 'Full Security Assessment' template with {len(all_test_ids)} tests")

    if not db.query(TestTemplate).filter(TestTemplate.name == "Essential Tests Only").first():
        db.add(TestTemplate(
            id=str(uuid.uuid4()),
            name="Essential Tests Only",
            description="Minimum required tests for device qualification",
            test_ids=json.dumps(essential_ids),
            whitelist_id=whitelist.id,
            report_config=json.dumps({"template_key": "generic", "device_category": "generic"}),
            is_default=False,
            created_by=admin.id,
        ))
        print(f"Created 'Essential Tests Only' template with {len(essential_ids)} tests")

    if not db.query(TestTemplate).filter(TestTemplate.name == "Pelco Camera Assessment").first():
        db.add(TestTemplate(
            id=str(uuid.uuid4()),
            name="Pelco Camera Assessment",
            description="Full 30-test qualification for Pelco camera devices (Rev 2 format)",
            test_ids=json.dumps(all_test_ids),
            whitelist_id=whitelist.id,
            report_config=json.dumps({"template_key": "pelco_camera", "device_category": "camera"}),
            is_default=False,
            created_by=admin.id,
        ))
        print("Created 'Pelco Camera Assessment' template")

    if not db.query(TestTemplate).filter(TestTemplate.name == "EasyIO Controller Assessment").first():
        db.add(TestTemplate(
            id=str(uuid.uuid4()),
            name="EasyIO Controller Assessment",
            description="Full 30-test qualification for EasyIO building controllers (v1.1 format)",
            test_ids=json.dumps(all_test_ids),
            whitelist_id=whitelist.id,
            report_config=json.dumps({"template_key": "easyio_controller", "device_category": "controller"}),
            is_default=False,
            created_by=admin.id,
        ))
        print("Created 'EasyIO Controller Assessment' template")

    db.flush()


def _seed_report_config(db, admin):
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
        compliance_standards=json.dumps(["ISO 27001", "Cyber Essentials", "SOC2"]),
        branding_colours=json.dumps({"primary": "#1F4E79", "accent": "#f59e0b"}),
        branding=json.dumps({
            "logo_url": "/app/templates/cropped-Electracom-Group-GREY (1).png",
            "company_name": "Electracom Projects Ltd",
            "colors": {"primary": "#1F4E79", "accent": "#f59e0b"},
        }),
        is_active=True,
        created_by=admin.id,
    )
    db.add(config)
    db.flush()
    print("Created Electracom default report config")


if __name__ == "__main__":
    init_db()
