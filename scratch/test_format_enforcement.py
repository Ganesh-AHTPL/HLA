import sys
import os
import io
import requests

BASE = "http://localhost:5000"

def test_format_enforcement():
    s = requests.Session()
    login_res = s.post(f"{BASE}/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    token = login_res.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("[1/4] Admin login successful.")

    # Test 1: Reject DOCX
    fake_docx = io.BytesIO(b"fake docx binary content")
    res_docx = s.post(f"{BASE}/api/projects/22/upload", files={"file": ("fake_spec.docx", fake_docx, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}, headers=headers)
    print(f"[2/4] DOCX upload response status: {res_docx.status_code}, error: {res_docx.json().get('error')}")
    assert res_docx.status_code == 422, "DOCX upload should be rejected with 422"
    assert "Only Excel files (.xlsx, .xls)" in res_docx.json().get("error", "")

    # Test 2: Reject PDF
    fake_pdf = io.BytesIO(b"%PDF-1.4 fake pdf")
    res_pdf = s.post(f"{BASE}/api/projects/22/upload", files={"file": ("architecture_doc.pdf", fake_pdf, "application/pdf")}, headers=headers)
    print(f"[3/4] PDF upload response status: {res_pdf.status_code}, error: {res_pdf.json().get('error')}")
    assert res_pdf.status_code == 422, "PDF upload should be rejected with 422"
    assert "Only Excel files (.xlsx, .xls)" in res_pdf.json().get("error", "")

    # Test 3: Upload actual Control23_Source_Logic.xlsx
    xlsx_path = r"C:\Users\Hp\Downloads\Control23_Source_Logic.xlsx"
    assert os.path.exists(xlsx_path), f"File not found: {xlsx_path}"
    with open(xlsx_path, "rb") as f:
        res_xlsx = s.post(f"{BASE}/api/projects/22/upload", files={"file": ("Control23_Source_Logic.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}, headers=headers)
    
    print(f"[4/4] XLSX upload response status: {res_xlsx.status_code}")
    assert res_xlsx.status_code == 200, f"XLSX upload failed: {res_xlsx.text}"
    data = res_xlsx.json()
    print(f"      Document #{data.get('id')} uploaded successfully!")
    ana = data.get("analysis", {})
    sources = ana.get("sources", [])
    rules = ana.get("rules", {}).get("filter_rules", [])
    buckets = ana.get("buckets", [])
    data_model = ana.get("data_model", [])
    print(f"      Extracted: {len(sources)} Sources, {len(rules)} Filter Rules, {len(buckets)} Buckets, {len(data_model)} Data Model Entities")
    assert len(sources) > 0, "Should have extracted sources"
    assert len(rules) > 0, "Should have extracted rules"
    print("\n>>> ALL FORMAT ENFORCEMENT & SCAN TESTS PASSED SUCCESSFULLY! <<<")

if __name__ == "__main__":
    test_format_enforcement()
