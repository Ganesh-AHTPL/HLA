import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from datetime import datetime, timezone, timedelta
from app import app
from models import db, Document, Project
import control_scheduler
from sqlalchemy import text

def run_tests():
    with app.app_context():
        proj = Project.query.first()
        if not proj:
            print("No project found.")
            return

        with db.engine.connect() as conn:
            conn.execute(text("CREATE TABLE IF NOT EXISTS public.dl_test_append (id INT, created_at TIMESTAMP)"))
            conn.execute(text("TRUNCATE TABLE public.dl_test_append"))
            conn.commit()

        test_analysis = {
            "sources": [
                {
                    "source_table": "dl_test_append",
                    "full_table_name": "public.dl_test_append",
                    "source_schema": "public",
                    "source_system": "Test Feed",
                    "type_of_load": "Append. (Take the latest week data for reconciliation)",
                    "frequency": "Weekly",
                    "schedule_time": "Every Monday 9AM IST"
                }
            ]
        }
        test_doc = Document(
            project_id=proj.id,
            filename="Test_Append_Doc.xlsx",
            original_name="Test_Append_Doc.xlsx",
            file_type=".xlsx",
            file_size=1000,
            file_path="",
            status="analyzed",
            analysis_data=test_analysis
        )
        db.session.add(test_doc)
        db.session.commit()

        try:
            # Case 1: Table exists, but 0 rows (feed not arrived)
            res1 = control_scheduler.execute_control_pipeline(
                document_id=test_doc.id,
                project_id=proj.id,
                environment="dev",
                hostname="test-node"
            )
            print("Case 1 (Table exists, 0 rows - feed not arrived):")
            print("  Status:", res1.get("status"))
            print("  Summary:", res1.get("summary_message"))

            # Case 2: Append table has data, but older than 14 days (stale feed)
            with db.engine.connect() as conn:
                conn.execute(text("INSERT INTO public.dl_test_append VALUES (1, NOW() - INTERVAL '14 days')"))
                conn.commit()

            res2 = control_scheduler.execute_control_pipeline(
                document_id=test_doc.id,
                project_id=proj.id,
                environment="dev",
                hostname="test-node"
            )
            print("Case 2 (Append table has stale data from 14 days ago):")
            print("  Status:", res2.get("status"))
            print("  Summary:", res2.get("summary_message"))

            # Case 3: Fresh data inserted for current cycle
            with db.engine.connect() as conn:
                conn.execute(text("INSERT INTO public.dl_test_append VALUES (2, NOW())"))
                conn.commit()

            res3 = control_scheduler.execute_control_pipeline(
                document_id=test_doc.id,
                project_id=proj.id,
                environment="dev",
                hostname="test-node"
            )
            print("Case 3 (Append table has fresh data for current run):")
            print("  Status:", res3.get("status"))
            print("  Summary:", res3.get("summary_message"))

        finally:
            with db.engine.connect() as conn:
                conn.execute(text("DROP TABLE IF EXISTS public.dl_test_append"))
                conn.commit()
            db.session.delete(test_doc)
            db.session.commit()

if __name__ == "__main__":
    run_tests()
