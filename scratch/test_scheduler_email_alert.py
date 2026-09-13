import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import json
from models import db, ControlSchedule, EmailNotificationLog, Project, Document
from app import app

BASE = "http://127.0.0.1:5000"

def test_failure_email_alert_flow():
    # 1. Database schema verification
    with app.app_context():
        with db.engine.connect() as conn:
            conn.execute(db.text("ALTER TABLE control_schedules ADD COLUMN IF NOT EXISTS notification_emails TEXT;"))
            conn.execute(db.text("ALTER TABLE control_schedules ADD COLUMN IF NOT EXISTS notify_on_failure BOOLEAN DEFAULT TRUE;"))
            conn.commit()
        db.create_all()
        print("[PASS] Database columns and email_notification_logs table verified in PostgreSQL")

    # 2. Login as admin
    s = requests.Session()
    login_res = s.post(f"{BASE}/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("[PASS] Admin login successful")

    # 3. Get first project
    proj_res = s.get(f"{BASE}/api/projects", headers=headers)
    assert proj_res.status_code == 200
    projects = proj_res.json()
    assert len(projects) > 0, "No projects found"
    project_id = projects[0]["id"]
    print(f"[PASS] Found project #{project_id} ('{projects[0]['name']}')")

    # 4. Test on-demand email alert endpoint
    test_alert_res = s.post(
        f"{BASE}/api/projects/{project_id}/schedules/test-email-alert",
        json={"recipient_emails": "qa-lead@telecom.com, devops@cloud.com"},
        headers=headers
    )
    assert test_alert_res.status_code == 200, f"Test alert failed: {test_alert_res.text}"
    alert_data = test_alert_res.json()
    assert alert_data["success"] is True
    assert "qa-lead@telecom.com" in alert_data["recipients"]
    assert "devops@cloud.com" in alert_data["recipients"]
    print(f"[PASS] On-demand test email failure alert dispatched to: {alert_data['recipients']}")

    # 5. Create a schedule with failure alerts enabled
    doc_res = s.get(f"{BASE}/api/projects/{project_id}", headers=headers)
    docs = doc_res.json().get("documents", [])
    assert len(docs) > 0, "No documents in project"
    doc_id = docs[0]["id"]

    sched_payload = {
        "document_id": doc_id,
        "name": "QA Failure Alert Scheduled Control",
        "environment": "dev",
        "hostname": "test-agent-host",
        "schedule_type": "daily",
        "run_time": "03:30",
        "notification_emails": "incident-response@telecom.com, lead-architect@enterprise.com",
        "notify_on_failure": True
    }
    create_sched = s.post(f"{BASE}/api/projects/{project_id}/schedules", json=sched_payload, headers=headers)
    assert create_sched.status_code == 201, f"Failed to create schedule: {create_sched.text}"
    sched_obj = create_sched.json()
    sched_id = sched_obj["id"]
    assert sched_obj["notification_emails"] == sched_payload["notification_emails"]
    assert sched_obj["notify_on_failure"] is True
    print(f"[PASS] Created schedule #{sched_id} with notification_emails='{sched_obj['notification_emails']}'")

    # 6. Trigger immediate run of this schedule
    # Note: If source tables are missing or not arrived, it triggers BLOCKED / FAILED, which triggers automatic email!
    run_res = s.post(f"{BASE}/api/projects/{project_id}/schedules/{sched_id}/run", headers=headers)
    assert run_res.status_code == 200, f"Run trigger failed: {run_res.text}"
    run_data = run_res.json()
    print(f"[PASS] Triggered schedule #{sched_id} run -> Status: {run_data['status']}")

    # 7. Verify email alert log endpoint
    email_logs_res = s.get(f"{BASE}/api/projects/{project_id}/schedules/email-alerts", headers=headers)
    assert email_logs_res.status_code == 200
    email_logs = email_logs_res.json()
    assert len(email_logs) > 0, "No email logs found"
    latest_email = email_logs[0]
    clean_subject = latest_email['subject'].encode('ascii', errors='replace').decode('ascii')
    print(f"[PASS] Verified EmailNotificationLog in DB: Subject='{clean_subject}', Recipients='{latest_email['recipient_emails']}', Status='{latest_email['status']}'")

    # 8. Clean up test schedule
    del_res = s.delete(f"{BASE}/api/projects/{project_id}/schedules/{sched_id}", headers=headers)
    assert del_res.status_code == 200
    print("[PASS] Cleaned up test schedule")

    print("\nALL SCHEDULE FAILURE EMAIL ALERT TESTS PASSED!")

if __name__ == "__main__":
    test_failure_email_alert_flow()
