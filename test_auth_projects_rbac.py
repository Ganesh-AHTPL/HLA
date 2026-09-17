import requests
import json
import sys

BASE_URL = "http://localhost:5000"

def test_auth_projects():
    print("=== Testing /api/projects Authentication & RBAC ===", flush=True)

    # 1. Unauthenticated GET /api/projects -> MUST return 401
    res = requests.get(f"{BASE_URL}/api/projects")
    assert res.status_code == 401, f"Expected 401 for unauthenticated request, got: {res.status_code}"
    err_json = res.json()
    assert "error" in err_json, "Expected error message in response"
    print("[PASS] Unauthenticated request to /api/projects correctly returns 401 Unauthorized", flush=True)

    # 2. Invalid Token GET /api/projects -> MUST return 401
    res = requests.get(f"{BASE_URL}/api/projects", headers={"Authorization": "Bearer invalid.jwt.token"})
    assert res.status_code == 401, f"Expected 401 for invalid token, got: {res.status_code}"
    print("[PASS] Invalid token request to /api/projects correctly returns 401 Unauthorized", flush=True)

    # 3. Authenticated Login as 'architect'
    res = requests.post(f"{BASE_URL}/api/auth/login", json={"username": "architect", "password": "architect123"})
    assert res.status_code == 200, f"Login failed: {res.text}"
    token_data = res.json()
    token = token_data.get("access_token") or token_data.get("token")
    assert token, "Token not returned from login"
    print("[PASS] Login as 'architect' succeeded", flush=True)

    # 4. Authenticated GET /api/projects -> MUST return 200 OK
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.get(f"{BASE_URL}/api/projects", headers=headers)
    assert res.status_code == 200, f"Expected 200 for authenticated request, got: {res.status_code}"
    projects = res.json()
    assert isinstance(projects, list), "Expected list of projects"
    print(f"[PASS] Authenticated request to /api/projects succeeded with 200 OK ({len(projects)} projects returned)", flush=True)

    # 5. Authenticated Login as 'viewer'
    res = requests.post(f"{BASE_URL}/api/auth/login", json={"username": "viewer", "password": "viewer123"})
    assert res.status_code == 200, f"Login as viewer failed: {res.text}"
    viewer_token = res.json().get("access_token") or res.json().get("token")

    # Viewer can read projects (200 OK)
    v_headers = {"Authorization": f"Bearer {viewer_token}"}
    res = requests.get(f"{BASE_URL}/api/projects", headers=v_headers)
    assert res.status_code == 200, f"Viewer read failed: {res.status_code}"
    print("[PASS] Viewer can read /api/projects with 200 OK", flush=True)

    # Viewer CANNOT create project (403 Forbidden via @role_required('admin', 'architect'))
    res = requests.post(f"{BASE_URL}/api/projects", json={"name": "Forbidden Project"}, headers=v_headers)
    assert res.status_code == 403, f"Expected 403 Forbidden for viewer creating project, got: {res.status_code}"
    print("[PASS] RBAC Enforced: Viewer creating project correctly returns 403 Forbidden", flush=True)

    print("\n========================================================", flush=True)
    print("ALL AUTHENTICATION & RBAC TESTS PASSED SUCCESSFULLY!", flush=True)
    print("========================================================", flush=True)

if __name__ == "__main__":
    test_auth_projects()
