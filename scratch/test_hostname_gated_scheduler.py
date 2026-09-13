import requests

BASE = "http://localhost:5000"

def test_hostname_gated_scheduler():
    s = requests.Session()
    login_res = s.post(f"{BASE}/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert login_res.status_code == 200
    headers = {"Authorization": f"Bearer {login_res.json()['token']}"}
    print("[1/6] Admin logged in successfully.")

    # 1. Attempt to create schedule WITHOUT hostname
    res_no_host = s.post(f"{BASE}/api/projects/22/schedules", json={
        "document_id": 36,
        "name": "Should Fail Without Hostname",
        "environment": "dev",
        "schedule_type": "daily",
        "run_time": "05:00",
        "hostname": ""
    }, headers=headers)
    print("[2/6] Create schedule without hostname response:", res_no_host.status_code, res_no_host.json())
    assert res_no_host.status_code == 400
    assert "Hostname is required" in res_no_host.json().get("error", "")

    # 2. Create schedule WITH hostname
    res_with_host = s.post(f"{BASE}/api/projects/22/schedules", json={
        "document_id": 36,
        "name": "Host Validated Schedule",
        "environment": "dev",
        "schedule_type": "daily",
        "run_time": "05:00",
        "hostname": "prod-recon-runner.internal.corp"
    }, headers=headers)
    assert res_with_host.status_code == 201
    sched = res_with_host.json()
    sched_id = sched["id"]
    print(f"[3/6] Created Schedule #{sched_id} with hostname '{sched['hostname']}'.")
    assert sched["hostname"] == "prod-recon-runner.internal.corp"

    # 3. Attempt to update schedule to empty hostname
    update_res = s.put(f"{BASE}/api/projects/22/schedules/{sched_id}", json={
        "hostname": ""
    }, headers=headers)
    print("[4/6] Update schedule with empty hostname response:", update_res.status_code, update_res.json())
    assert update_res.status_code == 400
    assert "Hostname is required" in update_res.json().get("error", "")

    # 4. Attempt document on-demand run without hostname
    doc_run_no_host = s.post(f"{BASE}/api/projects/22/documents/36/run-control", json={
        "environment": "dev",
        "hostname": ""
    }, headers=headers)
    print("[5/6] Direct control run without hostname response:", doc_run_no_host.status_code, doc_run_no_host.json())
    assert doc_run_no_host.status_code == 400

    # 5. Run schedule with valid hostname
    run_res = s.post(f"{BASE}/api/projects/22/schedules/{sched_id}/run", headers=headers)
    assert run_res.status_code == 200
    run_data = run_res.json()
    print(f"[6/6] Run Now with hostname succeeded: Run #{run_data['id']}, Hostname: '{run_data['hostname']}'")
    assert run_data["hostname"] == "prod-recon-runner.internal.corp"
    assert "Execution Target Hostname: prod-recon-runner.internal.corp" in run_data["execution_log"]

    print("\n>>> ALL HOSTNAME GATING TESTS PASSED PERFECTLY! <<<")

if __name__ == "__main__":
    test_hostname_gated_scheduler()
