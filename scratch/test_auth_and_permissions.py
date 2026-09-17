import requests

BASE = "http://127.0.0.1:5000"

def test_auth_workflow():
    s = requests.Session()

    # 1. Test Login with invalid credentials
    bad_login = s.post(f"{BASE}/api/auth/login", json={"username": "admin", "password": "wrongpassword"})
    assert bad_login.status_code == 401, f"Expected 401, got {bad_login.status_code}"
    print("[PASS] Invalid credentials rejected with 401")

    # 2. Test Login with Admin credentials
    login_res = s.post(f"{BASE}/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert login_res.status_code == 200, f"Expected 200, got {login_res.status_code}"
    data = login_res.json()
    token = data["access_token"]
    user = data["user"]
    assert user["role"] == "admin", f"Expected role admin, got {user['role']}"
    headers = {"Authorization": f"Bearer {token}"}
    print(f"[PASS] Admin login successful for {user['username']}")

    # 3. Test Create a new user with 'viewer' role
    test_user = "test_qa_user_42"
    # Clean up if existed from previous run
    users_list = s.get(f"{BASE}/api/auth/users", headers=headers).json()
    for u in users_list:
        if u["username"] == test_user:
            s.delete(f"{BASE}/api/auth/users/{u['id']}", headers=headers)

    create_res = s.post(f"{BASE}/api/auth/users", json={
        "username": test_user,
        "password": "qa_password_123",
        "email": "qa@enterprise.com",
        "role": "viewer"
    }, headers=headers)
    assert create_res.status_code == 201, f"Failed to create user: {create_res.text}"
    created_user = create_res.json()["user"]
    assert created_user["role"] == "viewer"
    uid = created_user["id"]
    print(f"[PASS] User '{test_user}' created with role: {created_user['role']}")

    # 4. Test Login with the newly created user
    qa_session = requests.Session()
    qa_login = qa_session.post(f"{BASE}/api/auth/login", json={"username": test_user, "password": "qa_password_123"})
    assert qa_login.status_code == 200, f"Login failed for new user: {qa_login.text}"
    qa_token = qa_login.json()["access_token"]
    qa_headers = {"Authorization": f"Bearer {qa_token}"}
    print(f"[PASS] Newly created user '{test_user}' can log in successfully")

    # 5. Verify viewer cannot access admin user management
    forbidden_res = qa_session.get(f"{BASE}/api/auth/users", headers=qa_headers)
    assert forbidden_res.status_code == 403, f"Expected 403 for viewer, got {forbidden_res.status_code}"
    print("[PASS] Viewer is properly blocked (403) from accessing admin user management")

    # 6. Test Admin updating user permissions (promote to 'architect')
    update_res = s.put(f"{BASE}/api/auth/users/{uid}", json={"role": "architect"}, headers=headers)
    assert update_res.status_code == 200, f"Failed to update user role: {update_res.text}"
    updated_user = update_res.json()["user"]
    assert updated_user["role"] == "architect", f"Expected architect, got {updated_user['role']}"
    print(f"[PASS] Admin successfully updated permissions for '{test_user}' to {updated_user['role']}")

    # 7. Test Admin resetting user password
    pwd_res = s.put(f"{BASE}/api/auth/users/{uid}", json={"password": "new_qa_password_456"}, headers=headers)
    assert pwd_res.status_code == 200, f"Failed to reset password: {pwd_res.text}"
    print(f"[PASS] Admin successfully reset password for '{test_user}'")

    # Verify new password works
    new_login = requests.post(f"{BASE}/api/auth/login", json={"username": test_user, "password": "new_qa_password_456"})
    assert new_login.status_code == 200, f"Login failed with new password: {new_login.text}"
    print(f"[PASS] User can log in with newly updated password")

    # 8. Test Admin deleting user
    del_res = s.delete(f"{BASE}/api/auth/users/{uid}", headers=headers)
    assert del_res.status_code == 200, f"Failed to delete user: {del_res.text}"
    print(f"[PASS] Admin successfully deleted user '{test_user}'")

    # 9. Verify Admin cannot delete or demote themselves
    admin_id = user["id"]
    self_demote = s.put(f"{BASE}/api/auth/users/{admin_id}", json={"role": "viewer"}, headers=headers)
    assert self_demote.status_code == 400, f"Expected 400 when admin demotes self, got {self_demote.status_code}"
    print("[PASS] Admin self-demotion prevented (400)")

    self_del = s.delete(f"{BASE}/api/auth/users/{admin_id}", headers=headers)
    assert self_del.status_code == 400, f"Expected 400 when admin deletes self, got {self_del.status_code}"
    print("[PASS] Admin self-deletion prevented (400)")

    print("\nALL AUTHENTICATION & PERMISSION TESTS PASSED!")

if __name__ == "__main__":
    test_auth_workflow()
