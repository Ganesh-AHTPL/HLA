import sys
import os
import unittest

# Add root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from target_logic_builder import (
    build_target_logic_package,
    generate_target_ddl,
    generate_source_tables_ddl,
    generate_transformation_sql,
    generate_pyspark_pipeline,
    deploy_target_ddl
)


class TestGenericHLAArchitectureEngine(unittest.TestCase):
    
    def test_control_24_generic_pipeline(self):
        """Simulates Control-24 (Financial / ERP Reconciliation)."""
        ctrl_24_analysis = {
            "control_overview": {
                "identification": {
                    "control_number": "CTRL-24",
                    "control_title": "ERP General Ledger vs Banking Settlement Reconciliation",
                    "purpose": "Daily automated reconciliation between SAP GL entries and bank statement feeds."
                }
            },
            "sources": [
                {"source_db": "SAP_ERP", "source_schema": "finance", "source_table": "sap_gl_entries", "type_of_load": "Truncate and load"},
                {"source_db": "Treasury_Portal", "source_schema": "banking", "source_table": "bank_statement_lines", "type_of_load": "Truncate and load"},
                {"source_db": "Salesforce_CRM", "source_schema": "contracts", "source_table": "sfdc_customer_contracts", "type_of_load": "Append"}
            ],
            "rules": {
                "input_streams": [
                    {"rule_id": "I1", "data_stream": "SAP GL", "rule_statement": "Daily SAP ledger export"},
                    {"rule_id": "I2", "data_stream": "Banking Feed", "rule_statement": "Daily MT940 statement lines"}
                ],
                "filter_rules": [
                    {"rule_id": "R1", "category": "Filter", "data_stream": "SAP GL", "rule_statement": "Deduplicate on (transaction_id, account_code) retaining latest posting_date."},
                    {"rule_id": "R2", "category": "Filter", "data_stream": "SAP GL", "rule_statement": "Drop records if mandatory keys transaction_id and amount are NULL."},
                    {"rule_id": "R3", "category": "Filter", "data_stream": "Banking Feed", "rule_statement": "Filter out internal bank sweeps and sandbox transfers."}
                ],
                "balance_rules": [
                    {"rule_id": "R4", "category": "Balance Node", "data_stream": "All Financial Streams", "rule_statement": "Harmonize into central financial balance staging."}
                ],
                "reconciliation_flows": [
                    {"rule_id": "R5", "category": "Reconciliation", "data_stream": "SAP vs Bank", "rule_statement": "Tier 1 exact transaction ID match, Tier 2 amount and reference match."}
                ]
            },
            "mappings": [
                {"report_table_name": "fin_recon_summary_report", "target_column": "reconciled_transaction_id", "mapping_type": "Direct", "source_field": "transaction_id"},
                {"report_table_name": "fin_recon_summary_report", "target_column": "settlement_variance_usd", "mapping_type": "Derived", "derivation_logic": "CASE WHEN sap.amount = bank.amount THEN 0 ELSE (sap.amount - bank.amount) END"},
                {"report_table_name": "fin_recon_summary_report", "target_column": "audit_verdict", "mapping_type": "Derived", "derivation_logic": "CASE WHEN variance = 0 THEN 'CLEARED' ELSE 'INVESTIGATE' END"}
            ],
            "config_tables": [
                {"config_table_name": "cfg_bank_holiday_exceptions", "purpose": "Banking settlement grace periods", "sample_fields": "holiday_date, currency, region"}
            ]
        }

        introspected = {
            "sap_gl_entries": {
                "columns": [
                    {"column_name": "id", "data_type": "BIGINT", "is_nullable": "NO", "default": None},
                    {"column_name": "transaction_id", "data_type": "VARCHAR(100)", "is_nullable": "NO", "default": None},
                    {"column_name": "account_code", "data_type": "VARCHAR(50)", "is_nullable": "NO", "default": None},
                    {"column_name": "amount", "data_type": "NUMERIC(18,2)", "is_nullable": "NO", "default": "0.00"},
                    {"column_name": "currency", "data_type": "VARCHAR(10)", "is_nullable": "YES", "default": "'USD'"},
                    {"column_name": "posting_date", "data_type": "TIMESTAMP", "is_nullable": "NO", "default": "CURRENT_TIMESTAMP"}
                ]
            },
            "bank_statement_lines": {
                "columns": [
                    {"column_name": "id", "data_type": "BIGINT", "is_nullable": "NO", "default": None},
                    {"column_name": "transaction_id", "data_type": "VARCHAR(100)", "is_nullable": "NO", "default": None},
                    {"column_name": "bank_reference", "data_type": "VARCHAR(100)", "is_nullable": "YES", "default": None},
                    {"column_name": "amount", "data_type": "NUMERIC(18,2)", "is_nullable": "NO", "default": "0.00"},
                    {"column_name": "created_dtm", "data_type": "TIMESTAMP", "is_nullable": "NO", "default": "CURRENT_TIMESTAMP"}
                ]
            }
        }

        target_cfg = {
            "target_env": "dev",
            "db_type": "postgresql",
            "schema_name": "target_ctrl24_dev"
        }

        pkg = build_target_logic_package(ctrl_24_analysis, introspected, target_cfg)

        # Assertions
        ddl = pkg["ddl"]
        trans_sql = pkg["transformation_sql"]
        pyspark = pkg["pyspark_code"]

        # ZERO legacy VDOM/DDOS/CMDB references
        self.assertNotIn("vdom", ddl.lower(), "DDL must not mention vdom")
        self.assertNotIn("ddos", ddl.lower(), "DDL must not mention ddos")
        self.assertNotIn("cmdb", ddl.lower(), "DDL must not mention cmdb")
        self.assertNotIn("vdom", trans_sql.lower(), "SQL must not mention vdom")
        self.assertNotIn("ddos", trans_sql.lower(), "SQL must not mention ddos")
        self.assertNotIn("cmdb", trans_sql.lower(), "SQL must not mention cmdb")
        self.assertNotIn("vdom", pyspark.lower(), "PySpark must not mention vdom")

        # Dynamic Ctrl-24 objects present
        self.assertIn("sap_gl_entries", ddl)
        self.assertIn("bank_statement_lines", ddl)
        self.assertIn("stg_sap_gl_entries_clean", ddl)
        self.assertIn("stg_bank_statement_lines_clean", ddl)
        self.assertIn("ctrl_24_balanced_dataset", ddl)
        self.assertIn("ctrl_24_recon_matches", ddl)
        self.assertIn("ctrl_24_recon_exceptions", ddl)
        self.assertIn("fin_recon_summary_report", ddl)
        self.assertIn("cfg_bank_holiday_exceptions", ddl)

        # Transformation SQL verifies dynamic execution
        self.assertIn("stg_sap_gl_entries_clean", trans_sql)
        self.assertIn("stg_bank_statement_lines_clean", trans_sql)
        self.assertIn("ctrl_24_balanced_dataset", trans_sql)
        self.assertIn("fin_recon_summary_report", trans_sql)

        # PySpark verifies dynamic reads
        self.assertIn('spark.read.jdbc(jdbc_url, "sap_gl_entries"', pyspark)
        self.assertIn('spark.read.jdbc(jdbc_url, "bank_statement_lines"', pyspark)
        self.assertIn('ctrl_24_balanced_dataset', pyspark)

        # Sandbox deployment test returns dynamic tables
        success, msg, tables = deploy_target_ddl({"db_type": "sandbox"}, ddl)
        self.assertTrue(success)
        self.assertIn("sap_gl_entries", tables)
        self.assertIn("stg_sap_gl_entries_clean", tables)
        self.assertIn("ctrl_24_balanced_dataset", tables)
        self.assertIn("fin_recon_summary_report", tables)
        print("[PASS] Control-24 Generic Test Passed! Tables provisioned:", len(tables))

    def test_control_25_iot_pipeline(self):
        """Simulates Control-25 (IoT Sensor & Edge Telemetry)."""
        ctrl_25_analysis = {
            "control_overview": {
                "identification": {
                    "control_number": "CTRL-25",
                    "control_title": "IoT Edge Telemetry vs Asset Registry",
                    "purpose": "Validation of field edge sensor heartbeat packets against central hardware registry."
                }
            },
            "sources": [
                {"source_db": "IoT_Broker", "source_schema": "public", "source_table": "edge_sensor_telemetry", "type_of_load": "Truncate and load"},
                {"source_db": "Asset_CMDB", "source_schema": "public", "source_table": "hardware_asset_registry", "type_of_load": "Truncate and load"}
            ],
            "rules": {
                "filter_rules": [
                    {"rule_id": "R1", "category": "Filter", "data_stream": "Edge Telemetry", "rule_statement": "Deduplicate on (device_id, event_timestamp)."}
                ],
                "balance_rules": [
                    {"rule_id": "R2", "category": "Balance Node", "data_stream": "All Streams", "rule_statement": "Harmonize into balanced telemetry."}
                ]
            },
            "mappings": [
                {"report_table_name": "iot_health_audit", "target_column": "device_health_status", "mapping_type": "Direct"}
            ]
        }

        pkg = build_target_logic_package(ctrl_25_analysis, {}, {"target_env": "dev", "schema_name": "target_ctrl25_dev"})
        self.assertIn("ctrl_25_balanced_dataset", pkg["ddl"])
        self.assertIn("stg_edge_sensor_telemetry_clean", pkg["ddl"])
        self.assertIn("iot_health_audit", pkg["ddl"])
        self.assertNotIn("vdom", pkg["ddl"].lower())
        print("[PASS] Control-25 Generic Test Passed!")


if __name__ == "__main__":
    unittest.main()
