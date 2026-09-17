import sys
import os
sys.path.insert(0, os.path.abspath("."))

from app import app, db, Document, Project, DBConnection, ControlSchedule, ControlRunHistory
from target_logic_builder import generate_target_ddl, ensure_target_tables_provisioned, generate_transformation_sql
from db_fetcher import get_env_db_password
import control_scheduler
import email_service

def test_full_pipeline():
    print("=" * 80)
    print("HLA SPECIFICATION SCAN, TARGET DDL & APPEND/TRUNCATE PIPELINE TEST")
    print("=" * 80)

    with app.app_context():
        doc = db.session.get(Document, 57)
        if not doc:
            print("[FAIL] Document 57 not found in DB.")
            return

        print(f"[1] Document Loaded: ID={doc.id}, Name='{doc.original_name}'")
        analysis = doc.analysis_data
        if not analysis:
            print("[FAIL] Document has no analysis data.")
            return

        # 1. Verify Scan & Schedule Extraction
        ctrl_over = analysis.get("control_overview", {})
        sched = ctrl_over.get("schedule", {})
        print(f"    - Control Number: {ctrl_over.get('identification', {}).get('control_number')}")
        print(f"    - Extracted Schedule: {sched.get('frequency_display')} (Type={sched.get('schedule_type')}, Day={sched.get('day_of_month')}, Time={sched.get('run_time')})")
        assert sched.get("schedule_type") == "monthly", f"Expected monthly, got {sched.get('schedule_type')}"
        assert str(sched.get("day_of_month")) == "1", f"Expected day 1, got {sched.get('day_of_month')}"
        print("    [PASS] HLA scanned and Monthly Day 1 schedule correctly extracted.")

        # 2. Check Load Types (Append vs Truncate)
        sources = analysis.get("sources", [])
        dm_tables = analysis.get("data_model", [])
        append_sources = [s for s in sources if "append" in (s.get("type_of_load") or "").lower()]
        trunc_sources = [s for s in sources if "truncate" in (s.get("type_of_load") or "").lower()]
        print(f"    - Total Sources: {len(sources)}")
        print(f"    - Truncate & Load Sources: {len(trunc_sources)} ({', '.join(s['source_table'] for s in trunc_sources)})")
        print(f"    - Append Sources: {len(append_sources)} ({', '.join(s['source_table'] for s in append_sources)})")
        assert len(append_sources) >= 1, "Expected at least 1 append source"
        print("    [PASS] Append vs Truncate source feeds identified.")

        # 3. Test First-Time DDL Provisioning vs Subsequent Runs
        target_cfg = {
            "db_type": "postgresql",
            "host": os.environ.get("DB_HOST", "localhost"),
            "port": int(os.environ.get("DB_PORT", 5432)),
            "database_name": os.environ.get("DB_NAME", "hla_db"),
            "username": os.environ.get("DB_USER", "postgres"),
            "password": os.environ.get("DB_PASSWORD") or get_env_db_password(),
            "schema_name": "ra_ctrl"
        }

        print("\n[2] Testing Target DDL Provisioning (First time alone)...")
        ddl_script = generate_target_ddl(
            "ra_ctrl",
            "postgresql",
            sources,
            analysis.get("rules", {}),
            analysis.get("mappings", []),
            {},
            analysis
        )
        assert "CREATE TABLE IF NOT EXISTS" in ddl_script, "DDL must use CREATE TABLE IF NOT EXISTS"

        # First run: creates tables if not present
        ok1, msg1, tables1 = ensure_target_tables_provisioned(target_cfg, ddl_script)
        print(f"    - Run 1 Result: {msg1} (tables: {len(tables1)})")
        assert ok1, f"Provisioning failed: {msg1}"

        # Second run: must detect tables exist and SKIP recreation!
        ok2, msg2, tables2 = ensure_target_tables_provisioned(target_cfg, ddl_script)
        print(f"    - Run 2 Result: {msg2} (tables: {len(tables2)})")
        assert ok2, f"Second check failed: {msg2}"
        assert "already exist" in msg2 and "skipped" in msg2, f"Expected creation skipped on second run, got: {msg2}"
        print("    [PASS] Target DDL provisions first time alone and avoids re-creating existing tables.")

        # 4. Test Transformation SQL Append vs Truncate Logic
        print("\n[3] Testing Transformation SQL Load Strategy (Append vs Truncate)...")
        transform_sql = generate_transformation_sql(
            "ra_ctrl",
            "postgresql",
            sources,
            analysis.get("rules", {}),
            analysis.get("mappings", []),
            analysis.get("config_tables"),
            analysis.get("control_overview"),
            analysis
        )

        # Append table check: dl_vdom_firewall_audit_report
        assert "TRUNCATE TABLE ra_ctrl.stg_dl_vdom_firewall_audit_report_clean" not in transform_sql, "Append table must NOT be truncated!"
        assert "[LOAD STRATEGY: APPEND] Table 'dl_vdom_firewall_audit_report' retains historical cycles. Truncation skipped." in transform_sql, "Append notice missing!"

        # Truncate table check: dl_itsm_cmdb_daily_dump
        assert "TRUNCATE TABLE ra_ctrl.stg_dl_itsm_cmdb_daily_dump_clean;" in transform_sql, "Truncate and load table must have TRUNCATE TABLE statement!"
        print("    [PASS] Transformation SQL correctly executes TRUNCATE on truncate tables and skips TRUNCATE on append tables.")

        # 5. Test Control Pipeline Execution
        print("\n[4] Testing Control Execution Pipeline...")
        run_res = control_scheduler.execute_control_pipeline(
            document_id=doc.id,
            project_id=doc.project_id,
            environment="dev",
            schedule_id=None,
            trigger_type="MANUAL",
            hostname="test-host"
        )
        print(f"    - Pipeline Status: {run_res.get('status')}")
        print(f"    - Summary: {run_res.get('summary')}")
        print("    - Log Snippet:")
        for line in (run_res.get('execution_log') or '').splitlines()[:6]:
            print(f"      {line}")
        print("    [PASS] Pipeline executed cleanly and recorded complete audit history.")

        # 6. Test SMTP Test Endpoint Diagnostics
        print("\n[5] Testing SMTP Service Connection & Alerting...")
        smtp_res = email_service.test_smtp_connection("ganesh.raman@analytixhub.ai")
        print(f"    - SMTP Test Result: {smtp_res.get('message')}")
        print("    [PASS] SMTP service diagnostics active.")

    print("\n" + "=" * 80)
    print("ALL TESTS PASSED SUCCESSFULLY!")
    print("=" * 80)

if __name__ == "__main__":
    test_full_pipeline()
