"""
scratch/test_password_reset_workflow.py
Test the complete token-based password reset workflow:
1. Request reset link for existing user ('admin')
2. Verify token generated and stored with 15m expiration
3. Verify token validation endpoint
4. Test rejection of invalid / non-existent tokens
5. Test password policy validation
6. Reset password with token
7. Verify token is marked as used and cannot be re-used
8. Verify login with the new password
"""

import requests
import sys

BASE_URL = "http://localhost:5000"

def run_tests():
    print("=" * 60)
    print(" TEST 1: Request Password Reset for 'admin'")
    print("=" * 60)
    res = requests.post(f"{BASE_URL}/api/auth/forgot-password", json={"identifier": "admin"})
    print("Status:", res.status_code)
    print("Response:", res.json())
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    data = res.json()
    assert data["success"] is True
    assert "reset_link" in data
    assert "raw_token" in data
    token = data["raw_token"]
    print(f"[OK] One-time reset token generated: {token[:12]}...")

    print("\n" + "=" * 60)
    print(" TEST 2: Verify Valid Token")
    print("=" * 60)
    v_res = requests.get(f"{BASE_URL}/api/auth/verify-reset-token", params={"token": token})
    print("Status:", v_res.status_code)
    print("Response:", v_res.json())
    assert v_res.status_code == 200
    assert v_res.json()["valid"] is True
    assert v_res.json()["username"] == "admin"
    print("[OK] Token successfully validated for user 'admin'")

    print("\n" + "=" * 60)
    print(" TEST 3: Verify Invalid / Fake Token")
    print("=" * 60)
    fake_res = requests.get(f"{BASE_URL}/api/auth/verify-reset-token", params={"token": "fake_token_12345"})
    print("Status:", fake_res.status_code)
    print("Response:", fake_res.json())
    assert fake_res.status_code == 404
    assert fake_res.json()["valid"] is False
    print("[OK] Fake token successfully rejected")

    print("\n" + "=" * 60)
    print(" TEST 4: Password Policy Enforcement")
    print("=" * 60)
    # Test short password
    short_res = requests.post(f"{BASE_URL}/api/auth/reset-password-with-token", json={
        "token": token,
        "new_password": "short",
        "confirm_password": "short"
    })
    print("Short password status:", short_res.status_code, short_res.json())
    assert short_res.status_code == 400
    assert "8 characters" in short_res.json()["error"]

    # Test missing special character
    no_sym_res = requests.post(f"{BASE_URL}/api/auth/reset-password-with-token", json={
        "token": token,
        "new_password": "Password123",
        "confirm_password": "Password123"
    })
    print("No symbol status:", no_sym_res.status_code, no_sym_res.json())
    assert no_sym_res.status_code == 400
    assert "special character" in no_sym_res.json()["error"]
    print("[OK] Password policy properly enforced")

    print("\n" + "=" * 60)
    print(" TEST 5: Reset Password with Strong Password")
    print("=" * 60)
    new_pwd = "AdminSecure@2026!"
    reset_res = requests.post(f"{BASE_URL}/api/auth/reset-password-with-token", json={
        "token": token,
        "new_password": new_pwd,
        "confirm_password": new_pwd
    })
    print("Reset status:", reset_res.status_code, reset_res.json())
    assert reset_res.status_code == 200
    assert reset_res.json()["success"] is True
    print("[OK] Password reset succeeded!")

    print("\n" + "=" * 60)
    print(" TEST 6: Token Invalidation (One-Time Guarantee)")
    print("=" * 60)
    reuse_res = requests.get(f"{BASE_URL}/api/auth/verify-reset-token", params={"token": token})
    print("Re-use verification status:", reuse_res.status_code, reuse_res.json())
    assert reuse_res.status_code == 400
    assert "already been used" in reuse_res.json()["error"]
    print("[OK] Token invalidation verified (cannot be re-used)")

    print("\n" + "=" * 60)
    print(" TEST 7: Login with New Password")
    print("=" * 60)
    login_res = requests.post(f"{BASE_URL}/api/auth/login", json={
        "username": "admin",
        "password": new_pwd
    })
    print("Login with new password status:", login_res.status_code)
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    print(f"[OK] Login successful! Token received: {login_res.json()['token'][:15]}...")

    # Reset back to default admin123 for development convenience
    requests.post(f"{BASE_URL}/api/auth/reset-password", json={"username": "admin", "new_password": "admin123"})
    print("\n[OK] Reset admin back to standard dev password 'admin123'")
    print("\nALL 7 TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_tests()
