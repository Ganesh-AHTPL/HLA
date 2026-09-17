import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app, db, User
from models import Document

from auth import generate_token

class TestRulesCatalogEndpoint(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        app.config["TESTING"] = True

    def test_rules_catalog_fallback_generic(self):
        """When no document is specified, returns generic enterprise catalog."""
        with app.app_context():
            user = User.query.first()
            token = generate_token(user)

        res = self.client.get("/api/rules/catalog", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("rules", data)
        rules = data["rules"]
        self.assertGreaterEqual(len(rules), 1)
        print(f"[PASS] Rules Catalog returned {len(rules)} rules from source '{data.get('source')}'. Document: {data.get('document_name')}")
        for r in rules:
            print(f"  - [{r.get('rule_id')}] {r.get('name')}: {r.get('statement')}")
            self.assertTrue(bool(r.get('name')))

if __name__ == "__main__":
    unittest.main()
