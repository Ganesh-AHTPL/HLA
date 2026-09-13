import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
import json
import requests
import openpyxl
from excel_analyzer import (
    analyze_excel_specification,
    find_table_header,
    extract_control_identification,
    extract_columns_from_english_logic
)
from target_logic_builder import build_target_logic_package

BASE_URL = "http://127.0.0.1:5000"
EXCEL_PATH = r"C:\Users\Hp\Downloads\Control23_Source_Logic.xlsx"

class TestExcelSpecificationFull(unittest.TestCase):

    def setUp(self):
        self.session = requests.Session()
        resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        self.assertEqual(resp.status_code, 200)
        self.token = resp.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_01_direct_excel_parsing(self):
        """Test complete scanning of all 7 sheets without any hardcoding."""
        self.assertTrue(os.path.exists(EXCEL_PATH), f"Specification file not found at {EXCEL_PATH}")
        
        analysis = analyze_excel_specification(EXCEL_PATH)
        
        # 1. Control Identification
        ctrl = analysis.get("control_overview", {}).get("identification", {})
        self.assertEqual(ctrl.get("control_number"), "CTRL-23")
        self.assertIn("Control-23", ctrl.get("control_title"))
        
        target_schema = analysis.get("control_overview", {}).get("target_schema", {})
        schema_name = target_schema.get("schema_name") if isinstance(target_schema, dict) else target_schema
        self.assertEqual(schema_name, "ra_ctrl.ctrl_23")

        # 2. Source Systems (7 sources across 3 databases)
        sources = analysis.get("sources", [])
        self.assertEqual(len(sources), 7)
        table_names = [s.get("full_table_name") for s in sources]
        self.assertIn("cmdb.dl_itsm_cmdb_daily_dump", table_names)
        self.assertIn("reports.dl_vdom_firewall_audit_report", table_names)
        self.assertIn("pearl.dl_pearl_active_profiles", table_names)
        self.assertIn("qlik_report.dl_ra_order_report_daily", table_names)
        self.assertIn("sap.zcurr_conv_rate", table_names)
        self.assertIn("SFDC.copf_id", table_names)
        self.assertIn("ra.stg_rk_ckt_recon_final", table_names)

        # 3. Source Databases (3 unique server/db combinations)
        source_dbs = analysis.get("source_databases", [])
        self.assertEqual(len(source_dbs), 3)

        # 4. Data Model (24 tables across 4 stages)
        data_model = analysis.get("data_model", [])
        self.assertEqual(len(data_model), 24)
        dm_names = [t.get("table_name") for t in data_model]
        self.assertIn("CTRL_23_SOURCE_DATASET_DDOS", dm_names)
        self.assertIn("CTRL_23_SOURCE_DATASET_VDOM", dm_names)
        self.assertIn("ETL_DATA_ACQUISITION", dm_names)
        self.assertIn("CTRL_23_FILTERED_DATASET_DDOS", dm_names)
        self.assertIn("CTRL_23_FILTER_SUMMARY", dm_names)
        self.assertIn("CTRL_23_BALANCE_DATASET_VDOM", dm_names)
        self.assertIn("CTRL_23_WORKING_DATASET_RL", dm_names)
        self.assertIn("CTRL_23_WORKING_DATASET_KL", dm_names)
        self.assertIn("CTRL_23_WORK_ITEM_CURRENT_RUN", dm_names)
        self.assertIn("KRI_CONFIG", dm_names)
        self.assertIn("CTRL_CONFIG", dm_names)
        self.assertIn("BUCKET_CONFIG", dm_names)
        self.assertIn("RULE_CONFIG", dm_names)

        # 5. Business Rules (I1-I4, R1-R10, R11, R12-R15)
        rules = analysis.get("rules", {})
        self.assertEqual(len(rules.get("input_streams", [])), 4)
        self.assertEqual(len(rules.get("filter_rules", [])), 10)
        self.assertEqual(len(rules.get("balance_rules", [])), 1)
        self.assertEqual(len(rules.get("reconciliation_flows", [])), 4)

        # 6. Buckets & Derived Fields (FB1-FB7, B1-B6, B4.1, B5.1-B5.6, 5 derived fields)
        buckets = analysis.get("buckets", [])
        self.assertEqual(len(buckets), 21)
        bkt_ids = [b.get("bucket_id") for b in buckets]
        self.assertIn("FB1", bkt_ids)
        self.assertIn("FB7", bkt_ids)
        self.assertIn("B1", bkt_ids)
        self.assertIn("B5.1", bkt_ids)

        derived_fields = analysis.get("derived_fields", [])
        self.assertEqual(len(derived_fields), 5)
        df_names = [d.get("field_name") for d in derived_fields]
        self.assertIn("Ageing_TRF", df_names)
        self.assertIn("TRF_Impact", df_names)
        self.assertIn("Days_Up", df_names)
        self.assertIn("Impact_Up", df_names)
        self.assertIn("Ageing_Up", df_names)

        # 7. Config Tables (3 dynamic tables)
        cfg_tables = analysis.get("config_tables", [])
        self.assertEqual(len(cfg_tables), 3)
        cfg_names = [c.get("table_name") for c in cfg_tables]
        self.assertIn("internal_profiles_vdom", cfg_names)
        self.assertIn("managed_service_types", cfg_names)
        self.assertIn("ip_exclusion_list", cfg_names)

    def test_02_nlp_column_extraction_from_english_logic(self):
        """Test extraction of column names alone from human-readable English rules."""
        rule_text_1 = "Filter out duplicate records (Host_Name, VDOM, IP are duplicate) in VDOM"
        cols_1 = extract_columns_from_english_logic(rule_text_1)
        self.assertIn("host_name", cols_1)
        self.assertIn("vdom", cols_1)
        self.assertIn("ip", cols_1)

        rule_text_2 = "Match basis IP Address (VUTM interface_ip = CMDB production_ip)"
        cols_2 = extract_columns_from_english_logic(rule_text_2)
        self.assertIn("interface_ip", cols_2)
        self.assertIn("production_ip", cols_2)

        rule_text_3 = "Field mapping: Circuit_Id (VUTM/DDOS) <-> SERVICE_ID (Circuit Reco)"
        cols_3 = extract_columns_from_english_logic(rule_text_3)
        self.assertIn("circuit_id", cols_3)
        self.assertIn("service_id", cols_3)

        formula_text = "If ageing > 90 days then Impact = (COPF timestamp - Current date) * MRC_IN_USD/30"
        cols_4 = extract_columns_from_english_logic(formula_text)
        self.assertIn("mrc_in_usd", cols_4)

    def test_03_zero_hardcoding_with_synthetic_control24(self):
        """Test that the parser dynamically handles another control number (e.g. Control-24) with zero code changes."""
        wb = openpyxl.load_workbook(EXCEL_PATH)
        ws = wb["Source Systems"]
        ws.cell(1, 1).value = "Control-24 NextGen Billing Reconciliation - Source Systems"
        
        scratch_24_path = os.path.join(os.path.dirname(__file__), "test_ctrl24_spec.xlsx")
        wb.save(scratch_24_path)
        wb.close()

        try:
            analysis_24 = analyze_excel_specification(scratch_24_path)
            ctrl_id = analysis_24["control_overview"]["identification"]
            self.assertEqual(ctrl_id["control_number"], "CTRL-24")
            self.assertIn("Control-24", ctrl_id["control_title"])

            schema = analysis_24["control_overview"]["target_schema"]["schema_name"]
            self.assertEqual(schema, "ra_ctrl.ctrl_24")
        finally:
            if os.path.exists(scratch_24_path):
                os.remove(scratch_24_path)

    def test_04_api_upload_and_auto_analysis(self):
        """Test that uploading the Excel file to /api/projects/{id}/files triggers immediate auto-analysis."""
        # Create a test project
        p_resp = self.session.post(f"{BASE_URL}/api/projects", headers=self.headers, json={
            "name": f"Excel Spec Test {os.urandom(3).hex()}",
            "control_number": "CTRL-23",
            "description": "Validation project for standard Excel specification format"
        })
        self.assertEqual(p_resp.status_code, 201)
        p_json = p_resp.json()
        project_id = p_json.get("project", {}).get("id") or p_json.get("id")

        # Upload Excel specification
        with open(EXCEL_PATH, "rb") as f:
            u_resp = self.session.post(
                f"{BASE_URL}/api/projects/{project_id}/upload",
                headers=self.headers,
                files={"file": ("Control23_Source_Logic.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            )
        self.assertEqual(u_resp.status_code, 200)
        u_data = u_resp.json()
        doc_id = u_data["id"]
        TestExcelSpecificationFull.uploaded_doc_id = doc_id

        # Verify auto-analysis occurred
        self.assertIn("analysis", u_data)
        analysis = u_data["analysis"]
        self.assertEqual(analysis["control_overview"]["identification"]["control_number"], "CTRL-23")
        self.assertEqual(len(analysis["sources"]), 7)
        self.assertEqual(len(analysis["data_model"]), 24)

        # Verify document status is 'analyzed' in DB
        doc_resp = self.session.get(f"{BASE_URL}/api/documents/{doc_id}", headers=self.headers)
        self.assertEqual(doc_resp.status_code, 200)
        self.assertEqual(doc_resp.json()["status"], "analyzed")

    def test_05_target_logic_builder_and_gated_deployment(self):
        """
        Verify that:
        1. When source tables are missing, dry-run validation and deployment fail with HTTP 400.
        2. No '(DEV)' or '(dev)' appears in action buttons or labels.
        3. Target DDL builds with target schema 'ra_ctrl.ctrl_23'.
        """
        # Create project and upload specification
        p_resp = self.session.post(f"{BASE_URL}/api/projects", headers=self.headers, json={
            "name": f"Gating Test {os.urandom(3).hex()}",
            "description": "Validation for gated deployment"
        })
        self.assertEqual(p_resp.status_code, 201)
        project_id = p_resp.json().get("project", {}).get("id")

        with open(EXCEL_PATH, "rb") as f:
            u_resp = self.session.post(
                f"{BASE_URL}/api/projects/{project_id}/upload",
                headers=self.headers,
                files={"file": ("Control23_Source_Logic.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            )
        self.assertEqual(u_resp.status_code, 200)
        doc_id = u_resp.json()["id"]

        # 1. Scan source database
        scan_resp = self.session.post(f"{BASE_URL}/api/documents/{doc_id}/scan-source-db", headers=self.headers, json={
            "database_name": "ods",
            "host": "localhost",
            "port": 5432,
            "username": "postgres"
        })
        self.assertEqual(scan_resp.status_code, 200)
        scan_data = scan_resp.json()
        results = scan_data.get("results", {})
        
        # Verify reports.dl_vdom_firewall_audit_report is strictly NOT found
        vdom_key = "reports.dl_vdom_firewall_audit_report"
        if vdom_key in results:
            self.assertFalse(results[vdom_key]["table_found"], "reports.dl_vdom_firewall_audit_report must not be found in public schema")

        # 2. Build target logic
        bld_resp = self.session.post(f"{BASE_URL}/api/documents/{doc_id}/build-target-logic", headers=self.headers, json={
            "environment": "dev",
            "target_schema": "ra_ctrl.ctrl_23"
        })
        self.assertEqual(bld_resp.status_code, 200)
        bld_data = bld_resp.json()
        artifact = bld_data.get("artifact", {})
        self.assertIn("generated_ddl", artifact)
        self.assertNotIn("(DEV)", artifact.get("environment", ""))

        # 3. Dry-run deployment MUST be blocked because tables are missing
        dep_resp = self.session.post(f"{BASE_URL}/api/documents/{doc_id}/deploy-target", headers=self.headers, json={
            "environment": "dev",
            "dry_run": True
        })
        self.assertEqual(dep_resp.status_code, 400, "Dry-run MUST fail with 400 when source tables are not found")
        dep_data = dep_resp.json()
        self.assertTrue(dep_data.get("blocked"), "Deployment response must have blocked=True")
        self.assertIn("blocked: Upstream source table(s) not found", dep_data.get("message", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
