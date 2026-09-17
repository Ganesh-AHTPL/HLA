import sys
sys.path.insert(0, '.')
import requests
import json

BASE_URL = "http://localhost:5000"

# 1. Login as Admin
login_res = requests.post(f"{BASE_URL}/api/auth/login", json={"username": "admin", "password": "admin123"})
assert login_res.status_code == 200, f"Login failed: {login_res.text}"
token = login_res.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}
print("[OK] Admin authenticated successfully.")

# 2. Scan Source Database for Doc 79
scan_res = requests.post(f"{BASE_URL}/api/documents/79/scan-source-db", headers=headers)
assert scan_res.status_code == 200, f"Scan failed: {scan_res.text}"
scan_data = scan_res.json()
print(f"[OK] Source DB Scan completed: {scan_data['tables_found_count']} found, {scan_data['tables_missing_count']} missing.")
print("     Configured DBs:", scan_data.get("configured_databases"))
missing_tables = [t['table_name'] for t in scan_data.get('table_audit', []) if not t['table_found']]
print("     Missing Source Tables:", missing_tables)
assert scan_data["tables_missing_count"] == 6

# 3. Dry-Run Validation Attempt on Doc 79 MUST be Blocked (HTTP 400)
dry_res = requests.post(f"{BASE_URL}/api/documents/79/deploy-target", json={"environment": "dev", "action": "validate"}, headers=headers)
print(f"[OK] Dry-Run Validation status code: {dry_res.status_code}")
assert dry_res.status_code == 400, f"Expected 400 blocked, got {dry_res.status_code}"
dry_data = dry_res.json()
assert dry_data.get("blocked") is True
print("     Dry-Run blocked response message:", dry_data.get("message"))

# 4. Live Deployment Attempt on Doc 79 MUST be Blocked (HTTP 400)
deploy_res = requests.post(f"{BASE_URL}/api/documents/79/deploy-target", json={"environment": "dev", "action": "deploy"}, headers=headers)
print(f"[OK] Live Deployment status code: {deploy_res.status_code}")
assert deploy_res.status_code == 400, f"Expected 400 blocked, got {deploy_res.status_code}"
deploy_data = deploy_res.json()
assert deploy_data.get("blocked") is True
print("     Deployment blocked response message:", deploy_data.get("message"))

# 5. Verify Target Transformation SQL for Doc 79
art_res = requests.get(f"{BASE_URL}/api/documents/79/target-artifacts", headers=headers)
assert art_res.status_code == 200
artifacts = art_res.json()
dev_art = next((a for a in artifacts if a["environment"] == "dev"), None)
assert dev_art is not None
sql = dev_art.get("generated_transformation_sql", "")

# Verify no character-by-character vertical text
assert "\nS\nE\nL\nE\nC\nT\n" not in sql, "Vertical single-character corruption found!"
print("[OK] Verified NO single-character vertical text in generated transformation SQL.")

# Verify no fake b.source_stream mapping
assert "b.source_stream AS application_name" not in sql, "Fake b.source_stream mapping found!"
assert "b.source_stream AS cmdb_production_ip" not in sql, "Fake b.source_stream mapping found!"
assert "b.source_stream AS sfdc_mrc" not in sql, "Fake b.source_stream mapping found!"
assert "UNRESOLVED MAPPING" in sql, "Explicit unresolved markers missing from target report SQL!"
print("[OK] Verified unmapped columns are explicitly flagged as UNRESOLVED MAPPING (no fake b.source_stream).")

print("\n=== ALL QUALITY GATE & VALIDATION CHECKS PASSED ===")
