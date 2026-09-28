"""
Tests for Authoritative Generic Physical Source Resolution.
Verifies ZERO hardcoding and strictly dynamic source resolution for arbitrary sources.
"""

import unittest
from sqlalchemy import create_engine
from backend.core.semantic_analyzer import SemanticAnalyzer
from backend.source.source_metadata import LogicalSourceStream
from backend.source.source_registry import SourceRegistry
from backend.source.physical_source_resolver import PhysicalSourceResolver
from backend.core.exceptions import SourceDependencyMissingError
from backend.sql.sql_generator import SQLGenerator
from backend.core.control_context import ControlContext
from db_fetcher import fetch_table_metadata, find_table_across_databases


class TestGenericSourceResolution(unittest.TestCase):

    def test_semantic_analyzer_extract_sources_generic(self):
        """Verify semantic analyzer parses arbitrary source tables without duplicate prefixes."""
        raw_sheets = {
            "Source Systems": [
                {
                    "Source ID": "SRC001",
                    "Table Name with Schema": "customer.customer_master",
                    "Database / Source": "CRM_DB",
                    "Frequency": "Daily",
                    "Schedule Time": "02:00",
                    "Approximate End Time": "02:30",
                    "Type of load": "Truncate and load",
                    "Active": "Yes"
                },
                {
                    "Source ID": "SRC002",
                    "Table Name with Schema": "sales.sales_transaction",
                    "Database / Source": "SALES_DB",
                    "Frequency": "Hourly",
                    "Schedule Time": "00:15",
                    "Approximate End Time": "00:25",
                    "Type of load": "Incremental Append",
                    "Active": "Yes"
                },
                {
                    "Source ID": "SRC003",
                    "Table Name with Schema": "inventory.inventory_snapshot",
                    "Database / Source": "ERP_DB",
                    "Frequency": "Daily",
                    "Schedule Time": "04:00",
                    "Approximate End Time": "04:45",
                    "Type of load": "Truncate and load",
                    "Active": "Yes"
                },
                {
                    "Source ID": "SRC004",
                    "Table Name with Schema": "network.device_events",
                    "Database / Source": "NETWORK_DB",
                    "Frequency": "Real-Time",
                    "Schedule Time": "Continuous",
                    "Approximate End Time": "-",
                    "Type of load": "Streaming Append",
                    "Active": "Yes"
                },
                {
                    "Source ID": "SRC099",
                    "Table Name with Schema": "finance.invoice_header",
                    "Database / Source": "FINANCE_DB",
                    "Frequency": "Monthly",
                    "Schedule Time": "23:00",
                    "Approximate End Time": "23:50",
                    "Type of load": "Truncate and load",
                    "Active": "Yes"
                },
                {
                    "Source ID": "SRC100",
                    "Table Name with Schema": "ops_db.operations.flight_manifest",
                    "Database / Source": "AIRLINE_OPS",
                    "Frequency": "Daily",
                    "Schedule Time": "01:00",
                    "Approximate End Time": "01:30",
                    "Type of load": "Full Load",
                    "Active": "Yes"
                }
            ]
        }

        analyzer = SemanticAnalyzer()
        sources, _ = analyzer._extract_sources(raw_sheets)

        self.assertEqual(len(sources), 6)

        # Verify SRC001
        s1 = sources[0]
        self.assertEqual(s1["source_id"], "SRC001")
        self.assertEqual(s1["source_name"], "CRM_DB")
        self.assertEqual(s1["database"], "CRM_DB")
        self.assertEqual(s1["schema_name"], "customer")
        self.assertEqual(s1["table_name"], "customer_master")
        self.assertEqual(s1["full_table_name"], "customer.customer_master")
        self.assertNotIn("customer.customer.customer_master", s1["full_table_name"])
        self.assertNotIn("CRM_DB.customer.customer_master", s1["full_table_name"])

        # Verify SRC002
        s2 = sources[1]
        self.assertEqual(s2["source_id"], "SRC002")
        self.assertEqual(s2["source_name"], "SALES_DB")
        self.assertEqual(s2["schema_name"], "sales")
        self.assertEqual(s2["table_name"], "sales_transaction")
        self.assertEqual(s2["full_table_name"], "sales.sales_transaction")
        self.assertNotIn("sales.sales.sales_transaction", s2["full_table_name"])

        # Verify SRC003
        s3 = sources[2]
        self.assertEqual(s3["source_id"], "SRC003")
        self.assertEqual(s3["source_name"], "ERP_DB")
        self.assertEqual(s3["schema_name"], "inventory")
        self.assertEqual(s3["table_name"], "inventory_snapshot")
        self.assertEqual(s3["full_table_name"], "inventory.inventory_snapshot")
        self.assertNotIn("inventory.inventory.inventory_snapshot", s3["full_table_name"])

        # Verify SRC004
        s4 = sources[3]
        self.assertEqual(s4["source_id"], "SRC004")
        self.assertEqual(s4["source_name"], "NETWORK_DB")
        self.assertEqual(s4["schema_name"], "network")
        self.assertEqual(s4["table_name"], "device_events")
        self.assertEqual(s4["full_table_name"], "network.device_events")
        self.assertNotIn("network.network.device_events", s4["full_table_name"])

        # Verify dynamic finance source
        s5 = sources[4]
        self.assertEqual(s5["source_id"], "SRC099")
        self.assertEqual(s5["source_name"], "FINANCE_DB")
        self.assertEqual(s5["schema_name"], "finance")
        self.assertEqual(s5["table_name"], "invoice_header")
        self.assertEqual(s5["full_table_name"], "finance.invoice_header")

        # Verify 3-part database.schema.table
        s6 = sources[5]
        self.assertEqual(s6["source_id"], "SRC100")
        self.assertEqual(s6["database"], "AIRLINE_OPS")
        self.assertEqual(s6["schema_name"], "operations")
        self.assertEqual(s6["table_name"], "flight_manifest")
        self.assertEqual(s6["full_table_name"], "operations.flight_manifest")

    def test_physical_source_resolver_diagnostics(self):
        """Verify PhysicalSourceResolver emits authoritative diagnostic messages."""
        engine = create_engine("sqlite:///:memory:")
        registry = SourceRegistry()

        # Stream not configured in registry
        resolver = PhysicalSourceResolver(engine, registry)
        with self.assertRaises(SourceDependencyMissingError) as excinfo:
            resolver.resolve_stream("UNCONFIGURED_STREAM")
        self.assertIn("SOURCE CONNECTION NOT CONFIGURED", str(excinfo.exception))
        self.assertIn("UNCONFIGURED_STREAM", str(excinfo.exception))

        # Stream configured, but table not found in DB
        stream = LogicalSourceStream(
            stream_name="SRC_CRM",
            source_id="SRC001",
            source_system="CRM_DB",
            physical_schema="customer",
            physical_table="customer_master"
        )
        registry.register_stream(
            stream_name="SRC_CRM",
            schema_name="customer",
            table_name="customer_master",
            source_system="CRM_DB",
            source_id="SRC001"
        )

        with self.assertRaises(SourceDependencyMissingError) as excinfo2:
            resolver.resolve_stream("SRC_CRM")
        err_str = str(excinfo2.exception)
        self.assertIn("SOURCE TABLE NOT FOUND", err_str)
        self.assertIn("Source ID: SRC001", err_str)
        self.assertIn("Source: CRM_DB", err_str)
        self.assertIn("Schema: customer", err_str)
        self.assertIn("Table: customer_master", err_str)
        self.assertNotIn("customer.customer.customer_master", err_str)

    def test_find_table_across_databases_diagnostics(self):
        """Verify find_table_across_databases returns clear diagnostic structures."""
        # No connection configured for source
        res1 = find_table_across_databases([], "customer", "customer_master", source_system="CRM_DB", source_id="SRC001")
        self.assertFalse(res1["table_found"])
        self.assertEqual(res1["status"], "connection_not_configured")
        self.assertIn("SOURCE CONNECTION NOT CONFIGURED", res1["message"])
        self.assertIn("CRM_DB", res1["message"])

        # Connection configured (sqlite memory), table not found / schema not found
        cfg = {"db_type": "sqlite", "host": ":memory:", "database_name": "CRM_DB"}
        res2 = find_table_across_databases([cfg], "customer", "customer_master", source_system="CRM_DB", source_id="SRC001")
        self.assertFalse(res2["table_found"])
        self.assertIn(res2["status"], ["table_not_found", "schema_not_found"])
        self.assertIn("SRC001", res2["message"])
        self.assertIn("CRM_DB", res2["message"])
        self.assertIn("customer", res2["message"])
        self.assertIn("customer_master", res2["message"])

    def test_sql_generator_stage1_never_duplicates_schema(self):
        """Verify Stage 1 SQL generation creates strictly clean FROM \"schema\".\"table\" without duplication."""
        ctx = ControlContext(control_id=101, control_name="CTRL-101", target_schema="recon_target")

        _, sql = SQLGenerator.generate_stage1_acquisition_sql(
            context=ctx,
            stream_name="CUSTOMER_FEED",
            source_schema="customer",
            source_table="customer_master",
            source_columns=["cust_id", "cust_name", "credit_limit"]
        )

        self.assertIn('FROM "customer"."customer_master" s;', sql)
        self.assertNotIn('"customer"."customer.customer_master"', sql)
        self.assertNotIn('"customer"."customer"."customer_master"', sql)
        self.assertNotIn('"CRM_DB"."customer"."customer_master"', sql)


if __name__ == "__main__":
    unittest.main()
