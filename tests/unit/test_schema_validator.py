"""
Unit tests for ColumnOrderValidator, DDLGenerator, and SchemaValidator.
"""

import unittest
from backend.schema.column_order_validator import ColumnOrderValidator
from backend.schema.ddl_generator import DDLGenerator
from backend.schema.schema_validator import SchemaValidator
from backend.core.constants import PLATFORM_HEADER_NAMES, PLATFORM_FOOTER_NAMES


class TestSchemaAndDDL(unittest.TestCase):

    def test_enforce_envelope_order(self):
        biz_cols = [("hostname", "VARCHAR(100)"), ("status", "VARCHAR(50)")]
        full_envelope = ColumnOrderValidator.enforce_envelope(biz_cols)

        col_names = [c[0] for c in full_envelope]
        # Verify first 4
        self.assertEqual(col_names[:4], PLATFORM_HEADER_NAMES)
        # Verify business
        self.assertEqual(col_names[4:6], ["hostname", "status"])
        # Verify last 4
        self.assertEqual(col_names[-4:], PLATFORM_FOOTER_NAMES)

    def test_ddl_generator_output(self):
        biz_cols = [("vdom", "VARCHAR(100)"), ("ip", "VARCHAR(50)")]
        ddl = DDLGenerator.generate_create_table_ddl("ra_ctrl", "ctrl_99_source_vdom", biz_cols)

        self.assertIn('CREATE TABLE IF NOT EXISTS "ra_ctrl"."ctrl_99_source_vdom"', ddl)
        self.assertIn('"ctrl_id" INTEGER', ddl)
        self.assertIn('"exec_seq" INTEGER', ddl)
        self.assertIn('"execution_date" DATE', ddl)
        self.assertIn('"execution_schedule" VARCHAR(50)', ddl)
        self.assertIn('"vdom" VARCHAR(100)', ddl)
        self.assertIn('"ip" VARCHAR(50)', ddl)
        self.assertIn('"processing_date" DATE DEFAULT CURRENT_DATE', ddl)

    def test_schema_validator_rejects_external_source_as_target(self):
        for ext_schema in ["cmdb", "pearl", "sfdc", "reports", "ra"]:
            val = SchemaValidator.validate_target_schema_name(ext_schema)
            self.assertFalse(val.is_valid)

        val_ok = SchemaValidator.validate_target_schema_name("ra_ctrl")
        self.assertTrue(val_ok.is_valid)

    def test_ddl_validator_rejects_synthetic_prefixes(self):
        bad_ddl = 'SELECT b.vutm_doos AS app_name FROM tbl;'
        val = SchemaValidator.validate_ddl_statement(bad_ddl)
        self.assertFalse(val.is_valid)
        self.assertTrue(any("b.vutm_doos" in err for err in val.errors))


if __name__ == "__main__":
    unittest.main()
