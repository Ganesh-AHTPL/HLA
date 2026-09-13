import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from app import app
from models import db, Project, Document, User, ControlSchedule
import control_scheduler

def test_monthly_schedule():
    with app.app_context():
        # Find or create a test user
        user = User.query.first()
        user_id = user.id if user else None

        # Find or create a test project and document
        project = Project.query.first()
        if not project:
            project = Project(name="Test Project", description="Test")
            db.session.add(project)
            db.session.commit()

        doc = Document.query.filter_by(project_id=project.id).first()
        if not doc:
            doc = Document(project_id=project.id, filename="test.xlsx", original_name="test.xlsx", file_type="excel")
            db.session.add(doc)
            db.session.commit()

        # 1. Test next run calculations for monthly runs
        # Test day 1
        nr1 = control_scheduler.compute_next_run(
            schedule_type="monthly",
            run_time="03:00",
            day_of_month="1",
            tz_name="UTC"
        )
        assert nr1 is not None, "Failed calculating monthly next run for day 1"
        assert nr1.day == 1, f"Expected day 1, got {nr1.day}"
        assert nr1.hour == 3, f"Expected hour 3, got {nr1.hour}"

        # Test day 15
        nr15 = control_scheduler.compute_next_run(
            schedule_type="monthly",
            run_time="14:30",
            day_of_month="15",
            tz_name="UTC"
        )
        assert nr15 is not None, "Failed calculating monthly next run for day 15"
        assert nr15.day == 15, f"Expected day 15, got {nr15.day}"
        assert nr15.hour == 14 and nr15.minute == 30, f"Expected 14:30, got {nr15.hour}:{nr15.minute}"

        # Test last day of month
        nr_last = control_scheduler.compute_next_run(
            schedule_type="monthly",
            run_time="23:00",
            day_of_month="last",
            tz_name="UTC"
        )
        assert nr_last is not None, "Failed calculating monthly next run for last day"
        assert nr_last.hour == 23 and nr_last.minute == 0

        # 2. Test ControlSchedule model creation & serialization
        sched = ControlSchedule(
            project_id=project.id,
            document_id=doc.id,
            name="Monthly Recon Control Run",
            control_number="Control-23",
            environment="dev",
            hostname="recon-host.internal",
            schedule_type="monthly",
            run_time="04:15",
            day_of_month="10",
            timezone_name="UTC",
            is_active=True,
            next_run_at=control_scheduler.compute_next_run(
                schedule_type="monthly",
                run_time="04:15",
                day_of_month="10",
                tz_name="UTC"
            ),
            created_by_id=user_id
        )
        db.session.add(sched)
        db.session.commit()

        d = sched.to_dict()
        assert d["schedule_type"] == "monthly", f"Expected 'monthly', got {d['schedule_type']}"
        assert d["day_of_month"] == "10", f"Expected '10', got {d['day_of_month']}"
        assert d["run_time"] == "04:15", f"Expected '04:15', got {d['run_time']}"
        assert d["next_run_at"] is not None

        # 3. Test job registration in APScheduler
        control_scheduler.register_schedule_job(sched, app)
        job = control_scheduler.get_scheduler().get_job(f"ctrl_sched_{sched.id}")
        assert job is not None, "Job should be registered in APScheduler"

        # 4. Clean up test schedule
        control_scheduler.unregister_schedule_job(sched.id)
        db.session.delete(sched)
        db.session.commit()

        print("[SUCCESS] Monthly scheduler model, next_run computation, and APScheduler registration tests PASSED!")

if __name__ == "__main__":
    test_monthly_schedule()
