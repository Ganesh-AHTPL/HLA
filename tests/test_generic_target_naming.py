"""
Unit tests for Generic Target Table Naming and Zero-Hardcoding Enforcement.

Verifies:
1. Absolute Rule: Never invent synthetic target tables (no ctrl_balanced_dataset, stg_*, customer_customer_master).
2. Separation of Logical Source and Physical Target.
3. HLA with explicit target generates ONLY that target object.
4. HLA with NO target entity defined generates 0 target tables and emits TARGET ENTITY NOT DEFINED banner.
5. Explicit data model stage/dimension entities are generated accurately according to document.
"""

import unittest
from target_logic_builder import (
    discover_target_entities,
    generate_target_ddl,
    generate_transformation_sql,
    generate_pyspark_pipeline,
    build_target_logic_package,
)


class TestGenericTargetNaming(unittest.TestCase):

    def test_hla_a_crm_customer_report(self):
        """
        HLA A:
        Source: CRM_DB.customer.customer_master
        Target: customer_report
        Generated target table: public.customer_report
        Must NOT generate: ctrl_customer_report, customer_customer_master, stg_customer_clean, ctrl_balanced_dataset
        """
        analysis_data = {
            "control_overview": {
                "identification": {"control_number": "CTRL-101", "control_title": "Customer Ingestion"},
                "target_schema": "public"
            },
            "sources": [
                {
                    "source_id": "SRC001",
                    "table_name_with_schema": "customer.customer_master",
                    "source_table": "customer_master",
                    "source_schema": "customer",
                    "database_source": "CRM_DB",
                    "type_of_load": "Append"
                }
            ],
            "mappings": [
                {
                    "target_table": "customer_report",
                    "target_column": "cust_id",
                    "source_table": "customer_master",
                    "source_field": "customer_id",
                    "mapping_type": "Direct"
                },
                {
                    "target_table": "customer_report",
                    "target_column": "cust_name",
                    "source_table": "customer_master",
                    "source_field": "name",
                    "mapping_type": "Direct"
                }
            ]
        }

        # 1. Target Entity Discovery
        targets = discover_target_entities(analysis_data, analysis_data["mappings"])
        target_names = [t["table_name"] for t in targets]
        self.assertEqual(target_names, ["customer_report"])

        # 2. Target DDL
        ddl = generate_target_ddl("public", "postgresql", analysis_data["sources"], {}, analysis_data["mappings"], {}, analysis_data)
        self.assertIn("CREATE TABLE IF NOT EXISTS public.customer_report", ddl)
        self.assertNotIn("ctrl_customer_report", ddl)
        self.assertNotIn("customer_customer_master", ddl)
        self.assertNotIn("ctrl_101_balanced_dataset", ddl)
        self.assertNotIn("ctrl_balanced_dataset", ddl)
        self.assertNotIn("stg_customer_master_clean", ddl)

        # 3. Transformation SQL
        sql = generate_transformation_sql("public", "postgresql", analysis_data["sources"], {}, analysis_data["mappings"], [], analysis_data["control_overview"], analysis_data)
        self.assertIn("INSERT INTO public.customer_report", sql)
        self.assertNotIn("ctrl_101_balanced_dataset", sql)

    def test_hla_b_finance_invoice_summary(self):
        """
        HLA B:
        Source: FINANCE_DB.billing.invoice
        Target: invoice_summary
        Generated target table: public.invoice_summary
        """
        analysis_data = {
            "control_overview": {
                "identification": {"control_number": "CTRL-202", "control_title": "Billing Reconciler"},
                "target_schema": "finance_mart"
            },
            "sources": [
                {
                    "source_id": "SRC001",
                    "table_name_with_schema": "billing.invoice",
                    "source_table": "invoice",
                    "source_schema": "billing",
                    "database_source": "FINANCE_DB",
                    "type_of_load": "Truncate & load"
                }
            ],
            "mappings": [
                {
                    "report_table_name": "invoice_summary",
                    "target_column": "total_amount",
                    "source_table": "invoice",
                    "source_field": "amount",
                    "mapping_type": "Direct"
                }
            ]
        }

        targets = discover_target_entities(analysis_data, analysis_data["mappings"])
        target_names = [t["table_name"] for t in targets]
        self.assertEqual(target_names, ["invoice_summary"])

        ddl = generate_target_ddl("finance_mart", "postgresql", analysis_data["sources"], {}, analysis_data["mappings"], {}, analysis_data)
        self.assertIn("CREATE TABLE IF NOT EXISTS finance_mart.invoice_summary", ddl)
        self.assertNotIn("finance_db_billing_invoice", ddl)
        self.assertNotIn("billing_invoice", ddl)

    def test_hla_c_no_target_entity_defined(self):
        """
        HLA C:
        Source: ERP_DB.inventory.stock
        Target: (No target defined in document)
        Result:
        0 target tables created.
        Target DB Studio displays TARGET ENTITY NOT DEFINED banner.
        """
        analysis_data = {
            "control_overview": {
                "identification": {"control_number": "CTRL-303", "control_title": "Inventory Feed Audit"},
                "target_schema": "public"
            },
            "sources": [
                {
                    "source_id": "SRC001",
                    "table_name_with_schema": "inventory.stock",
                    "source_table": "stock",
                    "source_schema": "inventory",
                    "database_source": "ERP_DB",
                    "type_of_load": "Append"
                }
            ],
            "mappings": [],
            "data_model": []
        }

        # 1. Target discovery yields 0 entities
        targets = discover_target_entities(analysis_data, [])
        self.assertEqual(len(targets), 0)

        # 2. DDL contains 0 CREATE TABLE statements and contains TARGET ENTITY NOT DEFINED
        ddl = generate_target_ddl("public", "postgresql", analysis_data["sources"], {}, [], {}, analysis_data)
        self.assertIn("TARGET ENTITY NOT DEFINED", ddl)
        self.assertNotIn("CREATE TABLE", ddl)

        # 3. Transformation SQL contains TARGET ENTITY NOT DEFINED
        sql = generate_transformation_sql("public", "postgresql", analysis_data["sources"], {}, [], [], analysis_data["control_overview"], analysis_data)
        self.assertIn("TARGET ENTITY NOT DEFINED", sql)
        self.assertNotIn("INSERT INTO", sql)

    def test_hla_d_explicit_staging_and_target_dimension(self):
        """
        HLA D:
        Source: CORE_DB.accounts.account_ledger
        Explicit Staging Stage in HLA: customer_stage
        Explicit Target Stage in HLA: customer_dimension
        Generated target tables:
        public.customer_stage
        public.customer_dimension
        """
        analysis_data = {
            "control_overview": {
                "identification": {"control_number": "CTRL-404", "control_title": "Account Processing"},
                "target_schema": "public"
            },
            "sources": [
                {
                    "source_id": "SRC001",
                    "table_name_with_schema": "accounts.account_ledger",
                    "source_table": "account_ledger",
                    "source_schema": "accounts",
                    "database_source": "CORE_DB"
                }
            ],
            "data_model": [
                {
                    "dataset_table_entity_name": "customer_stage",
                    "stage": "Staging",
                    "load_type": "Truncate & load",
                    "columns": [{"name": "account_id", "type": "VARCHAR(50)"}, {"name": "balance", "type": "NUMERIC(15,2)"}]
                },
                {
                    "dataset_table_entity_name": "customer_dimension",
                    "stage": "Target Dimension",
                    "load_type": "Append",
                    "columns": [{"name": "account_id", "type": "VARCHAR(50)"}, {"name": "dim_key", "type": "BIGINT"}]
                }
            ]
        }

        targets = discover_target_entities(analysis_data, [])
        target_names = [t["table_name"] for t in targets]
        self.assertEqual(target_names, ["customer_stage", "customer_dimension"])

        ddl = generate_target_ddl("public", "postgresql", analysis_data["sources"], {}, [], {}, analysis_data)
        self.assertIn("CREATE TABLE IF NOT EXISTS public.customer_stage", ddl)
        self.assertIn("CREATE TABLE IF NOT EXISTS public.customer_dimension", ddl)
        self.assertNotIn("accounts_account_ledger", ddl)
        self.assertNotIn("core_db", ddl)

    def test_load_source_data_into_target_skips_unreplicated_sources(self):
        """
        Verify that _load_source_data_into_target does not fail with NoSuchTableError
        when target schema only has document-defined targets (Source != Target).
        """
        from app import _load_source_data_into_target

        sources = [
            {"source_id": "SRC001", "database": "CRM_DB", "schema_name": "customer", "source_table": "customer_master"},
            {"source_id": "SRC002", "database": "SALES_DB", "schema_name": "sales", "source_table": "sales_transaction"},
            {"source_id": "SRC003", "database": "ERP_DB", "schema_name": "inventory", "source_table": "inventory_snapshot"},
            {"source_id": "SRC004", "database": "NETWORK_DB", "schema_name": "network", "source_table": "device_events"},
        ]
        target_config = {"db_type": "sqlite", "database_name": ":memory:"}
        res = _load_source_data_into_target([], sources, target_config, "public", "test-exec-id")
        self.assertEqual(res["rows"], 0)
        self.assertEqual(res["errors"], [])


if __name__ == "__main__":
    unittest.main()
