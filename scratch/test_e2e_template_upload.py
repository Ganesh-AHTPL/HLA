"""
End-to-End Test for Standard HLA Solution Design Template Upload & Analysis
"""
import requests
import json

BASE_URL = "http://localhost:5000"
TEMPLATE_PATH = r"C:\Users\Hp\Downloads\HLA_Solution_Design_Template.docx"

def test_template_upload():
    session = requests.Session()

    # 1. Login
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
        create_res = session.post(f"{BASE_URL}/api/projects", json={"name": "HLA Template Test Project"})
        assert create_res.status_code == 201
        project_id = create_res.json()["project"]["id"]
    print(f"[OK] Using Project ID: {project_id}")

    # 3. Upload Document
    with open(TEMPLATE_PATH, "rb") as f:
        files = {"file": ("HLA_Solution_Design_Template.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        upload_res = session.post(f"{BASE_URL}/api/projects/{project_id}/upload", files=files)
    
    assert upload_res.status_code == 200, f"Upload failed: {upload_res.text}"
    doc_data = upload_res.json()
    doc_id = doc_data["id"]
    analysis = doc_data.get("analysis") or {}
    print(f"[OK] Document uploaded successfully. ID: {doc_id}")

    # 4. Verify Template Conformance & Extracted Tables
    compliance = analysis.get("template_compliance") or {}
    print(f"[OK] Compliance Score: {compliance.get('compliance_score')}% (Compliant: {compliance.get('is_compliant')})")
    assert compliance.get("is_compliant") is True, f"Expected compliant template, got: {compliance}"
    assert compliance.get("compliance_score") == 100, f"Expected 100% compliance, got: {compliance.get('compliance_score')}"

    sources = analysis.get("sources") or []
    filter_rules = analysis.get("rules", {}).get("filter_rules") or []
    mappings = analysis.get("mappings") or []
    config_tables = analysis.get("config_tables") or []
    report_inventory = analysis.get("report_inventory") or []

    print(f"[OK] Sources extracted: {len(sources)}")
    print(f"[OK] Filter Rules extracted: {len(filter_rules)}")
    print(f"[OK] Mappings extracted: {len(mappings)}")
    print(f"[OK] Config Tables extracted: {len(config_tables)}")
    print(f"[OK] Report Inventory extracted: {len(report_inventory)}")

    assert len(sources) > 0, "No sources extracted!"
    assert len(filter_rules) > 0, "No filter rules extracted!"
    assert len(mappings) > 0, "No mappings extracted!"
    assert len(config_tables) > 0, "No config tables extracted!"
    assert len(report_inventory) > 0, "No report inventory extracted!"

    # 5. Test Download of Generated Specification
    dl_res = session.get(f"{BASE_URL}/api/documents/{doc_id}/download-generated")
    assert dl_res.status_code == 200, f"Download spec failed: {dl_res.status_code}"
    assert len(dl_res.content) > 1000, "Generated spec file is empty or corrupted"
    print(f"[OK] Downloaded generated specification document: {len(dl_res.content)} bytes")

    print("\nALL 13-TABLE TEMPLATE EXTRACTION & CONFORMANCE CHECKS PASSED!")

if __name__ == "__main__":
    test_template_upload()
