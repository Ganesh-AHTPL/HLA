import sys, os
sys.path.insert(0, os.path.abspath('.'))

from app import app, db
from models import Document, User
import json

with app.app_context():
    client = app.test_client()
    user = User.query.filter_by(role="admin").first()
    
    # Authenticate admin session or generate auth token
    from auth import generate_tokens
    tokens = generate_tokens(user)
    token = tokens["access_token"]
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # Post deployment request to endpoint
    payload = {
        "environment": "dev",
        "action": "deploy",
        "schema_name": "Unique"
    }
    res = client.post("/api/documents/198/deploy-target", data=json.dumps(payload), headers=headers)
    print("Endpoint Status Code:", res.status_code)
    data = res.get_json()
    print("Success:", data.get("success"))
    print("Message:", data.get("message"))
    print("Target Row Counts:", data.get("target_row_counts"))
    print("Stages:")
    for s in data.get("stages", []):
        print(f"  {s.get('status').upper()}: {s.get('label')}")
    
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    assert data.get("success") is True, f"Deployment failed: {data.get('message')}"
    print("\n[SUCCESS] Deployment endpoint test completed cleanly with full row counts!")
