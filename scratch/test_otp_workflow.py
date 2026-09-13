import requests

BASE_URL = "http://127.0.0.1:5000"

def test_otp_flow():
    print("1. Requesting OTP for user 'admin'...")
    res = requests.post(f"{BASE_URL}/api/auth/send-otp", json={"identifier": "admin"})
    print(f"Status: {res.status_code}, Response: {res.json()}")
    assert res.status_code == 200, "Send OTP failed"
    data = res.json()
    otp = data.get("otp")
    raw_token = data.get("raw_token")
    assert otp and len(otp) == 6, f"Invalid OTP: {otp}"
    print(f"-> Generated OTP: {otp}")

    print("2. Testing invalid OTP...")
    bad_res = requests.post(f"{BASE_URL}/api/auth/verify-otp", json={"otp": "000000"})
    print(f"Status: {bad_res.status_code}, Response: {bad_res.json()}")
    assert bad_res.status_code == 400, "Should reject invalid OTP"

    print("3. Testing valid OTP verification...")
    v_res = requests.post(f"{BASE_URL}/api/auth/verify-otp", json={"otp": otp, "identifier": "admin"})
    print(f"Status: {v_res.status_code}, Response: {v_res.json()}")
    assert v_res.status_code == 200, "Valid OTP verification failed"
    assert v_res.json().get("valid") is True

    print("4. Testing password reset with OTP...")
    reset_res = requests.post(f"{BASE_URL}/api/auth/reset-password-with-otp", json={
        "identifier": "admin",
        "otp": otp,
        "new_password": "NewAdminPassword!2026",
        "confirm_password": "NewAdminPassword!2026"
    })
    print(f"Status: {reset_res.status_code}, Response: {reset_res.json()}")
    assert reset_res.status_code == 200, "Reset password with OTP failed"

    print("5. Verifying login with new password...")
    login_res = requests.post(f"{BASE_URL}/api/auth/login", json={
        "username": "admin",
        "password": "NewAdminPassword!2026"
    })
    print(f"Status: {login_res.status_code}, Response: {login_res.json()}")
    assert login_res.status_code == 200, "Login with new password failed"

    print("6. Verifying OTP cannot be reused...")
    reuse_res = requests.post(f"{BASE_URL}/api/auth/verify-otp", json={"otp": otp})
    print(f"Status: {reuse_res.status_code}, Response: {reuse_res.json()}")
    assert reuse_res.status_code == 400, "OTP should not be reusable"

    print("7. Restoring default admin password for dev convenience...")
    restore_res = requests.post(f"{BASE_URL}/api/auth/reset-password", json={
        "username": "admin",
        "new_password": "admin123"
    })
    assert restore_res.status_code == 200
    print("-> Admin password restored to admin123")
    print("\nALL OTP BACKEND TESTS PASSED!")

if __name__ == "__main__":
    test_otp_flow()
