import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app, db
from models import SystemSetting, EmailNotificationLog
import email_service

class TestZeroConfigEmail(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config["TESTING"] = True
        cls.ctx = app.app_context()
        cls.ctx.push()

    @classmethod
    def tearDownClass(cls):
        cls.ctx.pop()

    def setUp(self):
        # Clear any SMTP settings so host is empty
        SystemSetting.query.filter(SystemSetting.key.like("smtp_%")).delete()
        db.session.commit()

    def test_zero_config_test_email(self):
        result = email_service.test_smtp_connection("ganesh.raman@analytixhub.ai")
        self.assertTrue(result["success"])
        self.assertEqual(result["delivery_mode"], "Zero-Config Direct Engine")
        self.assertEqual(result["preview"]["to"], "ganesh.raman@analytixhub.ai")
        self.assertIn("Email Dispatch Test", result["preview"]["subject"])

    def test_zero_config_failure_alert(self):
        class DummyRun:
            id = 9999
            control_number = "CTRL-01"
            environment = "Production"
            hostname = "prod-runner-01"
            status = "FAILED"
            summary_message = "Source table billing_events is missing."
            started_at = None
            result_details = {"tables_checked": 2, "tables_missing": 1, "missing_list": ["public.billing_events"]}

        result = email_service.send_control_failure_alert(
            run_record=DummyRun(),
            failure_reason="Source table billing_events is missing.",
            additional_recipients="operations@analytixhub.ai"
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["delivery_mode"], "Zero-Config Direct Engine")
        self.assertIn("operations@analytixhub.ai", result["sent_to"])

        # Check DB record
        log = EmailNotificationLog.query.filter(EmailNotificationLog.recipient_emails.contains("operations@analytixhub.ai")).order_by(EmailNotificationLog.id.desc()).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.status, "DISPATCHED")

if __name__ == "__main__":
    unittest.main()
