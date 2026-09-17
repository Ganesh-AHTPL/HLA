import requests

BASE_URL = "http://localhost:5000"

# 1. Login
login_res = requests.post(f"{BASE_URL}/api/auth/login", json={"username": "admin", "password": "admin123"})
assert login_res.status_code == 200, f"Login failed: {login_res.text}"
token = login_res.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}
print("[OK] Authenticated as Admin.")

# 2. Trigger Document 79 Analysis
ana_res = requests.post(f"{BASE_URL}/api/documents/79/analyze", headers=headers)
assert ana_res.status_code == 200, f"Analysis failed: {ana_res.text}"
ana_data = ana_res.json()
print("[OK] Analysis triggered for Document 79.")
hla_summary = ana_data["analysis"]["hla_analysis_summary"]
print("     Sheets scanned:", hla_summary["scan_status"])
print("     Total rows scanned:", hla_summary["total_rows_scanned"])
print("     Total populated cells:", hla_summary["total_populated_cells"])
print("     Entities discovered:", hla_summary["entities_discovered"])

# 3. Generate Target Artifacts via build-target-logic
art_res = requests.post(f"{BASE_URL}/api/documents/79/build-target-logic", json={"environment": "dev"}, headers=headers)
assert art_res.status_code == 200, f"Artifacts generation failed: {art_res.text}"
art_data = art_res.json()
artifact_obj = art_data.get("artifact") or {}
print(f"[OK] Target artifacts generated. Artifact ID: {artifact_obj.get('id')}")
sql = artifact_obj.get("generated_transformation_sql", "")
assert "HLA ANALYSIS SUMMARY" in sql, "HLA ANALYSIS SUMMARY missing from generated SQL!"
assert "TARGET COLUMN VALIDATION REPORT" in sql, "TARGET COLUMN VALIDATION REPORT missing from generated SQL!"
assert "b.source_stream AS application_name" not in sql, "Fake b.source_stream mapping found!"
assert "UNRESOLVED HLA DEPENDENCY" in sql, "UNRESOLVED markers missing from generated SQL!"
print("[OK] Verified generated SQL contains authoritative HLA Analysis Summary, Target Validation Report, and zero fake source_stream mappings.")

# 4. Dry-Run Validation (Must be blocked with HTTP 400 because source tables are missing in PostgreSQL)
dry_res = requests.post(f"{BASE_URL}/api/documents/79/deploy-target", json={"environment": "dev", "action": "validate"}, headers=headers)
assert dry_res.status_code == 400, f"Expected 400 blocked, got {dry_res.status_code}"
dry_data = dry_res.json()
assert dry_data.get("blocked") is True
print("[OK] Dry-run correctly blocked by Quality Gate. Message:", dry_data.get("message"))

# 5. Live Deployment (Must be blocked with HTTP 400 because source tables are missing in PostgreSQL)
deploy_res = requests.post(f"{BASE_URL}/api/documents/79/deploy-target", json={"environment": "dev", "action": "deploy"}, headers=headers)
assert deploy_res.status_code == 400, f"Expected 400 blocked, got {deploy_res.status_code}"
deploy_data = deploy_res.json()
assert deploy_data.get("blocked") is True
print("[OK] Live deployment correctly blocked by Quality Gate. Message:", deploy_data.get("message"))

print("\n=== ALL BACKEND VALIDATION TESTS PASSED ===")
