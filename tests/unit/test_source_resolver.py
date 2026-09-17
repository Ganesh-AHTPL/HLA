"""
Unit tests for SourceRegistry, PhysicalSourceResolver, and ColumnResolver.
"""

import unittest
from backend.source.source_registry import SourceRegistry
from backend.source.source_metadata import AttributeMapping


class TestSourceAndColumnResolver(unittest.TestCase):

    def test_source_registry_defaults(self):
        reg = SourceRegistry()
        stream = reg.get_stream("VUTM/DOOS")
        self.assertIsNotNone(stream)
        self.assertEqual(stream.physical_schema, "reports")
        self.assertEqual(stream.physical_table, "dl_vdom_firewall_audit_report")

        stream_cmdb = reg.get_stream("CMDB")
        self.assertIsNotNone(stream_cmdb)
        self.assertEqual(stream_cmdb.physical_schema, "cmdb")
        self.assertEqual(stream_cmdb.physical_table, "dl_itsm_cmdb_daily_dump")

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
