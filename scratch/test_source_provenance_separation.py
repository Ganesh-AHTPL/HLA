"""
Test Source vs Target Provenance Separation & Role Model
---------------------------------------------------------
Verifies:
1. Dynamic extraction of SOURCE entities strictly based on document provenance.
2. Target/intermediate entities (data_model, report_derivations, config_tables) are NEVER classified as SOURCE entities.
3. Quality Gate calculates missing upstream sources strictly from SOURCE entities.
4. Zero hardcoded table names, schemas, databases, or patterns.
"""

import os
import sys
import unittest
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import (
    app, db, User, Project, Document, TargetArtifact,
    extract_document_source_entities, extract_document_target_entities,
    make_entity_key
)
from auth import generate_token
from target_logic_builder import discover_target_entities


class TestSourceTargetProvenanceSeparation(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()

        self.run_id = uuid.uuid4().hex[:8]

    def tearDown(self):
        self.ctx.pop()

    def test_01_hla_document_provenance_separation(self):
        """
        Simulates an HLA document with 4 genuine source tables and 4 data model / intermediate entities.
        Verifies that ONLY the 4 source entities are extracted as source.
        """
        mock_analysis = {
            "sources": [
                {"source_table_name": "order_header", "schema": "sales", "database": "ha", "source_id": "SRC_01"},
                {"source_table_name": "order_item", "schema": "sales", "database": "ha", "source_id": "SRC_02"},
                {"source_table_name": "customer_master", "schema": "sales", "database": "ha", "source_id": "SRC_03"},
                {"source_table_name": "product_master", "schema": "sales", "database": "ha", "source_id": "SRC_04"}
            ],
            "data_model": [
                {"dataset_table_entity_name": "order_ingest", "stage": "STAGE", "schema": "sales"},
                {"dataset_table_entity_name": "order_flagged", "stage": "INTERMEDIATE", "schema": "sales"},
                {"dataset_table_entity_name": "work_item_current_run", "stage": "PROCESSING", "schema": "sales"},
                {"dataset_table_entity_name": "work_item", "stage": "CURATED", "schema": "sales"}
            ],
            "rules": {
                "filter_rules": [
                    {"rule_name": "R1", "source_dataset": "order_ingest", "expression": "amount > 0"},
                    {"rule_name": "R2", "source_dataset": "work_item", "expression": "flag = 'Y'"}
                ]
            },
            "buckets": [
                {"bucket_name": "B1", "source_dataset": "order_flagged"}
            ],
            "mappings": [
                {"source_table": "order_header", "source_column": "order_id", "target_table": "order_ingest", "target_column": "order_id"},
                {"source_table": "order_item", "source_column": "item_id", "target_table": "order_ingest", "target_column": "item_id"}
            ]
        }

        source_entities = extract_document_source_entities(mock_analysis)
        self.assertEqual(len(source_entities), 4)

        source_names = {s["table_name"] for s in source_entities}
        self.assertEqual(source_names, {"order_header", "order_item", "customer_master", "product_master"})

        # Verify that NONE of the intermediate/target models are in source_entities
        for prohibited in ["order_ingest", "order_flagged", "work_item_current_run", "work_item"]:
            self.assertNotIn(prohibited, source_names)

        # Verify role and origin on each source entity
        for s in source_entities:
            self.assertEqual(s["role"], "SOURCE")
            self.assertEqual(s["origin"], "document_sources_declaration")
            self.assertEqual(s["schema"], "sales")
            self.assertEqual(s["database"], "ha")

        # Verify target entities extraction
        target_entities = extract_document_target_entities(mock_analysis)
        target_names = {t["table_name"] for t in target_entities}
        self.assertTrue("order_ingest" in target_names or "work_item" in target_names)

    def test_02_completely_arbitrary_domain_zero_hardcoding(self):
        """
        Verifies provenance separation with dynamically generated, arbitrary names across healthcare/aviation domains.
        """
        dyn_s1 = f"patient_encounter_{self.run_id}"
        dyn_s2 = f"clinical_obs_{self.run_id}"
        dyn_t1 = f"encounter_curated_{self.run_id}"
        dyn_t2 = f"clinical_kpi_summary_{self.run_id}"
        dyn_sch = f"ehr_schema_{self.run_id}"

        mock_analysis = {
            "sources": [
                {"source_table_name": dyn_s1, "schema": dyn_sch, "database": "ehr_db"},
                {"source_table_name": dyn_s2, "schema": dyn_sch, "database": "ehr_db"}
            ],
            "data_model": [
                {"dataset_table_entity_name": dyn_t1, "stage": "STAGE"},
                {"dataset_table_entity_name": dyn_t2, "stage": "TARGET"}
            ],
            "rules": {
                "business_rules": [
                    {"rule_id": "BR_01", "source_dataset": dyn_t1}
                ]
            },
            "mappings": [
                {"source_table": dyn_s1, "source_column": "id", "target_table": dyn_t1, "target_column": "id"}
            ]
        }

        source_entities = extract_document_source_entities(mock_analysis)
        self.assertEqual(len(source_entities), 2)
        source_names = {s["table_name"] for s in source_entities}
        self.assertEqual(source_names, {dyn_s1, dyn_s2})
        self.assertNotIn(dyn_t1, source_names)
        self.assertNotIn(dyn_t2, source_names)

    def test_03_fallback_mappings_without_sources_sheet(self):
        """
        When document lacks a dedicated sources sheet, extracts candidate sources from mappings
        while strictly excluding data_model entities.
        """
        dyn_src = f"upstream_stream_{self.run_id}"
        dyn_tgt = f"downstream_stage_{self.run_id}"

        mock_analysis = {
            "data_model": [
                {"dataset_table_entity_name": dyn_tgt, "stage": "TARGET"}
            ],
            "mappings": [
                {"source_table": dyn_src, "source_column": "pk", "target_table": dyn_tgt, "target_column": "pk"},
                # Even if mapping mistakenly puts a target entity as source_table in some rule mapping:
                {"source_table": dyn_tgt, "source_column": "pk", "target_table": "reporting_mart", "target_column": "pk"}
            ]
        }

        source_entities = extract_document_source_entities(mock_analysis)
        source_names = {s["table_name"] for s in source_entities}
        self.assertIn(dyn_src, source_names)
        self.assertNotIn(dyn_tgt, source_names)

    def test_04_deploy_target_validation_and_no_nameerror(self):
        """
        Tests deploy-target endpoint with action='validate' and action='deploy' ensuring zero NameError: sources.
        """
        user = User.query.filter_by(username="admin").first()
        if not user:
            user = User(username="admin", email="admin@test.com", role="admin")
            user.set_password("AdminPass123!")
            db.session.add(user)
            db.session.commit()

        token = generate_token(user)
        headers = {"Authorization": f"Bearer {token}"}

        proj = Project(name=f"Proj_{self.run_id}", description="Dynamic Test")
        db.session.add(proj)
        db.session.commit()

        dyn_src = f"feed_table_{self.run_id}"
        dyn_tgt = f"target_stage_{self.run_id}"
        dyn_sch = f"dyn_schema_{self.run_id}"

        doc = Document(
            project_id=proj.id,
            filename=f"test_{self.run_id}.xlsx",
            original_name=f"test_{self.run_id}.xlsx",
            file_type="xlsx",
            file_path="/tmp/fake.xlsx",
            analysis_data={
                "sources": [{"source_table_name": dyn_src, "schema": dyn_sch, "database": "dyn_db"}],
                "data_model": [{"dataset_table_entity_name": dyn_tgt, "stage": "STAGE"}],
                "control_overview": {"identification": {"control_number": f"CTRL-{self.run_id}"}, "target_schema": "dyn_target"}
            }
        )
        db.session.add(doc)
        db.session.commit()

        art = TargetArtifact(
            project_id=proj.id,
            document_id=doc.id,
            environment="dev",
            target_schema="dyn_target",
            generated_ddl=f"CREATE TABLE IF NOT EXISTS dyn_target.{dyn_tgt} (id VARCHAR(50), payload TEXT);",
            generated_transformation_sql=f"-- Transformation for {dyn_tgt}\nSELECT 1;"
        )
        db.session.add(art)
        db.session.commit()

        # Test action='validate' - Quality gate blocks because dynamic source table does not exist in live DB
        res_val = self.client.post(
            f"/api/documents/{doc.id}/deploy-target",
            headers=headers,
            json={"environment": "dev", "action": "validate", "target_config": {"schema_name": "dyn_target", "db_type": "sandbox"}}
        )
        self.assertIn(res_val.status_code, (200, 400))
        data_val = res_val.get_json()
        self.assertNotIn("name 'sources' is not defined", str(data_val))
        self.assertIn(dyn_src, str(data_val))

        # Test action='deploy'
        res_dep = self.client.post(
            f"/api/documents/{doc.id}/deploy-target",
            headers=headers,
            json={"environment": "dev", "action": "deploy", "target_config": {"schema_name": "dyn_target", "db_type": "sandbox"}}
        )
        self.assertIn(res_dep.status_code, (200, 400))
        data_dep = res_dep.get_json()
        self.assertNotIn("name 'sources' is not defined", str(data_dep))
        self.assertIn(dyn_src, str(data_dep))


if __name__ == "__main__":
    unittest.main()
