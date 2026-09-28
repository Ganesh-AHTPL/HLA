"""
test_generic_table_column_order.py
----------------------------------
Test suite validating that table generation produces clean, 100% document-driven
column definitions strictly from the HLA specification and source databases.

GUARANTEES:
- No synthetic control envelope columns (ctrl_id, exec_seq, execution_schedule, etc.).
- No config_tables created unless explicitly modeled as a physical target entity.
- Source/business columns are preserved with their accurate data types.
- Pure document-driven DDL generation.
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from target_logic_builder import (
    generate_source_tables_ddl,
    generate_target_ddl,
    build_table_columns_with_standard_envelope,
    _parse_required_objects_from_ddl,
)


class TestGenericTableColumnOrder(unittest.TestCase):

    def test_01_direct_column_formatting(self):
        """Verify column definitions format directly without synthetic control envelopes."""
        mid_cols = [
            "    customer_code VARCHAR(50) NOT NULL",
            "    balance_amt NUMERIC(18,2)",
            "    status_flag VARCHAR(10) DEFAULT 'ACTIVE'",
        ]
        res = build_table_columns_with_standard_envelope(mid_cols, target_dialect="postgresql")
        body = ",\n".join(res)
        ddl = f"CREATE TABLE test_schema.test_tbl (\n{body}\n);"
        parsed = _parse_required_objects_from_ddl(ddl)
        self.assertEqual(len(parsed), 1)
        col_names = [c["name"].lower() for c in parsed[0]["columns"]]
        self.assertEqual(col_names, ["customer_code", "balance_amt", "status_flag"])
        self.assertNotIn("ctrl_id", col_names)
        self.assertNotIn("exec_seq", col_names)

    def test_02_target_ddl_generation_pure_hla(self):
        """Verify generate_target_ddl outputs clean target objects without synthetic control columns."""
        analysis = {
            "data_model": [
                {
                    "dataset_table_entity_name": "customer_summary",
                    "stage": "Curated",
                    "load_type": "Truncate and load",
                    "description": "Customer summary reporting",
                    "columns": [
                        {"name": "customer_id", "type": "VARCHAR(50)", "nullable": "NOT NULL"},
                        {"name": "customer_name", "type": "VARCHAR(100)"},
                        {"name": "total_sales", "type": "DECIMAL(18,2)"}
                    ]
                }
            ]
        }
        ddl = generate_target_ddl("public", "postgresql", [], {}, [], analysis_data=analysis)
        self.assertIn("CREATE TABLE IF NOT EXISTS public.customer_summary", ddl)
        self.assertIn("customer_id VARCHAR(50)", ddl)
        self.assertIn("customer_name VARCHAR(100)", ddl)
        self.assertIn("total_sales DECIMAL(18,2)", ddl)
        self.assertNotIn("ctrl_id", ddl)
        self.assertNotIn("exec_seq", ddl)
        self.assertNotIn("config_tables", ddl)

    def test_03_no_config_tables_as_target(self):
        """Verify Config Tables sheet does NOT produce a physical table unless in Data Model."""
        analysis = {
            "config_tables": [
                {"config_table_name": "cfg_params", "target_column": "param_val"}
            ],
            "data_model": [
                {
                    "dataset_table_entity_name": "stg_orders",
                    "stage": "Staging",
                    "load_type": "Append",
                    "columns": [
                        {"name": "order_id", "type": "VARCHAR(50)"},
                        {"name": "order_amount", "type": "DECIMAL(18,2)"}
                    ]
                }
            ]
        }
        ddl = generate_target_ddl("public", "postgresql", [], {}, [], analysis_data=analysis)
        self.assertIn("CREATE TABLE IF NOT EXISTS public.stg_orders", ddl)
        self.assertNotIn("CREATE TABLE IF NOT EXISTS public.cfg_params", ddl)
        self.assertNotIn("config_tables", ddl)


if __name__ == "__main__":
    unittest.main()
