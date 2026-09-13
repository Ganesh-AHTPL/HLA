import requests
import json

base_url = "http://localhost:5000"

# 1. Test Login
print("1. Testing Login...")
try:
    login_res = requests.post(f"{base_url}/api/auth/login", json={"username": "admin", "password": "admin123"})
    print("Login status:", login_res.status_code, login_res.json() if login_res.status_code == 200 else login_res.text)
    token = login_res.json().get("token") if login_res.status_code == 200 else None
except Exception as e:
    print("Login exception:", e)
    token = None

if token:
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Test Projects
    print("\n2. Testing Projects...")
    p_res = requests.get(f"{base_url}/api/projects", headers=headers)
    print("Projects status:", p_res.status_code, "Count:", len(p_res.json()) if p_res.status_code == 200 else p_res.text)

    # 3. Test Documents
    print("\n3. Testing Documents...")
    d_res = requests.get(f"{base_url}/api/documents", headers=headers)
    print("Documents status:", d_res.status_code, "Count:", len(d_res.json()) if d_res.status_code == 200 else d_res.text)
    docs = d_res.json() if d_res.status_code == 200 else []

    # 4. Test Rules Catalog
    print("\n4. Testing Rules Catalog...")
    r_res = requests.get(f"{base_url}/api/rules/catalog", headers=headers)
    print("Rules Catalog status:", r_res.status_code, "Rules count:", len(r_res.json().get("rules", [])) if r_res.status_code == 200 else r_res.text)

    # 5. If docs exist, test build-target-logic
    if docs:
        doc_id = docs[0]["id"]
        print(f"\n5. Testing build-target-logic on doc #{doc_id}...")
        bt_res = requests.post(
            f"{base_url}/api/documents/{doc_id}/build-target-logic",
            headers=headers,
            json={"target_env": "dev", "target_config": {"db_type": "sandbox", "schema_name": "target_dev"}}
        )
        print("Build target status:", bt_res.status_code)
        if bt_res.status_code != 200:
            print("Build target error:", bt_res.text)
        else:
            print("Build target success! DDL length:", len(bt_res.json().get("ddl", "")))
