import os
import requests

def test_full_api_flow():
    base = "http://127.0.0.1:5000"

    # 1. Login as admin
    s = requests.Session()
    login_res = s.post(f"{base}/api/auth/login", json={"username": "admin", "password": "admin123"})
    print("1. Login status:", login_res.status_code)
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    token = login_res.json().get("token")
    s.headers.update({"Authorization": f"Bearer {token}"})

    # 2. Create Project
    print("\n2. Creating new project...")
    p_res = s.post(f"{base}/api/projects", json={
        "name": "Control-23 Enterprise Architecture",
        "description": "Multi-Source to Single Dynamic Target Schema Pipeline"
    })
    assert p_res.status_code == 201, f"Create project failed: {p_res.text}"
    project = p_res.json().get("project", {})
    p_id = project["id"]
    print(f"   [OK] Project created: ID {p_id} ('{project.get('name')}')")

    # 3. Upload & Analyze HLA Document
    hla_path = r"C:\Users\Hp\Downloads\HLA_Solution_Design_Template.docx"
    assert os.path.exists(hla_path), f"File not found: {hla_path}"
    print(f"\n3. Uploading HLA Document: {hla_path}")
    with open(hla_path, "rb") as f:
        up_res = s.post(f"{base}/api/upload", files={"file": f}, data={"project_id": p_id})
    assert up_res.status_code == 200, f"Upload failed: {up_res.text}"
    upload_data = up_res.json()
    doc_id = upload_data["id"]
    print(f"   [OK] Document uploaded: ID {doc_id} ('{upload_data.get('filename')}')")

    # Document auto-analyzed upon upload
    analysis = upload_data.get("analysis", {})
    co = analysis.get("control_overview", {})
    print(f"   [OK] Analysis extracted from upload:")
    print(f"        - Control: {co.get('identification', {}).get('control_number')}")
    print(f"        - Digits:  {co.get('control_digits')}")
    print(f"        - Target Schema: {co.get('target_schema')}")
    assert co.get("target_schema") == "ra_ctrl.ctrl_23", f"Expected ra_ctrl.ctrl_23, got {co.get('target_schema')}"

    # 4. Check targets config endpoint
    print("\n4. Checking Target DB Configs via API:")
    t_res = s.get(f"{base}/api/projects/{p_id}/targets")
    assert t_res.status_code == 200
    targets = t_res.json()
    print("   - Dev target schema:", targets["dev"].get("schema_name"))
    print("   - Prod target schema:", targets["prod"].get("schema_name"))
    assert targets["dev"].get("schema_name") == "ra_ctrl.ctrl_23", f"Expected ra_ctrl.ctrl_23, got {targets['dev'].get('schema_name')}"

    # 5. Build Target Logic via API
    print("\n5. Calling Build Target Logic endpoint:")
    build_res = s.post(f"{base}/api/documents/{doc_id}/build-target-logic", json={
        "environment": "dev",
        "target_config": {}
    })
    assert build_res.status_code == 200, f"Build target logic failed: {build_res.text}"
    data = build_res.json()
    artifact = data.get("artifact", {})
    art_schema = artifact.get("target_schema")
    print(f"   [OK] Target logic built successfully!")
    print(f"        - Artifact Target Schema: {art_schema}")
    assert art_schema == "ra_ctrl.ctrl_23", f"Expected ra_ctrl.ctrl_23, got {art_schema}"

    # Check generated DDL
    ddl = artifact.get("generated_ddl", "")
    assert 'CREATE SCHEMA IF NOT EXISTS "ra_ctrl.ctrl_23";' in ddl
    assert '"ra_ctrl.ctrl_23".' in ddl
    print("   [OK] Verified DDL contains quoted schema 'ra_ctrl.ctrl_23' and tables")

    # 6. Deploy / Validate Live against Target Database
    print("\n6. Validating Target DDL against PostgreSQL:")
    deploy_res = s.post(f"{base}/api/documents/{doc_id}/deploy-target", json={
        "environment": "dev",
        "action": "validate"
    })
    assert deploy_res.status_code == 200, f"Validate DDL failed: {deploy_res.text}"
    val_data = deploy_res.json()
    print(f"   - Validation success: {val_data.get('success')}")
    print(f"   - Message: {val_data.get('message')}")
    assert val_data.get("success") is True, f"Validation failed: {val_data.get('message')}"

    print("\n================================================================================")
    print("END-TO-END API PIPELINE VERIFICATION PASSED 100%!")
    print("================================================================================")

if __name__ == "__main__":
    test_full_api_flow()
