import os
import sys
import json
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

from app import app
from models import db, Project, Document, DBConnection, ControlSchedule, ControlRunHistory, TargetArtifact

def test_prod_scheduler_and_connections():
    client = app.test_client()

    print("================================================================================")
    print("STEP 1: Authenticate with JWT")
    print("================================================================================")
    login_res = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert login_res.status_code == 200, f"Login failed: {login_res.data}"
    login_data = json.loads(login_res.data)
    token = login_data.get("access_token") or login_data.get("token")
    assert token, "No token returned"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    print("[PASS] Logged in successfully with Bearer token.")

    # Get or create project
    proj_res = client.get("/api/projects", headers=headers)
    assert proj_res.status_code == 200, f"List projects failed: {proj_res.data}"
    projects = json.loads(proj_res.data)
    assert len(projects) > 0, "No projects found."
    project_id = projects[0]["id"]
    print(f"[PASS] Using Project ID: {project_id} ('{projects[0]['name']}')")

    print("\n================================================================================")
    print("STEP 2: Test Saving, Updating, and Listing Database Connections")
    print("================================================================================")
    
    # 2A: Save a source connection with blank database_name and empty password on localhost
    save_conn_res = client.post(f"/api/projects/{project_id}/connections", json={
        "source_db_name": "E2E_Test_Source_DB",
        "db_type": "postgresql",
        "host": "localhost",
        "port": 5432,
        "database_name": "",  # Tests default to hla_db
        "username": "postgres",
        "password": "",  # Tests localhost password fallback
        "conn_role": "source"
    }, headers=headers)
    assert save_conn_res.status_code == 200, f"Save connection failed: {save_conn_res.data}"
    conn_payload = json.loads(save_conn_res.data)
    conn_data = conn_payload["connection"]
    conn_id = conn_data["id"]
    assert conn_data["database_name"] == "hla_db", f"Expected default 'hla_db', got '{conn_data['database_name']}'"
    assert conn_data["status"] == "connected", f"Expected connected, got {conn_data['status']}"
    print(f"[PASS] Created connection #{conn_id} '{conn_data['source_db_name']}' with auto-defaulted database_name='{conn_data['database_name']}' and status='{conn_data['status']}'.")

    # 2B: Update the existing connection using its ID
    update_conn_res = client.post(f"/api/projects/{project_id}/connections", json={
        "id": conn_id,
        "source_db_name": "E2E_Test_Source_DB_Renamed",
        "db_type": "postgresql",
        "host": "localhost",
        "port": 5432,
        "database_name": "hla_db",
        "username": "postgres",
        "conn_role": "source"
    }, headers=headers)
    assert update_conn_res.status_code == 200, f"Update connection failed: {update_conn_res.data}"
    updated_conn = json.loads(update_conn_res.data)["connection"]
    assert updated_conn["id"] == conn_id, f"ID mismatch: expected {conn_id}, got {updated_conn['id']}"
    assert updated_conn["source_db_name"] == "E2E_Test_Source_DB_Renamed"
    print(f"[PASS] Successfully updated connection #{conn_id} in-place with new name '{updated_conn['source_db_name']}'.")

    # 2C: Test connection test/ping endpoint
    ping_res = client.post(f"/api/projects/{project_id}/connections/test", json={
        "db_type": "postgresql",
        "host": "localhost",
        "port": 5432,
        "database_name": "hla_db",
        "username": "postgres"
    }, headers=headers)
    assert ping_res.status_code == 200
    ping_data = json.loads(ping_res.data)
    assert ping_data["success"] is True, f"Ping failed: {ping_data}"
    print(f"[PASS] Tested connection ping: {ping_data['message']}")

    print("\n================================================================================")
    print("STEP 3: Save and Verify Target Database Configuration for PROD")
    print("================================================================================")
    target_res = client.post(f"/api/projects/{project_id}/targets", json={
        "target_env": "prod",
        "apply_to_both": False,
        "db_type": "postgresql",
        "host": "localhost",
        "port": 5432,
        "database_name": "hla_db",
        "username": "postgres",
        "schema_name": "ra_ctrl_prod"
    }, headers=headers)
    assert target_res.status_code == 200, f"Target save failed: {target_res.data}"
    targets_data = json.loads(target_res.data)["targets"]
    assert targets_data["prod"] is not None, "Target PROD config not returned"
    assert targets_data["prod"]["status"] == "connected", f"Target PROD status: {targets_data['prod']['status']}"
    print(f"[PASS] Successfully saved Target PROD configuration: {targets_data['prod']['source_db_name']} (schema: {targets_data['prod']['schema_name']})")

    print("\n================================================================================")
    print("STEP 4: Create and Manage Control Schedule for PROD Environment")
    print("================================================================================")
    
    # Get active document
    docs_res = client.get(f"/api/projects/{project_id}", headers=headers)
    project_info = json.loads(docs_res.data)
    doc_id = None
    for d in project_info.get("documents", []):
        if d.get("analysis_data") or d.get("status") == "analyzed":
            doc_id = d["id"]
            break
    if not doc_id and project_info.get("documents"):
        doc_id = project_info["documents"][0]["id"]
    assert doc_id, "No document found in project."
    print(f"[PASS] Using Document ID: {doc_id}")

    # Create PROD schedule
    sched_payload = {
        "document_id": doc_id,
        "name": "Daily Enterprise PROD Reconciliation",
        "environment": "prod",
        "hostname": "localhost",
        "schedule_type": "daily",
        "run_time": "03:00",
        "timezone": "UTC",
        "notification_emails": "ops-prod@enterprise.com",
        "notify_on_failure": True
    }
    create_sched_res = client.post(f"/api/projects/{project_id}/schedules", json=sched_payload, headers=headers)
    assert create_sched_res.status_code == 201, f"Create schedule failed: {create_sched_res.data}"
    prod_sched = json.loads(create_sched_res.data)
    sched_id = prod_sched["id"]
    assert prod_sched["environment"] == "prod", f"Expected env 'prod', got '{prod_sched['environment']}'"
    assert prod_sched["next_run_at"] is not None
    print(f"[PASS] Created PROD Control Schedule #{sched_id}: '{prod_sched['name']}' [PROD] (Next Run: {prod_sched['next_run_at']})")

    # List schedules and verify PROD filtering
    sched_list_res = client.get(f"/api/projects/{project_id}/schedules", headers=headers)
    assert sched_list_res.status_code == 200
    all_schedules = json.loads(sched_list_res.data)
    prod_schedules = [s for s in all_schedules if s["environment"] == "prod"]
    assert any(s["id"] == sched_id for s in prod_schedules), "Created PROD schedule not in list!"
    print(f"[PASS] Verified PROD schedule list contains {len(prod_schedules)} PROD schedule(s).")

    print("\n================================================================================")
    print("STEP 5: Trigger Immediate Run Now on PROD Schedule")
    print("================================================================================")
    run_now_res = client.post(f"/api/projects/{project_id}/schedules/{sched_id}/run", headers=headers)
    assert run_now_res.status_code == 200, f"Run now failed: {run_now_res.data}"
    run_record = json.loads(run_now_res.data)
    print(f"[PASS] PROD Execution Run #{run_record['id']} completed with status: {run_record['status']}")
    print(f"  Target Environment: {run_record['environment'].upper()}")
    print(f"  Summary Message: {run_record['summary_message']}")
    assert run_record["environment"] == "prod", f"Expected 'prod', got {run_record['environment']}"
    assert "PROD" in run_record["execution_log"]
    print("  Verified log explicitly recorded execution for PROD target environment.")

    print("\n================================================================================")
    print("STEP 6: Trigger Direct Document Manual Control Run for PROD")
    print("================================================================================")
    manual_res = client.post(f"/api/projects/{project_id}/documents/{doc_id}/run-control", json={
        "environment": "prod",
        "hostname": "localhost"
    }, headers=headers)
    assert manual_res.status_code == 200, f"Manual run failed: {manual_res.data}"
    manual_run = json.loads(manual_res.data)
    assert manual_run["environment"] == "prod"
    print(f"[PASS] Direct Document Manual Run #{manual_run['id']} completed with environment: {manual_run['environment'].upper()}")

    print("\n================================================================================")
    print("STEP 7: Clean Up Temporary E2E Test Objects")
    print("================================================================================")
    del_sched_res = client.delete(f"/api/projects/{project_id}/schedules/{sched_id}", headers=headers)
    assert del_sched_res.status_code == 200
    print(f"[PASS] Deleted test PROD schedule #{sched_id}.")

    del_conn_res = client.delete(f"/api/projects/{project_id}/connections/{conn_id}", headers=headers)
    assert del_conn_res.status_code == 200
    print(f"[PASS] Deleted test connection #{conn_id}.")

    print("\n================================================================================")
    print(">>> ALL PROD SCHEDULER & CONNECTION TESTS PASSED 100% SUCCESSFULLY! <<<")
    print("================================================================================")

if __name__ == "__main__":
    test_prod_scheduler_and_connections()
