"""
Integration tests for source dependency resolution against PostgreSQL.
"""

import unittest
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import create_engine
from backend.core.control_context import ControlContext
from backend.source.dependency_resolver import DependencyResolver
from backend.source.source_metadata import AttributeMapping
from config import Config


class TestSourceDependencyIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(Config.SQLALCHEMY_DATABASE_URI)
        from sqlalchemy import text
        with cls.engine.begin() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS reports"))
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS cmdb"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS reports.dl_vdom_firewall_audit_report (application_name VARCHAR(255))"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS cmdb.dl_itsm_cmdb_daily_dump (cmdb_production_ip VARCHAR(255))"))

    def test_dependency_validation_against_existing_tables(self):
        dep_resolver = DependencyResolver(self.engine)
        context = ControlContext(
            control_id=99,
            control_name="Integration Test Control"
        )

        # Register dynamic test streams in registry
        dep_resolver.source_resolver.registry.register_stream(
            "VUTM/DOOS", "reports", "dl_vdom_firewall_audit_report", "Reports DB", "SRC001"
        )
        dep_resolver.source_resolver.registry.register_stream(
            "CMDB", "cmdb", "dl_itsm_cmdb_daily_dump", "ITSM DB", "SRC002"
        )

        mappings = [
            AttributeMapping(
                logical_attribute_name="Application_Name",
                logical_source_stream="VUTM/DOOS",
                target_field_name="application_name"
            ),
            AttributeMapping(
                logical_attribute_name="CMDB_Production_IP",
                logical_source_stream="CMDB",
                target_field_name="cmdb_production_ip"
            )
        ]

        val = dep_resolver.validate_dependencies(
            context=context,
            required_streams=["VUTM/DOOS", "CMDB"],
            attribute_mappings=mappings
        )

        # Check that introspection resolved the streams and attributes
        self.assertIn("vutm/doos", val.details.get("resolved_streams", []))
        self.assertIn("cmdb", val.details.get("resolved_streams", []))

    def test_missing_source_table_fails_gracefully(self):
        dep_resolver = DependencyResolver(self.engine)
        context = ControlContext(control_id=99, control_name="Missing Table Control")

        # Register non-existent table in registry
        dep_resolver.source_resolver.registry.register_stream(
            "GHOST_STREAM", "ghost_schema", "non_existent_table"
        )

        val = dep_resolver.validate_dependencies(
            context=context,
            required_streams=["GHOST_STREAM"],
            attribute_mappings=[]
        )

        self.assertFalse(val.is_valid)
        self.assertTrue(any("SOURCE_DEPENDENCY_MISSING" in err for err in val.errors))


if __name__ == "__main__":
    unittest.main()
