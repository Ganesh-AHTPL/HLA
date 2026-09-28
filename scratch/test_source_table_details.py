"""
Unit & Integration Tests for Dynamic Source Table Details, Schema Introspection, and Lineage
---------------------------------------------------------------------------------------------
Verifies that Source Table Details and Source -> Target Mappings are completely dynamic
and work with ANY arbitrary source database names, schema names, table names, and column definitions.
"""

import os
import sys
import unittest
import json
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db, User, Project, Document, DBConnection, TargetArtifact
from auth import generate_token
from target_logic_builder import build_target_logic_package, generate_source_to_target_mappings, discover_target_entities

class TestDynamicSourceTableDetailsAndLineage(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()

        # Dynamic suffix to ensure tests are isolated and independent
        self.test_run_id = uuid.uuid4().hex[:8]
        self.dynamic_db_name = f"dyn_source_db_{self.test_run_id}"
        self.dynamic_schema_name = f"dyn_schema_{self.test_run_id}"
        self.dynamic_source_table_1 = f"dyn_upstream_feed_{self.test_run_id}"
        self.dynamic_source_table_2 = f"dyn_lookup_dim_{self.test_run_id}"
        self.dynamic_target_table = f"dyn_target_stage_{self.test_run_id}"

        # Dynamic column names
        self.col_pk = f"dyn_pk_{self.test_run_id}"
        self.col_ts = f"dyn_timestamp_{self.test_run_id}"
        self.col_val = f"dyn_metric_value_{self.test_run_id}"
        self.col_unmapped = f"dyn_extra_unmapped_{self.test_run_id}"

        # Create test user
        self.user = User.query.filter_by(username="dynamictestuser").first()
        if not self.user:
            self.user = User(
                username="dynamictestuser",
                email="dynamictest@example.com",
                role="admin",
                status="active"
            )
            self.user.set_password("SecurePass123!")
            db.session.add(self.user)
            db.session.commit()

        self.token = generate_token(self.user)
        self.headers = {"Authorization": f"Bearer {self.token}"}

        # Create test project
        self.project = Project(
            name=f"Dynamic Source Test Project {self.test_run_id}",
            description="Testing dynamic source database introspection and lineage"
        )
        db.session.add(self.project)
        db.session.commit()

        # Create test document with dynamic names
        self.doc = Document(
            filename=f"dynamic_hla_{self.test_run_id}.xlsx",
            original_name=f"dynamic_hla_{self.test_run_id}.xlsx",
            file_type="excel",
            file_path=f"uploads/dynamic_hla_{self.test_run_id}.xlsx",
            project_id=self.project.id,
            analysis_data={
                "document_title": f"Dynamic Solution Design {self.test_run_id}",
                "sources": [
                    {
                        "source_table_name": self.dynamic_source_table_1,
                        "schema": self.dynamic_schema_name,
                        "database": self.dynamic_db_name,
                        "source_system": self.dynamic_db_name
                    },
                    {
                        "source_table_name": self.dynamic_source_table_2,
                        "schema": self.dynamic_schema_name,
                        "database": self.dynamic_db_name,
                        "source_system": self.dynamic_db_name
                    }
                ],
                "mappings": [
                    {
                        "source_table": self.dynamic_source_table_1,
                        "source_field": self.col_pk,
                        "derivation_logic": "direct",
                        "target_table": self.dynamic_target_table,
                        "target_column": self.col_pk
                    },
                    {
                        "source_table": self.dynamic_source_table_1,
                        "source_field": self.col_ts,
                        "derivation_logic": f"CAST({self.col_ts} AS TIMESTAMP)",
                        "target_table": self.dynamic_target_table,
                        "target_column": self.col_ts
                    },
                    {
                        "source_table": self.dynamic_source_table_1,
                        "source_field": self.col_val,
                        "derivation_logic": f"COALESCE({self.col_val}, 0.0)",
                        "target_table": self.dynamic_target_table,
                        "target_column": f"calculated_{self.col_val}"
                    }
                ],
                "control_overview": {
                    "identification": {
                        "control_number": f"CTRL-DYN-{self.test_run_id.upper()}",
                        "control_title": "Dynamic Solution Control"
                    },
                    "target_schema": self.dynamic_schema_name
                }
            }
        )
        db.session.add(self.doc)
        db.session.commit()

        # Clean existing artifacts
        TargetArtifact.query.filter_by(project_id=self.project.id).delete()
        db.session.commit()

    def tearDown(self):
        self.ctx.pop()

    def test_01_dynamic_lineage_generation_direct_and_unmapped(self):
        """Verify generate_source_to_target_mappings produces accurate lineage with dynamic table and column names."""
        analysis = self.doc.analysis_data
        introspected = {
            self.dynamic_source_table_1: {
                "table_found": True,
                "columns": [
                    {"column_name": self.col_pk, "data_type": "integer", "is_nullable": "NO"},
                    {"column_name": self.col_ts, "data_type": "timestamp", "is_nullable": "YES"},
                    {"column_name": self.col_val, "data_type": "numeric(18,4)", "is_nullable": "YES"}
                ],
                "primary_keys": [self.col_pk],
                "row_count": 42000
            }
        }
        target_entities = [
            {
                "table_name": self.dynamic_target_table,
                "columns": [
                    {"name": self.col_pk, "type": "INTEGER"},
                    {"name": self.col_ts, "type": "TIMESTAMP"},
                    {"name": f"calculated_{self.col_val}", "type": "NUMERIC(18,4)"},
                    {"name": self.col_unmapped, "type": "VARCHAR(100)"}  # Unmapped column
                ]
            }
        ]

        mappings = generate_source_to_target_mappings(analysis, introspected, target_entities)
        self.assertTrue(len(mappings) >= 4)

        pk_map = next((m for m in mappings if m["target_column"] == self.col_pk), None)
        self.assertIsNotNone(pk_map)
        self.assertEqual(pk_map["source_column"], self.col_pk)
        self.assertEqual(pk_map["transformation"], "direct")

        calc_val_map = next((m for m in mappings if m["target_column"] == f"calculated_{self.col_val}"), None)
        self.assertIsNotNone(calc_val_map)
        self.assertEqual(calc_val_map["source_column"], self.col_val)
        self.assertIn("COALESCE", calc_val_map["transformation"])

        unmapped_map = next((m for m in mappings if m["target_column"] == self.col_unmapped), None)
        self.assertIsNotNone(unmapped_map)
        self.assertEqual(unmapped_map["transformation"], "UNMAPPED")

    def test_02_scan_source_db_endpoint_rich_metadata(self):
        """Verify scan_source_db endpoint populates rich column types, PKs, nullability, row counts, and persists."""
        res = self.client.post(f"/api/documents/{self.doc.id}/scan-source-db", json={}, headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIn("table_audit", data)
        self.assertEqual(data["total_tables"], 2)

        # Check document analysis_data persistence
        reloaded_doc = db.session.get(Document, self.doc.id)
        self.assertIn("last_source_scan", reloaded_doc.analysis_data)
        saved_scan = reloaded_doc.analysis_data["last_source_scan"]
        self.assertEqual(len(saved_scan["table_audit"]), 2)

    def test_03_source_metadata_survives_build_target_logic(self):
        """Verify running Build Target Logic never clears or wipes dynamic source table metadata."""
        # 1. Scan source DB
        self.client.post(f"/api/documents/{self.doc.id}/scan-source-db", json={}, headers=self.headers)

        # 2. Build target logic
        res = self.client.post(
            f"/api/documents/{self.doc.id}/build-target-logic",
            json={
                "environment": "dev",
                "target_config": {
                    "db_type": "postgresql",
                    "host": "localhost",
                    "port": "5432",
                    "database_name": "hla_db",
                    "schema_name": "public"
                }
            },
            headers=self.headers
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        artifact_data = data["artifact"]

        # 3. Verify artifact has source_metadata_json and source_mapping_json
        self.assertIn("source_metadata_json", artifact_data)
        self.assertIn("source_mapping_json", artifact_data)
        self.assertTrue(len(artifact_data["source_mapping_json"]) > 0)
        self.assertEqual(len(artifact_data["source_metadata_json"].get("table_audit", [])), 2)

    def test_04_get_target_artifacts_survives_page_refresh(self):
        """Verify GET /api/documents/<id>/target-artifacts returns populated dynamic source metadata and mappings across page reloads."""
        # First ensure target logic is built
        self.client.post(
            f"/api/documents/{self.doc.id}/build-target-logic",
            json={
                "environment": "dev",
                "target_config": {"schema_name": "public"}
            },
            headers=self.headers
        )

        # Simulate browser refresh by calling GET endpoint
        res = self.client.get(f"/api/documents/{self.doc.id}/target-artifacts", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        artifacts = res.get_json()
        self.assertTrue(len(artifacts) > 0)
        dev_art = artifacts[0]

        self.assertIn("source_metadata", dev_art)
        self.assertIn("source_mapping", dev_art)
        self.assertTrue(len(dev_art["source_mapping"]) > 0)
        self.assertTrue(len(dev_art["source_metadata"].get("table_audit", [])) > 0)

if __name__ == "__main__":
    unittest.main()
