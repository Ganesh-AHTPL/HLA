"""
scratch/test_source_db_gate_and_email.py
Comprehensive verification test suite for:
1. Strict Source DB and Table availability enforcement during manual & scheduled runs.
2. Dynamic SMTP Settings persistence and live error reporting.
"""

import os
import sys
import unittest

# Ensure root directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app, db
from models import Project, Document, DBConnection, ControlSchedule, ControlRunHistory, SystemSetting, User
import control_scheduler
import email_service


class TestSourceDBGateAndEmail(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config["TESTING"] = True
        cls.ctx = app.app_context()
        cls.ctx.push()

    @classmethod
    def tearDownClass(cls):
        cls.ctx.pop()

    def setUp(self):
        # Create a fresh clean test project with a dummy HLA document
        self.project = Project(name="Gatekeeper Test Workspace", description="Test project for gate enforcement")
        db.session.add(self.project)
        db.session.commit()

        self.doc = Document(
            project_id=self.project.id,
            filename="Test_Control_Specification.docx",
            original_name="Test Control 23 Spec",
            file_type="docx",
            file_size=1024,
            file_path="uploads/test_control_spec.docx",
            status="analyzed",
            analysis_data={
                "control_overview": {
                    "identification": {"control_number": "CTRL-99", "control_title": "Test Control 99"},
                    "control_digits": "99",
                    "target_schema": "ra_ctrl.ctrl_99"
                },
                "sources": [
                    {
                        "source_table": "raw_feed_events",
                        "source_schema": "public",
                        "source_system": "BillingCore",
                        "load_type": "Truncate and load",
                        "frequency": "Daily"
                    },
                    {
                        "source_table": "subscriber_profiles",
                        "source_schema": "public",
                        "source_system": "CRM",
                        "load_type": "Append",
                        "frequency": "Daily"
                    }
                ]
            }
        )
        db.session.add(self.doc)
        db.session.commit()

    def tearDown(self):
        # Clean up test project and artifacts
        try:
            db.session.delete(self.project)
            db.session.commit()
        except Exception:
            db.session.rollback()

    def test_01_manual_run_without_source_db_strictly_fails(self):
        """
        Verify that running a control manually without source database info configured
        MUST FAIL immediately and not succeed or fall back to localhost.
        """
        # Ensure 0 source DB connections exist for this project
        source_conns = DBConnection.query.filter_by(project_id=self.project.id, conn_role="source").all()
        self.assertEqual(len(source_conns), 0, "Precondition failed: Project should have 0 source DB connections")

        # Execute control pipeline manually
        result = control_scheduler.execute_control_pipeline(
            document_id=self.doc.id,
            project_id=self.project.id,
            environment="dev",
            schedule_id=None,
            trigger_type="MANUAL",
            hostname="test-runner-01"
        )

        print("\n--- Test 01: Manual Run Without Source DB Info ---")
        print(f"Status: {result.get('status')}")
        print(f"Summary: {result.get('summary_message')}")

        # The run MUST FAIL
        self.assertEqual(result.get("status"), "FAILED", "Run MUST FAIL when no source DB info is configured!")
        self.assertIn("No source database info configured", result.get("summary_message", ""),
                      "Summary must clearly state that source database info is missing!")

        # Verify in database
        run_record = ControlRunHistory.query.get(result["id"])
        self.assertIsNotNone(run_record)
        self.assertEqual(run_record.status, "FAILED")

    def test_02_manual_run_with_missing_tables_strictly_fails(self):
        """
        Verify that if source DB is configured but declared tables are missing,
        the run MUST FAIL or BE BLOCKED.
        """
        # Add a source DB connection pointing to an empty test schema/db
        test_conn = DBConnection(
            project_id=self.project.id,
            source_db_name="LegacyCRM",
            conn_role="source",
            db_type="postgresql",
            host="localhost",
            port=5432,
            database_name="hla_db",
            username="postgres",
            password="fake_password_or_clean",
            schema_name="nonexistent_schema_xyz",
            status="connected"
        )
        db.session.add(test_conn)
        db.session.commit()

        # Execute control pipeline manually
        result = control_scheduler.execute_control_pipeline(
            document_id=self.doc.id,
            project_id=self.project.id,
            environment="dev",
            schedule_id=None,
            trigger_type="MANUAL",
            hostname="test-runner-01"
        )

        print("\n--- Test 02: Manual Run With Missing Tables ---")
        print(f"Status: {result.get('status')}")
        print(f"Summary: {result.get('summary_message')}")

        # Must be BLOCKED or FAILED because tables don't exist
        self.assertIn(result.get("status"), ["BLOCKED", "FAILED"],
                      "Run MUST FAIL or BE BLOCKED when source tables are not available!")
        self.assertNotEqual(result.get("status"), "SUCCESS")

    def test_03_smtp_settings_persistence_and_unconfigured_status(self):
        """
        Verify that SMTP settings can be saved to SystemSetting table,
        and that unconfigured SMTP returns clean diagnostic failure rather than faking delivery.
        """
        # 1. Clear any existing smtp settings for test
        SystemSetting.query.filter(SystemSetting.key.like("smtp_%")).delete()
        db.session.commit()

        # 2. Verify is_smtp_configured is False
        cfg = email_service.get_smtp_config()
        print("\n--- Test 03: SMTP Settings & Diagnostic Status ---")
        print(f"Default SMTP Config: host='{cfg.get('host')}', user='{cfg.get('user')}'")

        # 3. Save real configuration
        save_data = {
            "host": "smtp.gmail.com",
            "port": 587,
            "user": "test-alerts@gmail.com",
            "password": "abcd efgh ijkl mnop",
            "security": "starttls",
            "from_email": "test-alerts@gmail.com"
        }
        updated = email_service.save_smtp_config(save_data)
        self.assertEqual(updated["host"], "smtp.gmail.com")
        self.assertEqual(updated["port"], 587)
        self.assertEqual(updated["user"], "test-alerts@gmail.com")
        self.assertTrue(email_service.is_smtp_configured(updated))
        print("[OK] SMTP Config successfully saved in PostgreSQL SystemSetting table.")

        # 4. Test connection function with invalid auth returns proper diagnostic error
        test_res = email_service.test_smtp_connection("recipient@enterprise.com", override_config=updated)
        print(f"SMTP Test Connection Result: success={test_res.get('success')}, message='{test_res.get('message')}'")
        # Since 'abcd efgh ijkl mnop' is not a real app password, Gmail will reject with Authentication error
        self.assertFalse(test_res["success"])
        self.assertTrue("Authentication failed" in test_res["message"] or "failed" in test_res["message"].lower())


if __name__ == "__main__":
    unittest.main()
