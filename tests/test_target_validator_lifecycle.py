import unittest
from target_logic_builder import (
    validate_statement_against_target_schema,
    validate_transformation_pipeline_against_schema,
    reconcile_objects,
    _format_schema_prefix,
    _parse_required_objects_from_ddl
)

class TestTargetValidatorLifecycle(unittest.TestCase):
    """
    Tests dynamic target object lifecycle:
    - Missing target tables defined in DDL must be recognized as valid CREATE actions
    - Only truly undefined tables (neither in target DB nor DDL) are flagged
    - Zero hardcoded table or schema names
    """

    def test_missing_target_table_in_ddl_is_valid_for_insert(self):
        """
        When target tables do NOT exist yet in the physical target database,
        but are defined in the generated target DDL, pre-execution validator
        MUST recognize them as valid targets and allow deployment.
        """
        target_schema = "Unique"
        ddl_script = """
        CREATE SCHEMA IF NOT EXISTS "Unique";

        CREATE TABLE IF NOT EXISTS "Unique".order_ingest (
            order_id VARCHAR(50),
            total_amount NUMERIC(10,2),
            execution_id VARCHAR(64)
        );

        CREATE TABLE IF NOT EXISTS "Unique".order_flagged (
            flag_id VARCHAR(50),
            reason TEXT,
            execution_id VARCHAR(64)
        );
        """
        # Physical target metadata (empty target schema before deployment)
        physical_target_meta = {
            "schema_exists": True,
            "tables": {}  # Empty: tables not yet physically created
        }

        # DDL parsed metadata
        req_objs = _parse_required_objects_from_ddl(ddl_script)
        ddl_target_meta = {"tables": {}}
        for obj in req_objs:
            b_name = obj["bare_name"].lower()
            cols = obj.get("columns", [])
            ddl_target_meta["tables"][b_name] = {
                "columns": cols,
                "column_names": {c["name"].lower() for c in cols}
            }

        # Statement targeting new DDL table
        stmt = 'INSERT INTO "Unique".order_ingest (order_id, total_amount, execution_id) VALUES (\'1\', 10.5, \'exec-1\');'
        is_valid, diag = validate_statement_against_target_schema(
            physical_target_meta,
            target_schema,
            stmt,
            ddl_target_meta=ddl_target_meta
        )
        self.assertTrue(is_valid, f"Validation should succeed for DDL-defined table: {diag}")

    def test_missing_table_not_in_ddl_fails_validation(self):
        """
        When a table is neither in the physical target DB nor in the generated DDL,
        the validator must properly report it.
        """
        target_schema = "Unique"
        physical_target_meta = {"schema_exists": True, "tables": {}}
        ddl_target_meta = {"tables": {}}

        stmt = 'INSERT INTO "Unique".non_existent_table (col_a) VALUES (1);'
        is_valid, diag = validate_statement_against_target_schema(
            physical_target_meta,
            target_schema,
            stmt,
            ddl_target_meta=ddl_target_meta
        )
        self.assertFalse(is_valid)
        self.assertIn("does not exist in target schema 'Unique' and is not defined in target DDL", diag)

    def test_dynamic_schema_and_table_reconciliation(self):
        """
        Reconciliation must accurately report MISSING -> CREATE when tables don't exist,
        and REUSE when compatible tables exist.
        """
        target_schema = "custom_dynamic_schema"
        ddl_script = """
        CREATE TABLE IF NOT EXISTS custom_dynamic_schema.payload_stage (
            payload_id VARCHAR(50),
            payload_data TEXT
        );
        """
        # Existing target meta contains payload_stage with compatible columns
        live_meta = {
            "schema_exists": True,
            "tables": {
                "payload_stage": {
                    "columns": [{"name": "payload_id", "type": "VARCHAR(50)"}, {"name": "payload_data", "type": "TEXT"}],
                    "column_names": {"payload_id", "payload_data"}
                }
            }
        }
        recon = reconcile_objects(live_meta, ddl_script, target_schema=target_schema)
        self.assertEqual(recon["counts"]["invalid"], 0)
        self.assertEqual(recon["counts"]["existing"], 1)

    def test_schema_formatting_respects_reserved_words(self):
        """
        SQL keywords (like 'Unique') are safely quoted, while normal identifiers remain clean.
        """
        create_stmt_res, prefix_res = _format_schema_prefix("Unique", "postgresql")
        self.assertEqual(prefix_res, '"Unique".')

        create_stmt_std, prefix_std = _format_schema_prefix("sales", "postgresql")
        self.assertEqual(prefix_std, 'sales.')


if __name__ == "__main__":
    unittest.main()
