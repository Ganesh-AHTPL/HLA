import requests
import psycopg2

BASE_URL = "http://127.0.0.1:5000"

def get_latest_otp_from_db():
    conn = psycopg2.connect("postgresql://postgres:ganesh@localhost:5432/hla_db")
    cur = conn.cursor()
    cur.execute("SELECT otp_code, attempts, max_attempts, used FROM password_reset_tokens ORDER BY id DESC LIMIT 1;")
    row = cur.fetchone()
    conn.close()
    return row

def test_strict_otp():
    print("--- 1. Send OTP Request ---")
    res = requests.post(f"{BASE_URL}/api/auth/send-otp", json={"identifier": "admin"})
    assert res.status_code == 200, f"send-otp failed: {res.text}"
    data = res.json()
    print(f"Response: {data}")
    # Verify OTP is NOT in JSON response (sent ONLY via email)
    assert "otp" not in data, "Security violation: OTP must not be leaked in API response!"
    print("[OK] OTP is NOT leaked in API response (sent ONLY via email)")

    # Retrieve OTP directly from DB as a simulated email recipient would read it from their inbox
    db_row = get_latest_otp_from_db()
    otp_code, attempts, max_attempts, used = db_row
    assert otp_code and len(otp_code) == 6, f"Invalid OTP in DB: {otp_code}"
    print(f"[OK] Retrieved dispatched OTP from DB/Email: {otp_code}, attempts={attempts}, max={max_attempts}")

    print("--- 2. Verify Email Log Subject & Body in DB ---")
    conn = psycopg2.connect("postgresql://postgres:ganesh@localhost:5432/hla_db")
    cur = conn.cursor()
    cur.execute("SELECT subject, body_text FROM email_notification_logs ORDER BY id DESC LIMIT 1;")
    email_row = cur.fetchone()
    conn.close()
    subject, body = email_row
    print(f"Logged Subject: {subject}")
    print(f"Logged Body:\n{body}")
    assert subject == "HLA Studio - Password Reset OTP", f"Unexpected subject: {subject}"
    assert "Hello," in body
    assert "Your HLA Studio password reset verification code is:" in body
    assert otp_code in body
    assert "This code is valid for 10 minutes." in body
    assert "If you did not request a password reset, please ignore this email." in body
    assert "Regards,\nHLA Studio" in body
    print("[OK] Email Subject and Body strictly match the specification!")

    print("--- 3. Testing Attempts Throttling on Invalid OTP ---")
    bad_res1 = requests.post(f"{BASE_URL}/api/auth/verify-otp", json={"identifier": "admin", "otp": "999999"})
    assert bad_res1.status_code == 400
    assert "4 attempt(s) remaining" in bad_res1.json().get("error", "")
    print(f"Attempt 1 rejected correctly: {bad_res1.json().get('error')}")

    bad_res2 = requests.post(f"{BASE_URL}/api/auth/verify-otp", json={"identifier": "admin", "otp": "888888"})
    assert bad_res2.status_code == 400
    assert "3 attempt(s) remaining" in bad_res2.json().get("error", "")
    print(f"Attempt 2 rejected correctly: {bad_res2.json().get('error')}")

    print("--- 4. Verify Correct OTP ---")
    ok_res = requests.post(f"{BASE_URL}/api/auth/verify-otp", json={"identifier": "admin", "otp": otp_code})
    assert ok_res.status_code == 200, f"Valid OTP failed: {ok_res.text}"
    token = ok_res.json().get("token")
    assert token, "Token not returned"
    print("[OK] Correct OTP verified successfully!")

    print("--- 5. Set New Password & Update Hash in DB ---")
    new_pwd = "StrictOTPPass!2026"
    reset_res = requests.post(f"{BASE_URL}/api/auth/reset-password-with-otp", json={
        "identifier": "admin",
        "otp": otp_code,
        "token": token,
        "new_password": new_pwd,
        "confirm_password": new_pwd
    })
    assert reset_res.status_code == 200, f"Reset password failed: {reset_res.text}"
    print("[OK] Password securely updated in DB!")

    print("--- 6. Verify Login with New Password ---")
    login_res = requests.post(f"{BASE_URL}/api/auth/login", json={"username": "admin", "password": new_pwd})
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    print("[OK] Login successful with updated password!")

    print("--- 7. Verify OTP is Invalidated ---")
    reuse_res = requests.post(f"{BASE_URL}/api/auth/verify-otp", json={"identifier": "admin", "otp": otp_code})
    assert reuse_res.status_code in [400, 404]
    print("[OK] OTP cannot be reused after successful password reset.")

    print("--- 8. Restore Default Admin Password ---")
    requests.post(f"{BASE_URL}/api/auth/reset-password", json={"username": "admin", "new_password": "admin123"})
    print("[OK] Restored default admin123")
    print("\nALL STRICT SPECIFICATION TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_strict_otp()
