import requests

BASE = "http://localhost:5000"

def test_control_scheduler_e2e():
    s = requests.Session()
    login_res = s.post(f"{BASE}/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    token = login_res.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("[1/8] Admin login successful.")

    # 1. Fetch initial schedules
    res = s.get(f"{BASE}/api/projects/22/schedules", headers=headers)
    assert res.status_code == 200
    initial_schedules = res.json()
    print(f"[2/8] Fetched {len(initial_schedules)} existing schedule(s) for Project 22.")

    # 2. Create new schedule
    payload = {
        "document_id": 36,
        "name": "Control-Test Hourly Production Scan",
        "environment": "prod",
        "schedule_type": "hourly",
        "run_time": "00:15",
        "timezone": "UTC"
    }
    create_res = s.post(f"{BASE}/api/projects/22/schedules", json=payload, headers=headers)
    assert create_res.status_code == 201, f"Create failed: {create_res.text}"
    new_sched = create_res.json()
    sched_id = new_sched["id"]
    print(f"[3/8] Created Schedule #{sched_id}: '{new_sched['name']}' (Next: {new_sched['next_run_at']})")

    # 3. Update schedule
    update_res = s.put(f"{BASE}/api/projects/22/schedules/{sched_id}", json={
        "name": "Control-Test Daily Nightly Reconcile",
        "schedule_type": "daily",
        "run_time": "04:00"
    }, headers=headers)
    assert update_res.status_code == 200
    updated = update_res.json()
    assert updated["name"] == "Control-Test Daily Nightly Reconcile"
    print(f"[4/8] Updated Schedule #{sched_id} name & time to 04:00.")

    # 4. Trigger Run Now
    print(f"[5/8] Triggering 'Run Now' on Schedule #{sched_id}...")
    run_res = s.post(f"{BASE}/api/projects/22/schedules/{sched_id}/run", headers=headers)
    assert run_res.status_code == 200, f"Run Now failed: {run_res.text}"
    run_data = run_res.json()
    run_id = run_data["id"]
    print(f"      Run #{run_id} completed: status={run_data['status']}, duration={run_data['duration_seconds']}s")
    print(f"      Tables checked: {run_data['tables_checked_count']}, Missing: {run_data['tables_missing_count']}")
    assert run_data["status"] == "BLOCKED"  # Strictly blocked because source tables are missing from source DB!

    # 5. Verify direct document control run
    doc_run_res = s.post(f"{BASE}/api/projects/22/documents/36/run-control", json={"environment": "dev"}, headers=headers)
    assert doc_run_res.status_code == 200
    print(f"[6/8] Direct document control run executed: Run #{doc_run_res.json()['id']} (Status: {doc_run_res.json()['status']})")

    # 6. Query execution history & detail log
    hist_res = s.get(f"{BASE}/api/projects/22/schedules/history", headers=headers)
    assert hist_res.status_code == 200
    runs = hist_res.json()
    print(f"[7/8] History records found: {len(runs)}")

    detail_res = s.get(f"{BASE}/api/projects/22/schedules/history/{run_id}", headers=headers)
    assert detail_res.status_code == 200
    run_detail = detail_res.json()
    assert "QUALITY GATE ENGAGED" in run_detail["execution_log"]
    print("      Verified console audit log contains QUALITY GATE ENGAGED.")

    # 7. Toggle schedule
    toggle_res = s.post(f"{BASE}/api/projects/22/schedules/{sched_id}/toggle", headers=headers)
    assert toggle_res.status_code == 200
    assert toggle_res.json()["is_active"] == False
    print(f"[8/8] Toggled schedule #{sched_id} to paused.")

    print("\n>>> ALL CONTROL SCHEDULER E2E TESTS PASSED SUCCESSFULLY! <<<")

if __name__ == "__main__":
    test_control_scheduler_e2e()
