"""
Unit tests for SQLGenerator across all 8 Stages.
"""

import unittest
from datetime import date
from backend.core.control_context import ControlContext
from backend.sql.sql_generator import SQLGenerator
from backend.core.constants import FORBIDDEN_SYNTHETIC_COLUMN_PREFIXES


class TestSQLGenerator(unittest.TestCase):

    def setUp(self):
        self.context = ControlContext(
            control_id=99,
            control_name="Generic Test Control",
            hla_version="2.1",
            target_schema="ra_ctrl",
            execution_date=date(2026, 9, 17),
            execution_schedule="DAILY",
            exec_seq=5,
            processing_date=date(2026, 9, 17)
        )

    def test_stage1_acquisition_sql(self):
        tbl, sql = SQLGenerator.generate_stage1_acquisition_sql(
            context=self.context,
            stream_name="VUTM",
            source_schema="reports",
            source_table="dl_vdom_firewall_audit_report",
            source_columns=["vdom", "hostname", "ip"]
        )
        self.assertEqual(tbl, "CTRL_99_SOURCE_DATASET_VUTM")
        self.assertIn('INSERT INTO "ra_ctrl"."CTRL_99_SOURCE_DATASET_VUTM"', sql)
        self.assertIn('"ctrl_id"', sql)
        self.assertIn(':control_id', sql)
        self.assertIn('s."vdom"', sql)
        self.assertIn('s."hostname"', sql)
        self.assertIn('FROM "reports"."dl_vdom_firewall_audit_report"', sql)

    def test_stage4_reconciliation_sql(self):
        tbl, sql = SQLGenerator.generate_stage4_reconciliation_sql(
            context=self.context,
            primary_stream="VUTM",
            secondary_stream="CMDB",
            recon_keys=["ip"],
            primary_columns=["vdom", "ip"],
            secondary_columns=["profile_name", "ip"]
        )
        self.assertEqual(tbl, "CTRL_99_WORKING_DATASET_RL")
        self.assertIn('FULL OUTER JOIN', sql)
        self.assertIn("CASE \n    WHEN a.\"ip\" IS NOT NULL AND b.\"ip\" IS NOT NULL THEN 'YY'", sql)
        self.assertIn("WHEN a.\"ip\" IS NOT NULL THEN 'YN'", sql)
        self.assertIn("ELSE 'NY'", sql)

    def test_no_synthetic_prefixes_in_generated_sql(self):
        for stage_fn in [
            lambda: SQLGenerator.generate_stage1_acquisition_sql(self.context, "CMDB", "cmdb", "dl_itsm", ["ip"]),
            lambda: SQLGenerator.generate_stage4_reconciliation_sql(self.context, "VUTM", "CMDB", ["ip"], [], []),
            lambda: SQLGenerator.generate_stage5_kri_sql(self.context),
            lambda: SQLGenerator.generate_stage6_work_item_current_run_sql(self.context),
            lambda: SQLGenerator.generate_stage7_historical_work_item_sql(self.context),
            lambda: SQLGenerator.generate_stage8_report_summary_sql(self.context),
        ]:
            _, sql = stage_fn()
            for prefix in FORBIDDEN_SYNTHETIC_COLUMN_PREFIXES:
                self.assertNotIn(prefix, sql.lower())


if __name__ == "__main__":
    unittest.main()
