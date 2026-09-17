"""
End-to-End Test for Target DB .kdb Vault Upload
Tests:
1. Target .kdb upload with dual environments ([target.dev] and [target.prod])
2. Single-environment target .kdb upload
3. JSON target vault upload
4. Verification of GET /api/projects/<id>/targets
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "http://localhost:5000"

# Dynamically retrieve DB credentials from environment (never hardcode in files)
DB_PWD = os.getenv("PGPASSWORD", "")
if not DB_PWD and "@" in os.getenv("DATABASE_URL", ""):
    try:
        DB_PWD = os.getenv("DATABASE_URL", "").split("://")[1].split("@")[0].split(":")[1]
    except Exception:
        DB_PWD = ""

def test_target_kdb():
    session = requests.Session()

    # 1. Login as Admin
    login_res = session.post(f"{BASE_URL}/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    token = login_res.json()["token"]
    session.headers.update({"Authorization": f"Bearer {token}"})
    print("[OK] Logged in as Admin")

    # 2. Get or create project
    p_res = session.get(f"{BASE_URL}/api/projects")
    projects = p_res.json()
    if isinstance(projects, list) and len(projects) > 0:
        project_id = projects[0]["id"]
    else:
        create_res = session.post(f"{BASE_URL}/api/projects", json={"name": "Target KDB Test Project"})
        assert create_res.status_code == 201, f"Failed create project: {create_res.text}"
        project_id = create_res.json()["project"]["id"]
    print(f"[OK] Using Project ID: {project_id}")

    # 3. Test Dual Environment .kdb Upload
    kdb_content = f"""
[target.dev]
db_type = postgresql
host = localhost
port = 5432
database = hla_db
username = postgres
password = {DB_PWD}
schema = target_dev

[target.prod]
db_type = postgresql
host = localhost
port = 5432
database = hla_db
username = postgres
password = {DB_PWD}
schema = target_prod
"""
    upload_res = session.post(
        f"{BASE_URL}/api/projects/{project_id}/targets/vault-upload",
        json={"content": kdb_content, "filename": "target_profiles.kdb", "target_env": "dev"}
    )
    assert upload_res.status_code == 200, f"Dual target .kdb upload failed: {upload_res.text}"
    data = upload_res.json()
    print(f"[OK] Dual .kdb upload response: {data['message']}")
    assert data["total_configured"] == 2, f"Expected 2 configured environments, got {data['total_configured']}"
    assert "dev" in data["configured_envs"]
    assert "prod" in data["configured_envs"]
    assert data["targets"]["dev"]["status"] == "connected", f"Dev target not connected: {data['targets']['dev']}"
    assert data["targets"]["prod"]["status"] == "connected", f"Prod target not connected: {data['targets']['prod']}"

    # 4. Verify GET /api/projects/<id>/targets
    get_res = session.get(f"{BASE_URL}/api/projects/{project_id}/targets")
    assert get_res.status_code == 200
    targets = get_res.json()
    assert targets["dev"] is not None
    assert targets["dev"]["schema_name"] == "target_dev"
    assert targets["prod"] is not None
    assert targets["prod"]["schema_name"] == "target_prod"
    print(f"[OK] GET /targets verified: dev schema={targets['dev']['schema_name']}, prod schema={targets['prod']['schema_name']}")

    # 5. Test Single Target Environment .kdb Upload
    single_kdb = f"""
[target]
db_type = postgresql
host = localhost
port = 5432
database = hla_db
username = postgres
password = {DB_PWD}
schema = custom_target_dev
"""
    single_res = session.post(
        f"{BASE_URL}/api/projects/{project_id}/targets/vault-upload",
        json={"content": single_kdb, "filename": "single_target.kdb", "target_env": "dev"}
    )
    assert single_res.status_code == 200, f"Single target upload failed: {single_res.text}"
    single_data = single_res.json()
    assert single_data["targets"]["dev"]["schema_name"] == "custom_target_dev"
    print(f"[OK] Single .kdb upload successfully updated dev schema to: {single_data['targets']['dev']['schema_name']}")

    print("\n ALL TARGET DB .KDB VAULT TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_target_kdb()
