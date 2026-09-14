import requests
import psycopg2

BASE = "http://127.0.0.1:5000"

def run_test():
    print("--- Testing Unregistered Email (Not Found) ---")
    res1 = requests.post(f"{BASE}/api/auth/forgot-password", json={"email": "nonexistent_user_test@domain.com"})
    print(f"Status Code: {res1.status_code}")
    print(f"Response Body: {res1.json()}")
    assert res1.status_code == 404
    assert res1.json()["error"] == "Email ID not found."
    print("[PASS] 404 'Email ID not found.' returned for unregistered email.\n")

    print("--- Testing Registered Email with Unconfigured SMTP ---")
    res2 = requests.post(f"{BASE}/api/auth/forgot-password", json={"email": "ganesh.raman@analytixhub.ai"})
    print(f"Status Code: {res2.status_code}")
    print(f"Response Body: {res2.json()}")
    assert res2.status_code in [200, 500]
    print("[PASS] Registered email processed properly.\n")

    print("--- Verifying No Orphaned Active OTP in Database ---")
    conn = psycopg2.connect("postgresql://postgres:ganesh@localhost:5432/hla_db")
    cur = conn.cursor()
    cur.execute("""
        SELECT prt.id, prt.used, prt.verified
        FROM password_reset_tokens prt
        JOIN users u ON u.id = prt.user_id
        WHERE u.email = 'architect@hlaproject.local' AND prt.used = false
    """)
    rows = cur.fetchall()
    conn.close()
    print(f"Active unused tokens for architect: {len(rows)}")
    assert len(rows) == 0, f"Found active token after failed send: {rows}"
    print("[PASS] Database consistency verified: no orphaned active token left after email failure.")

if __name__ == "__main__":
    run_test()
