import os
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "http://localhost:5000"
session = requests.Session()

# Dynamically retrieve DB credentials from environment (never hardcode in files)
DB_PWD = os.getenv("PGPASSWORD", "")
if not DB_PWD and "@" in os.getenv("DATABASE_URL", ""):
    try:
        DB_PWD = os.getenv("DATABASE_URL", "").split("://")[1].split("@")[0].split(":")[1]
    except Exception:
        DB_PWD = ""

def run_test():
    print("1. Logging in as architect...")
    login_res = session.post(f"{BASE_URL}/api/auth/login", json={
        "username": "architect",
        "password": "architect123"
    })
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    token = login_res.json()["token"]
    session.headers.update({"Authorization": f"Bearer {token}"})
    print("   [OK] Logged in successfully.")

    print("2. Fetching or creating project...")
    proj_res = session.get(f"{BASE_URL}/api/projects")
    assert proj_res.status_code == 200, f"Fetch projects failed: {proj_res.text}"
    projects = proj_res.json()
    if not projects:
        create_res = session.post(f"{BASE_URL}/api/projects", json={
            "name": "Custom Connection Project",
            "description": "Testing custom connection names"
        })
        assert create_res.status_code == 201, f"Create project failed: {create_res.text}"
        project_id = create_res.json()["project"]["id"]
    else:
        project_id = projects[0]["id"]
    print(f"   [OK] Using project ID: {project_id}")

    print("3. Saving a custom-named connection: 'Billing_Warehouse_DB'...")
    conn_payload = {
        "source_db_name": "Billing_Warehouse_DB",
        "db_type": "postgresql",
        "host": "localhost",
        "port": 5432,
        "database_name": "hla_db",
        "username": "postgres",
        "password": DB_PWD,
        "schema_name": "public",
        "conn_role": "source"
    }
    save_conn_res = session.post(f"{BASE_URL}/api/projects/{project_id}/connections", json=conn_payload)
    assert save_conn_res.status_code == 200, f"Save connection failed: {save_conn_res.text}"
    saved_conn = save_conn_res.json().get("connection") or save_conn_res.json()
    conn_id = saved_conn.get("id")
    print(f"   [OK] Saved connection '{saved_conn.get('source_db_name')}' with ID: {conn_id}")

    print("4. Listing connections to verify custom name persists...")
    list_res = session.get(f"{BASE_URL}/api/projects/{project_id}/connections")
    assert list_res.status_code == 200, f"List failed: {list_res.text}"
    all_conns = list_res.json()
    match = next((c for c in all_conns if c["source_db_name"] == "Billing_Warehouse_DB"), None)
    assert match is not None, "Saved connection 'Billing_Warehouse_DB' not found in listing!"
    print(f"   [OK] Found saved connection: {match['source_db_name']} (role={match.get('conn_role')})")

    print("5. Testing ping to the saved connection...")
    ping_res = session.post(f"{BASE_URL}/api/projects/{project_id}/connections/test", json=conn_payload)
    assert ping_res.status_code == 200, f"Ping failed: {ping_res.text}"
    assert ping_res.json().get("success") is True, f"Ping returned success=False: {ping_res.json()}"
    print(f"   [OK] Ping succeeded: {ping_res.json().get('message')}")

    print("6. Introspecting table using the custom-named connection...")
    introspect_res = session.post(f"{BASE_URL}/api/introspect-table", json={
        "source_db_name": "Billing_Warehouse_DB",
        "schema_name": "public",
        "table_name": "users",
        "connection_config": {
            "use_local": True
        }
    })
    assert introspect_res.status_code == 200, f"Introspect failed: {introspect_res.text}"
    introspect_data = introspect_res.json()
    assert "columns" in introspect_data and len(introspect_data["columns"]) > 0, "No columns returned!"
    print(f"   [OK] Successfully introspected table 'users', found {len(introspect_data['columns'])} columns!")

    print("7. Testing deletion of the custom connection...")
    del_res = session.delete(f"{BASE_URL}/api/projects/{project_id}/connections/{conn_id}")
    assert del_res.status_code == 200, f"Delete failed: {del_res.text}"
    print("   [OK] Connection successfully deleted.")

    print("\nALL CUSTOM CONNECTION NAMING TESTS PASSED!")

if __name__ == "__main__":
    run_test()
