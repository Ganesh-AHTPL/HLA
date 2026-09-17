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

    def test_dependency_validation_against_existing_tables(self):
        dep_resolver = DependencyResolver(self.engine)
        context = ControlContext(
            control_id=99,
            control_name="Integration Test Control"
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
