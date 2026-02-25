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

def init_db():
    """Create all tables and seed default data."""
    print("Creating database tables...")
    Base.metadata.create_all(bind=sync_engine)
    print("Tables created successfully.")

    db = SessionLocal()
    try:
        # Create default admin user
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            admin = User(
                id=str(uuid.uuid4()),
                username="admin",
                email="admin@edq.local",
                password_hash=hash_password("admin123"),
                full_name="System Administrator",
                role="admin",
                is_active=True,
            )
            db.add(admin)
            print("Created default admin user (admin / admin123)")

        # Create default test template with all 30 tests
        default_template = db.query(TestTemplate).filter(TestTemplate.name == "Full Security Assessment").first()
        if not default_template:
            all_test_ids = [t["test_id"] for t in UNIVERSAL_TESTS]
            default_template = TestTemplate(
                id=str(uuid.uuid4()),
                name="Full Security Assessment",
                description="Complete 30-test qualification suite covering all security domains",
                test_ids=json.dumps(all_test_ids),
                is_default=True,
                created_by=admin.id if admin else None,
            )
            db.add(default_template)
            print(f"Created default test template with {len(all_test_ids)} tests")

        # Create essential-only template
        essential_template = db.query(TestTemplate).filter(TestTemplate.name == "Essential Tests Only").first()
        if not essential_template:
            essential_ids = [t["test_id"] for t in UNIVERSAL_TESTS if t.get("is_essential")]
            essential_template = TestTemplate(
                id=str(uuid.uuid4()),
                name="Essential Tests Only",
                description="Minimum required tests for device qualification",
                test_ids=json.dumps(essential_ids),
                is_default=False,
                created_by=admin.id if admin else None,
            )
            db.add(essential_template)
            print(f"Created essential-only template with {len(essential_ids)} tests")

        # Create default protocol whitelist
        default_wl = db.query(ProtocolWhitelist).filter(ProtocolWhitelist.name == "Electracom Default").first()
        if not default_wl:
            entries = [
                {"port": 80, "protocol": "TCP", "service": "HTTP", "required_version": ""},
                {"port": 443, "protocol": "TCP", "service": "HTTPS/TLS", "required_version": "TLS 1.2+"},
                {"port": 554, "protocol": "TCP", "service": "RTSP", "required_version": ""},
                {"port": 8080, "protocol": "TCP", "service": "HTTP Alt", "required_version": ""},
                {"port": 22, "protocol": "TCP", "service": "SSH", "required_version": "OpenSSH 8.0+"},
            ]
            default_wl = ProtocolWhitelist(
                id=str(uuid.uuid4()),
                name="Electracom Default",
                description="Standard protocol whitelist for smart building devices",
                entries=json.dumps(entries),
                is_default=True,
                created_by=admin.id if admin else None,
            )
            db.add(default_wl)
            print("Created default protocol whitelist")

        db.commit()
        print("\nDatabase initialization complete!")
        print("Default credentials: admin / admin123")

    except Exception as e:
        db.rollback()
        print(f"Error during initialization: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    init_db()
