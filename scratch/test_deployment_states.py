import unittest
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import app, db, User, Project, Document, DBConnection, TargetArtifact


from auth import generate_token


class TestDeploymentStates(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.app = app
        self.client = app.test_client()
        self.ctx = app.app_context()
        self.ctx.push()

        # Find or create admin user for testing
        self.user = User.query.filter_by(username="admin").first()
        if not self.user:
            self.user = User(username="admin", role="admin")
            self.user.set_password("admin123")
            db.session.add(self.user)
            db.session.commit()

        self.token = generate_token(self.user)
        self.headers = {"Authorization": f"Bearer {self.token}"}

        # Create test project
        self.project = Project(name="Test Deployment States Project")
        db.session.add(self.project)
        db.session.commit()

        # Create test document with analysis data requiring source tables
        self.analysis_with_sources = {
            "document_id": "999",
            "control_overview": {
                "identification": {"control_number": "CTRL-99", "control_title": "Test Control"},
                "target_schema": "test_schema"
            },
            "sources": [
                {"source_table_name": "src_orders", "source_table": "src_orders", "database": "src_db", "schema": "public"},
                {"source_table_name": "src_customers", "source_table": "src_customers", "database": "src_db", "schema": "public"}
            ],
            "rules": {"input_streams": [], "filter_rules": [], "balance_rules": [], "reconciliation_flows": []},
            "mappings": [{"source_field": "order_id", "target_column": "order_id", "derivation_logic": "direct"}]
        }

        self.doc = Document(
            project_id=self.project.id,
            filename="test_ctrl.xlsx",
            original_name="test_ctrl.xlsx",
            file_type=".xlsx",
            file_path="uploads/test_ctrl.xlsx",
            status="analyzed",
            analysis_data=self.analysis_with_sources
        )
        db.session.add(self.doc)
        db.session.commit()

    def tearDown(self):
        # Cleanup
        TargetArtifact.query.filter_by(project_id=self.project.id).delete()
        DBConnection.query.filter_by(project_id=self.project.id).delete()
        Document.query.filter_by(project_id=self.project.id).delete()
        Project.query.filter_by(id=self.project.id).delete()
        db.session.commit()
        self.ctx.pop()

    def test_scenario_d_no_credentials_no_kdb_is_preview_only(self):
        """Scenario D: No credentials and no KDB -> PREVIEW_ONLY"""
        # Ensure no DBConnection exists for this project
        DBConnection.query.filter_by(project_id=self.project.id).delete()
        db.session.commit()

        # Temporarily mock get_env_db_password to return None for isolated test
        import app as app_module
        orig_fn = app_module.get_env_db_password
        app_module.get_env_db_password = lambda: None
        try:
            res = self.client.post(f"/api/documents/{self.doc.id}/build-target-logic", json={
                "environment": "dev",
                "target_config": {"db_type": "postgresql", "host": "192.168.1.100", "database_name": "test_db", "username": "u", "password": ""}
            }, headers=self.headers)
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertTrue(data["preview_mode"])
            self.assertTrue(data["requires_kdb_for_deploy"])
            self.assertEqual(data["deployment_status"], "preview_only")
            self.assertEqual(data["artifact"]["deployment_status"], "preview_only")
        finally:
            app_module.get_env_db_password = orig_fn

    def test_scenario_a_manual_credentials_verified_not_preview_only(self):
        """Scenario A: Manual credentials verified, no KDB -> DRAFT (or BLOCKED if tables missing), NOT PREVIEW_ONLY"""
        # Create verified manual DB connection for source
        conn = DBConnection(
            project_id=self.project.id,
            source_db_name="Test Source DB",
            conn_role="source",
            db_type="postgresql",
            host="192.168.1.100",
            port=5432,
            database_name="src_db",
            username="src_user",
            password="secret_password",
            schema_name="public",
            status="connected"
        )
        db.session.add(conn)
        db.session.commit()

        # Document without missing sources (all empty / synthesized)
        doc_no_sources = Document(
            project_id=self.project.id,
            filename="no_sources.xlsx",
            original_name="no_sources.xlsx",
            file_type=".xlsx",
            file_path="uploads/no_sources.xlsx",
            status="analyzed",
            analysis_data={
                "control_overview": {"identification": {"control_number": "CTRL-88"}, "target_schema": "public"},
                "sources": [],
                "mappings": []
            }
        )
        db.session.add(doc_no_sources)
        db.session.commit()

        res = self.client.post(f"/api/documents/{doc_no_sources.id}/build-target-logic", json={
            "environment": "dev"
        }, headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        # MUST NOT be preview_only
        self.assertFalse(data["preview_mode"])
        self.assertFalse(data["requires_kdb_for_deploy"])
        self.assertIn(data["deployment_status"], ("draft", "ready"))
        self.assertNotEqual(data["deployment_status"], "preview_only")

    def test_scenario_b_manual_credentials_verified_tables_missing_is_blocked(self):
        """Scenario B: Manual credentials verified, required source tables missing -> BLOCKED / quality gate, NOT PREVIEW_ONLY"""
        # Create verified manual DB connection for source
        conn = DBConnection(
            project_id=self.project.id,
            source_db_name="Test Source DB",
            conn_role="source",
            db_type="postgresql",
            host="192.168.1.100",
            port=5432,
            database_name="src_db",
            username="src_user",
            password="secret_password",
            schema_name="public",
            status="connected"
        )
        db.session.add(conn)
        db.session.commit()

        # self.doc has 2 required source tables which will not be found in non-existent 192.168.1.100
        res = self.client.post(f"/api/documents/{self.doc.id}/build-target-logic", json={
            "environment": "dev"
        }, headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        # Must be BLOCKED due to missing tables quality gate, NOT preview_only!
        self.assertFalse(data["preview_mode"])
        self.assertFalse(data["requires_kdb_for_deploy"])
        self.assertEqual(data["deployment_status"], "blocked")
        self.assertGreater(data["missing_source_tables_count"], 0)

    def test_scenario_c_kdb_vault_flow_works(self):
        """Scenario C: KDB uploaded -> existing KDB flow continues working"""
        # Upload vault content
        vault_content = """[source.crm]
db_type = postgresql
host = 192.168.1.100
port = 5432
database = crm_db
username = postgres
password = pass123
schema = public
"""
        res_v = self.client.post(f"/api/projects/{self.project.id}/upload-vault", json={
            "content": vault_content,
            "filename": "credentials.kdb"
        }, headers=self.headers)
        self.assertEqual(res_v.status_code, 200)

        # Verify source connections were created
        source_conns = DBConnection.query.filter_by(project_id=self.project.id, conn_role="source").all()
        self.assertGreater(len(source_conns), 0)

    def test_scenario_e_source_verified_tables_found_target_verified_is_ready(self):
        """Scenario E: Source verified + required tables available + target verified -> READY and deployment allowed"""
        # Setup source connection
        src_conn = DBConnection(
            project_id=self.project.id,
            source_db_name="Local Postgres",
            conn_role="source",
            db_type="postgresql",
            host="localhost",
            port=5432,
            database_name="hla_db",
            username="postgres",
            status="connected"
        )
        # Setup target connection
        tgt_conn = DBConnection(
            project_id=self.project.id,
            source_db_name="Local Target DB",
            conn_role="target",
            target_env="dev",
            db_type="postgresql",
            host="localhost",
            port=5432,
            database_name="hla_db",
            username="postgres",
            schema_name="public",
            status="connected"
        )
        db.session.add_all([src_conn, tgt_conn])
        db.session.commit()

        # Document with no missing sources
        ready_doc = Document(
            project_id=self.project.id,
            filename="ready_ctrl.xlsx",
            original_name="ready_ctrl.xlsx",
            file_type=".xlsx",
            file_path="uploads/ready_ctrl.xlsx",
            status="analyzed",
            analysis_data={
                "control_overview": {"identification": {"control_number": "CTRL-77"}, "target_schema": "public"},
                "sources": [],
                "mappings": [{"source_field": "f1", "target_column": "f1", "derivation_logic": "direct"}]
            }
        )
        db.session.add(ready_doc)
        db.session.commit()

        res = self.client.post(f"/api/documents/{ready_doc.id}/build-target-logic", json={
            "environment": "dev"
        }, headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertFalse(data["preview_mode"])
        self.assertEqual(data["deployment_status"], "ready")
        self.assertEqual(data["artifact"]["deployment_status"], "ready")


if __name__ == "__main__":
    unittest.main()
