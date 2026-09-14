import requests
import json
import time

BASE_URL = "http://localhost:5000"

def test_governance_phase1():
    print("\n=======================================================", flush=True)
    print("RUNNING COMPLETE PHASE 1 GOVERNANCE & RBAC TEST SUITE", flush=True)
    print("=======================================================\n", flush=True)

    # 1. Unauthenticated request to /api/governance/users -> 401
    res = requests.get(f"{BASE_URL}/api/governance/users")
    assert res.status_code == 401, f"Expected 401, got {res.status_code}"
    print("[PASS] 1. Unauthenticated access correctly returns 401 Unauthorized", flush=True)

    # 2. Login as 'admin'
    res = requests.post(f"{BASE_URL}/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert res.status_code == 200, f"Admin login failed: {res.text}"
    admin_data = res.json()
    admin_token = admin_data["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    assert "effective_permissions" in admin_data["user"]
    assert len(admin_data["user"]["effective_permissions"]) >= 25
    print(f"[PASS] 2. Admin login succeeded ({len(admin_data['user']['effective_permissions'])} permissions granted)", flush=True)

    # 3. Login as 'architect'
    res = requests.post(f"{BASE_URL}/api/auth/login", json={"username": "architect", "password": "architect123"})
    assert res.status_code == 200, f"Architect login failed: {res.text}"
    arch_token = res.json()["access_token"]
    arch_headers = {"Authorization": f"Bearer {arch_token}"}
    print("[PASS] 3. Architect login succeeded", flush=True)

    # 4. Login as 'viewer'
    res = requests.post(f"{BASE_URL}/api/auth/login", json={"username": "viewer", "password": "viewer123"})
    assert res.status_code == 200, f"Viewer login failed: {res.text}"
    viewer_token = res.json()["access_token"]
    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}
    print("[PASS] 4. Viewer login succeeded", flush=True)

    # 5. RBAC boundaries: Architect trying to access /api/governance/users -> MUST return 403
    res = requests.get(f"{BASE_URL}/api/governance/users", headers=arch_headers)
    assert res.status_code == 403, f"Expected 403 for architect on /users, got {res.status_code}"
    print("[PASS] 5. Architect blocked (403) from /api/governance/users", flush=True)

    # 6. RBAC boundaries: Viewer trying to access /api/governance/users -> MUST return 403
    res = requests.get(f"{BASE_URL}/api/governance/users", headers=viewer_headers)
    assert res.status_code == 403, f"Expected 403 for viewer on /users, got {res.status_code}"
    print("[PASS] 6. Viewer blocked (403) from /api/governance/users", flush=True)

    # 7. Admin listing users -> 200 OK
    res = requests.get(f"{BASE_URL}/api/governance/users", headers=admin_headers)
    assert res.status_code == 200, f"Admin get users failed: {res.text}"
    users_resp = res.json()
    assert "users" in users_resp
    print(f"[PASS] 7. Admin retrieved user directory ({users_resp['total']} total users)", flush=True)

    # 8. Create a test user
    test_user_payload = {
        "username": "gov_test_user",
        "password": "TestPassword123!",
        "email": "gov_test@enterprise.com",
        "role": "viewer",
        "status": "ACTIVE"
    }
    # Cleanup if exists
    del_res = requests.delete(f"{BASE_URL}/api/governance/users/9999", headers=admin_headers) # dummy
    res = requests.post(f"{BASE_URL}/api/governance/users", json=test_user_payload, headers=admin_headers)
    if res.status_code == 409:
        # fetch user id and delete
        u_find = requests.get(f"{BASE_URL}/api/governance/users?q=gov_test_user", headers=admin_headers).json()["users"]
        if u_find:
            requests.delete(f"{BASE_URL}/api/governance/users/{u_find[0]['id']}", headers=admin_headers)
        res = requests.post(f"{BASE_URL}/api/governance/users", json=test_user_payload, headers=admin_headers)

    assert res.status_code == 201, f"User creation failed: {res.text}"
    created_user = res.json()["user"]
    test_user_id = created_user["id"]
    print(f"[PASS] 8. User created successfully (ID: {test_user_id}, Role: {created_user['role']})", flush=True)

    # 9. Test user permissions query
    res = requests.get(f"{BASE_URL}/api/governance/users/{test_user_id}/permissions", headers=admin_headers)
    assert res.status_code == 200
    p_info = res.json()
    assert "effective_permissions" in p_info
    print(f"[PASS] 9. User effective permissions retrieved ({p_info['permission_count']} permissions)", flush=True)

    # 10. Self-Protection: Admin cannot disable own account
    admin_user_id = admin_data["user"]["id"]
    res = requests.post(f"{BASE_URL}/api/governance/users/{admin_user_id}/status", json={"status": "DISABLED"}, headers=admin_headers)
    assert res.status_code == 400, f"Expected 400 for admin self-disable, got {res.status_code}"
    print("[PASS] 10. Self-Protection: Admin cannot disable own active account (400 Bad Request)", flush=True)

    # 11. Self-Protection: Admin cannot lock own account
    res = requests.post(f"{BASE_URL}/api/governance/users/{admin_user_id}/status", json={"status": "LOCKED"}, headers=admin_headers)
    assert res.status_code == 400, f"Expected 400 for admin self-lock, got {res.status_code}"
    print("[PASS] 11. Self-Protection: Admin cannot lock own active account (400 Bad Request)", flush=True)

    # 12. Self-Protection: Admin cannot delete own account
    res = requests.delete(f"{BASE_URL}/api/governance/users/{admin_user_id}", headers=admin_headers)
    assert res.status_code == 400, f"Expected 400 for admin self-delete, got {res.status_code}"
    print("[PASS] 12. Self-Protection: Admin cannot delete own active account (400 Bad Request)", flush=True)

    # 13. Self-Protection: Admin cannot demote own account
    res = requests.put(f"{BASE_URL}/api/governance/users/{admin_user_id}", json={"role": "viewer"}, headers=admin_headers)
    assert res.status_code == 400, f"Expected 400 for admin self-demote, got {res.status_code}"
    print("[PASS] 13. Self-Protection: Admin cannot remove own Administrator privileges (400 Bad Request)", flush=True)

    # 14. Force Logout Test: increment token_version for test user
    # First login as test user
    res = requests.post(f"{BASE_URL}/api/auth/login", json={"username": "gov_test_user", "password": "TestPassword123!"})
    assert res.status_code == 200
    test_token = res.json()["access_token"]
    test_headers = {"Authorization": f"Bearer {test_token}"}

    # Verify token works
    res = requests.get(f"{BASE_URL}/api/auth/me", headers=test_headers)
    assert res.status_code == 200

    # Admin force logouts test user
    res = requests.post(f"{BASE_URL}/api/governance/users/{test_user_id}/force-logout", headers=admin_headers)
    assert res.status_code == 200, f"Force logout failed: {res.text}"
    print("[PASS] 14. Force logout endpoint executed successfully", flush=True)

    # Now previously issued token for test user MUST return 401
    res = requests.get(f"{BASE_URL}/api/auth/me", headers=test_headers)
    assert res.status_code == 401, f"Expected 401 after force logout, got {res.status_code}"
    print("[PASS] 15. Previous session immediately invalidated by force logout (401)", flush=True)

    # 16. Account Lockout Protection: test 5 consecutive failed logins
    dummy_user = "gov_test_user"
    for attempt in range(1, 6):
        res = requests.post(f"{BASE_URL}/api/auth/login", json={"username": dummy_user, "password": f"WrongPass{attempt}"})
    # 6th attempt must be 403 account locked
    res = requests.post(f"{BASE_URL}/api/auth/login", json={"username": dummy_user, "password": "TestPassword123!"})
    assert res.status_code == 403, f"Expected 403 for locked user, got {res.status_code} ({res.text})"
    assert "locked" in res.text.lower()
    print("[PASS] 16. Brute-force protection: Account locked after 5 failed attempts (403 Forbidden)", flush=True)

    # Admin unlocks user
    res = requests.post(f"{BASE_URL}/api/governance/users/{test_user_id}/status", json={"status": "ACTIVE"}, headers=admin_headers)
    assert res.status_code == 200
    print("[PASS] 17. Admin successfully unlocked account back to ACTIVE", flush=True)

    # 17. Roles Management: List, Create Custom Role, Clone, Delete
    res = requests.get(f"{BASE_URL}/api/governance/roles", headers=admin_headers)
    assert res.status_code == 200
    roles = res.json()
    assert len(roles) >= 3
    print(f"[PASS] 18. Retrieved roles list ({len(roles)} roles)", flush=True)

    # Cannot delete system role
    admin_role = next(r for r in roles if r["code"] == "admin")
    res = requests.delete(f"{BASE_URL}/api/governance/roles/{admin_role['id']}", headers=admin_headers)
    assert res.status_code == 400
    print("[PASS] 19. Prevented deletion of system Administrator role (400)", flush=True)

    # Create custom role
    custom_role_code = f"compliance_{int(time.time())}"
    res = requests.post(f"{BASE_URL}/api/governance/roles", json={
        "name": "Compliance Auditor",
        "code": custom_role_code,
        "description": "Reviews control executions and audit trails",
        "permissions": ["control.view", "evidence.view", "audit.view"]
    }, headers=admin_headers)
    assert res.status_code == 201, f"Create custom role failed: {res.text}"
    custom_role = res.json()["role"]
    print(f"[PASS] 20. Created custom role '{custom_role['name']}' ({custom_role['code']})", flush=True)

    # Clone custom role
    res = requests.post(f"{BASE_URL}/api/governance/roles/{custom_role['id']}/clone", json={
        "name": "Junior Auditor",
        "code": f"jr_{custom_role_code}"
    }, headers=admin_headers)
    assert res.status_code == 201
    cloned_role = res.json()["role"]
    print(f"[PASS] 21. Cloned role to '{cloned_role['name']}'", flush=True)

    # 18. Permissions Matrix:
    res = requests.get(f"{BASE_URL}/api/governance/permissions/matrix", headers=admin_headers)
    assert res.status_code == 200
    matrix_data = res.json()
    assert len(matrix_data["permissions"]) == 25
    assert "categories" in matrix_data
    print(f"[PASS] 22. Permission matrix loaded (25 standard permissions across {len(matrix_data['categories'])} domains)", flush=True)

    # Update role permissions matrix
    res = requests.put(f"{BASE_URL}/api/governance/permissions/matrix", json={
        "role_code": custom_role_code,
        "permissions": ["control.view", "audit.view"]
    }, headers=admin_headers)
    assert res.status_code == 200
    print("[PASS] 23. Role-permission matrix updated successfully", flush=True)

    # 19. Audit Center & Append-Only Behavior:
    res = requests.get(f"{BASE_URL}/api/governance/audit/events?page=1&page_size=10", headers=admin_headers)
    assert res.status_code == 200
    audit_data = res.json()
    assert audit_data["total"] > 0
    # Verify metadata contains NO password/secret
    for ev in audit_data["events"]:
        meta_str = json.dumps(ev["metadata"]).lower()
        assert "admin123" not in meta_str
        assert "wrongpass" not in meta_str
        assert "testpassword" not in meta_str
    print(f"[PASS] 24. Audit Center records inspected ({audit_data['total']} total immutable events, 0 credentials found)", flush=True)

    # Audit CSV Export
    res = requests.get(f"{BASE_URL}/api/governance/audit/export", headers=admin_headers)
    assert res.status_code == 200
    assert "text/csv" in res.headers.get("Content-Type", "")
    assert "Timestamp (UTC)" in res.text
    print(f"[PASS] 25. Audit CSV export verified ({len(res.text.splitlines())} lines generated)", flush=True)

    # 20. Security Center Health Summary:
    res = requests.get(f"{BASE_URL}/api/governance/security-center/summary", headers=admin_headers)
    assert res.status_code == 200
    sec_data = res.json()
    assert sec_data["database"]["status"] == "CONNECTED"
    assert "authentication" in sec_data
    assert "kpis" in sec_data
    # Assert no secret keys
    sec_str = json.dumps(sec_data).lower()
    assert "password" not in sec_str
    assert "secret" not in sec_str
    print(f"[PASS] 26. Security Center summary verified (DB: {sec_data['database']['status']}, Active Accounts: {sec_data['kpis']['active_accounts']})", flush=True)

    # 21. Executive Overview Foundation:
    res = requests.get(f"{BASE_URL}/api/governance/executive-overview", headers=admin_headers)
    assert res.status_code == 200
    exec_data = res.json()
    assert "metrics" in exec_data
    print(f"[PASS] 27. Executive Overview verified (Projects: {exec_data['metrics']['projects_count']}, Controls: {exec_data['metrics']['controls_count']})", flush=True)

    # Clean up test entities
    requests.delete(f"{BASE_URL}/api/governance/users/{test_user_id}", headers=admin_headers)
    requests.delete(f"{BASE_URL}/api/governance/roles/{cloned_role['id']}", headers=admin_headers)
    requests.delete(f"{BASE_URL}/api/governance/roles/{custom_role['id']}", headers=admin_headers)

    print("\n=======================================================", flush=True)
    print("ALL 27 PHASE 1 BACKEND & RBAC TESTS PASSED SUCCESSFULLY!", flush=True)
    print("=======================================================\n", flush=True)

if __name__ == "__main__":
    test_governance_phase1()
