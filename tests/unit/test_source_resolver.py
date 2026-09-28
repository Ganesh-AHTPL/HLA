"""
Unit tests for SourceRegistry, PhysicalSourceResolver, and ColumnResolver.
"""

import unittest
from backend.source.source_registry import SourceRegistry
from backend.source.source_metadata import AttributeMapping


class TestSourceAndColumnResolver(unittest.TestCase):

    def test_source_registry_dynamic_registration(self):
        reg = SourceRegistry()
        reg.register_stream(
            logical_name="CUSTOMER_STREAM",
            physical_schema="customer",
            physical_table="customer_master",
            source_system="CRM_DB",
            source_id="SRC001"
        )
        stream = reg.get_stream("CUSTOMER_STREAM")
        self.assertIsNotNone(stream)
        self.assertEqual(stream.physical_schema, "customer")
        self.assertEqual(stream.physical_table, "customer_master")
        self.assertEqual(stream.source_system, "CRM_DB")
        self.assertEqual(stream.source_id, "SRC001")

    def test_source_registry_from_analysis(self):
        reg = SourceRegistry()
        analysis_data = {
            "sources": [
                {
                    "source_id": "SRC002",
                    "source_name": "SALES_DB",
                    "schema_name": "sales",
                    "table_name": "sales_transaction",
                    "full_table_name": "sales.sales_transaction"
                }
            ]
        }
        reg.register_sources_from_analysis(analysis_data)
        stream = reg.get_stream("sales.sales_transaction")
        self.assertIsNotNone(stream)
        self.assertEqual(stream.physical_schema, "sales")
        self.assertEqual(stream.physical_table, "sales_transaction")
        self.assertEqual(stream.source_system, "SALES_DB")
        self.assertEqual(stream.source_id, "SRC002")

    def test_source_registry_custom_overrides(self):
        custom = {
            "custom_stream": ("custom_schema", "custom_table", "Custom System")
        }
        reg = SourceRegistry(custom_mappings=custom)
        stream = reg.get_stream("custom_stream")
        self.assertIsNotNone(stream)
        self.assertEqual(stream.physical_schema, "custom_schema")
        self.assertEqual(stream.physical_table, "custom_table")


if __name__ == "__main__":
    unittest.main()
