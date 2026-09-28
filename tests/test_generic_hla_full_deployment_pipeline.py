"""
Comprehensive End-to-End Test for HLA Generic Document-Driven Deployment Pipeline.
Tests:
- HLA Excel parsing (Generic_HLA_Architecture_Template.xlsx)
- Canonical Source Table resolution (no duplicated schema/table names)
- Target entity discovery (Data Model + Mappings + Report Derivations)
- Clean Target DDL generation (no synthetic config_tables or ctrl_* tables)
- Physical PostgreSQL DDL execution & table creation
- Source data extraction, HLA rule validation, exception routing, and target loading
- Direct SQL row count verification on live PostgreSQL target tables
"""

import os
import unittest
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, text, inspect
from backend.core.semantic_analyzer import SemanticAnalyzer
from target_logic_builder import (
    discover_target_entities,
    generate_target_ddl,
    deploy_target_ddl,
    parse_canonical_table_ref
)
from db_fetcher import get_env_db_password, build_connection_url
from app import _load_source_data_into_target


class TestGenericHLAFullDeploymentPipeline(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.excel_path = "uploads/projects/9/Generic_HLA_Architecture_Template.xlsx"
        cls.target_config = {
            "db_type": "postgresql",
            "host": os.getenv("PGHOST", "localhost"),
            "port": int(os.getenv("PGPORT", "5432")),
            "database_name": os.getenv("PGDATABASE", "hla_db"),
            "username": os.getenv("PGUSER", "postgres"),
            "password": get_env_db_password(),
            "schema_name": "public"
        }
        cls.target_url = build_connection_url(cls.target_config)
        cls.engine = create_engine(cls.target_url)

    def test_01_canonical_table_reference_resolution(self):
        """Verify table references are canonically resolved without double-prepending."""
        ref1 = parse_canonical_table_ref("customer.customer_master", default_schema="customer", default_source="CRM_DB")
        self.assertEqual(ref1["schema"], "customer")
        self.assertEqual(ref1["table"], "customer_master")
        self.assertNotIn("customer_customer_master", ref1["table"])

        ref2 = parse_canonical_table_ref("sales.sales_transaction", default_schema="sales", default_source="SALES_DB")
        self.assertEqual(ref2["schema"], "sales")
        self.assertEqual(ref2["table"], "sales_transaction")
        self.assertNotIn("sales_sales_transaction", ref2["table"])

        ref3 = parse_canonical_table_ref("CRM_DB.customer.customer_master")
        self.assertEqual(ref3["source"], "CRM_DB")
        self.assertEqual(ref3["schema"], "customer")
        self.assertEqual(ref3["table"], "customer_master")

    def test_02_dynamic_target_discovery_no_synthetic_tables(self):
        """Verify target entities are discovered strictly from HLA document with no invented tables."""
        analysis = SemanticAnalyzer.analyze_workbook(self.excel_path)
        targets = discover_target_entities(analysis, analysis.get("mappings"))
        target_names = [t["table_name"] for t in targets]

        # Expected HLA targets from Data Model & Report Derivation
        self.assertIn("stg_customer", target_names)
        self.assertIn("stg_sales", target_names)
        self.assertIn("stg_inventory", target_names)
        self.assertIn("customer_sales_summary", target_names)
        self.assertIn("data_quality_exceptions", target_names)

        # Prohibited synthetic tables
        self.assertNotIn("config_tables", target_names)
        self.assertNotIn("ctrl_balanced_dataset", target_names)
        self.assertNotIn("ctrl_recon_exceptions", target_names)
        self.assertNotIn("ctrl_recon_matches", target_names)
        self.assertNotIn("stg_customer_customer_master", target_names)
        self.assertNotIn("stg_sales_sales_transaction", target_names)

    def test_03_target_ddl_and_physical_creation(self):
        """Verify DDL is generated and physically executed on PostgreSQL."""
        analysis = SemanticAnalyzer.analyze_workbook(self.excel_path)
        ddl = generate_target_ddl(
            "public", "postgresql",
            analysis.get("sources"), analysis.get("rules"), analysis.get("mappings"),
            analysis_data=analysis
        )

        # Verify DDL contains clean target table statements
        self.assertIn("CREATE TABLE IF NOT EXISTS public.stg_customer", ddl)
        self.assertIn("CREATE TABLE IF NOT EXISTS public.stg_sales", ddl)
        self.assertIn("CREATE TABLE IF NOT EXISTS public.stg_inventory", ddl)
        self.assertIn("CREATE TABLE IF NOT EXISTS public.customer_sales_summary", ddl)
        self.assertIn("CREATE TABLE IF NOT EXISTS public.data_quality_exceptions", ddl)

        # Drop existing test tables to ensure clean physical creation
        with self.engine.connect() as conn:
            for t in ["stg_customer", "stg_sales", "stg_inventory", "customer_sales_summary", "data_quality_exceptions"]:
                conn.execute(text(f"DROP TABLE IF EXISTS public.{t} CASCADE"))
            conn.commit()

        # Deploy DDL
        success, msg, deployed_tables = deploy_target_ddl(self.target_config, ddl)
        self.assertTrue(success, f"DDL deployment failed: {msg}")

        # Verify tables exist via information_schema
        with self.engine.connect() as conn:
            created_tables = conn.execute(text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            )).scalars().all()
            for expected in ["stg_customer", "stg_sales", "stg_inventory", "customer_sales_summary", "data_quality_exceptions"]:
                self.assertIn(expected, created_tables, f"Table '{expected}' not found in public schema")

    def test_04_source_data_loading_and_physical_verification(self):
        """Verify source data is extracted, HLA rules enforced, and loaded into physical PostgreSQL tables."""
        analysis = SemanticAnalyzer.analyze_workbook(self.excel_path)
        source_configs = [self.target_config]

        # Deploy fresh DDL for clean schema
        ddl = generate_target_ddl(
            "public", "postgresql",
            analysis.get("sources"), analysis.get("rules"), analysis.get("mappings"),
            analysis_data=analysis
        )
        with self.engine.connect() as conn:
            for t in ["stg_customer", "stg_sales", "stg_inventory", "customer_sales_summary", "data_quality_exceptions"]:
                conn.execute(text(f"DROP TABLE IF EXISTS public.{t} CASCADE"))
            conn.commit()
        deploy_target_ddl(self.target_config, ddl)

        # Execute data loading & transformation
        loaded = _load_source_data_into_target(
            source_configs=source_configs,
            sources=analysis.get("sources"),
            target_config=self.target_config,
            target_schema="public",
            execution_id="test-e2e-run",
            analysis_data=analysis
        )

        self.assertGreater(loaded["rows"], 0, "No rows were loaded into target tables")
        self.assertEqual(len(loaded["errors"]), 0, f"Errors encountered during data load: {loaded['errors']}")

        # Verify physical row counts via direct PostgreSQL SQL queries
        with self.engine.connect() as conn:
            stg_cust_cnt = conn.execute(text("SELECT COUNT(*) FROM public.stg_customer")).scalar()
            stg_sales_cnt = conn.execute(text("SELECT COUNT(*) FROM public.stg_sales")).scalar()
            stg_inv_cnt = conn.execute(text("SELECT COUNT(*) FROM public.stg_inventory")).scalar()
            summary_cnt = conn.execute(text("SELECT COUNT(*) FROM public.customer_sales_summary")).scalar()
            exceptions_cnt = conn.execute(text("SELECT COUNT(*) FROM public.data_quality_exceptions")).scalar()

            # Active customers (C001, C002) = 2
            self.assertEqual(stg_cust_cnt, 2, f"Expected 2 rows in stg_customer, found {stg_cust_cnt}")
            # Positive sales transactions = 3
            self.assertEqual(stg_sales_cnt, 3, f"Expected 3 rows in stg_sales, found {stg_sales_cnt}")
            # Non-negative inventory = 2
            self.assertEqual(stg_inv_cnt, 2, f"Expected 2 rows in stg_inventory, found {stg_inv_cnt}")
            # Summary rows for 2 customers = 2
            self.assertEqual(summary_cnt, 2, f"Expected 2 rows in customer_sales_summary, found {summary_cnt}")
            # Filtered/invalid exception records = 4
            self.assertEqual(exceptions_cnt, 4, f"Expected 4 rows in data_quality_exceptions, found {exceptions_cnt}")

            # Verify actual values inside customer_sales_summary
            rows = conn.execute(text("SELECT customer_id, customer_total_sales, customer_transaction_count FROM public.customer_sales_summary ORDER BY customer_id")).fetchall()
            self.assertEqual(rows[0][0], "C001")
            self.assertEqual(float(rows[0][1]), 15500.00)
            self.assertEqual(int(rows[0][2]), 2)

            self.assertEqual(rows[1][0], "C002")
            self.assertEqual(float(rows[1][1]), 2000.00)
            self.assertEqual(int(rows[1][2]), 1)


if __name__ == "__main__":
    unittest.main()
