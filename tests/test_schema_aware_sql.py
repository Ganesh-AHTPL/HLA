"""
test_schema_aware_sql.py
------------------------
Comprehensive test suite for the generic schema-aware SQL generator and
pre-execution validation layer.

Covers all requirements:
  TEST 1:  Table has all requested columns (SQL generated and validated successfully)
  TEST 2:  Table does not have one requested column (Validation detects and reports mismatch)
  TEST 3:  Table has completely different columns (No generic columns blindly accepted)
  TEST 4:  Table has audit columns (Audit values populated only for columns actually defined)
  TEST 5:  Table has no audit columns (SQL still works without injecting non-existent columns)
  TEST 6:  Table has nullable columns (Nullable columns handled properly)
  TEST 7:  Table has NOT NULL columns without defaults (Validation flags missing required columns)
  TEST 8:  Table has identity/generated columns (Generator does not insert into generated columns)
  TEST 9:  Table has column defaults (Allows DB defaults to apply instead of requiring explicit insert)
  TEST 10: Two tables have completely different schemas (Each receives independent schema-aware SQL)
  TEST 11: Multiple schemas contain tables with the same name (Schema-qualified metadata lookup verified)
  TEST 12: Table or column does not exist (Clear diagnostic error before SQL execution; aborts before write)
  TEST 13: End-to-End Generator Master-Table Protection (Pre-existing master tables preserved without generic dummy inserts)

Run:
  python tests/test_schema_aware_sql.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from target_logic_builder import (
    extract_statement_target_and_columns,
    validate_statement_against_target_schema,
    generate_transformation_sql,
    _split_sql_statements,
    _has_executable_sql,
)


def _build_mock_meta(tables_dict: dict, schema_name: str = "ra_ctrl.test_schema") -> dict:
    """Helper to build target schema metadata dict mimicking inspect_target_schema."""
    formatted_tables = {}
    for tbl_name, col_list in tables_dict.items():
        tbl_lower = tbl_name.lower()
        cols = []
        for c in col_list:
            if isinstance(c, str):
                cols.append({
                    "name": c.lower(),
                    "data_type": "varchar(255)",
                    "is_nullable": True,
                    "default": None,
                    "is_identity": False,
                    "is_generated": False,
                })
            elif isinstance(c, dict):
                cols.append({
                    "name": c["name"].lower(),
                    "data_type": c.get("data_type", "varchar(255)").lower(),
                    "is_nullable": c.get("is_nullable", True),
                    "default": c.get("default", None),
                    "is_identity": c.get("is_identity", False),
                    "is_generated": c.get("is_generated", False),
                })
        formatted_tables[tbl_lower] = {
            "exists": True,
            "columns": cols,
            "column_names": {c["name"] for c in cols},
        }

    return {
        "schema_exists": True,
        "schema_name": schema_name,
        "tables": formatted_tables,
    }


# ------------------------------------------------------------------------------
# TEST 1: Table has all requested columns
# ------------------------------------------------------------------------------
def test_1_table_has_all_requested_columns():
    meta = _build_mock_meta({
        "customer_orders": ["order_id", "customer_name", "amount", "order_date"]
    })
    stmt = """
    INSERT INTO "ra_ctrl.test_schema".customer_orders (order_id, customer_name, amount, order_date)
    VALUES (101, 'Acme Corp', 99.95, CURRENT_DATE);
    """
    valid, diag = validate_statement_against_target_schema(meta, "ra_ctrl.test_schema", stmt)
    assert valid is True, f"Expected validation success, got: {diag}"
    print("TEST 1 PASS - Table has all requested columns: SQL validated successfully")


# ------------------------------------------------------------------------------
# TEST 2: Table does not have one requested column
# ------------------------------------------------------------------------------
def test_2_table_missing_one_requested_column():
    meta = _build_mock_meta({
        "ctrl_config": ["ctrl_id", "control_name", "execution_schedule"]
    })
    # Attempting to insert batch_id which does not exist in ctrl_config
    stmt = """
    INSERT INTO "ra_ctrl.test_schema".ctrl_config (ctrl_id, control_name, batch_id)
    VALUES ('C1', 'Recon', 'BATCH_001');
    """
    valid, diag = validate_statement_against_target_schema(meta, "ra_ctrl.test_schema", stmt)
    assert valid is False, "Expected validation failure for missing column"
    assert "Columns not present in target:" in diag
    assert "batch_id" in diag
    assert "[SCHEMA VALIDATION FAILED]" in diag
    print("TEST 2 PASS - Table missing one requested column: Detected and reported mismatch")


# ------------------------------------------------------------------------------
# TEST 3: Table has completely different columns
# ------------------------------------------------------------------------------
def test_3_table_has_completely_different_columns():
    # Target table is ctrl_config with only configuration attributes
    meta = _build_mock_meta({
        "ctrl_config": ["config_id", "param_key", "param_val"]
    })
    # SQL generator attempting to inject generic system columns
    stmt = """
    INSERT INTO "ra_ctrl.test_schema".ctrl_config (batch_id, execution_cycle_date, record_status, source_reference, kri_flag)
    SELECT NULL, CURRENT_DATE, 'ACTIVE', 'ctrl_config', 'NONE';
    """
    valid, diag = validate_statement_against_target_schema(meta, "ra_ctrl.test_schema", stmt)
    assert valid is False, "Expected validation failure for completely mismatched columns"
    assert "batch_id" in diag
    assert "execution_cycle_date" in diag
    assert "record_status" in diag
    assert "source_reference" in diag
    assert "kri_flag" in diag
    print("TEST 3 PASS - Table has completely different columns: Generic columns rejected")


# ------------------------------------------------------------------------------
# TEST 4: Table has audit columns
# ------------------------------------------------------------------------------
def test_4_table_has_audit_columns():
    meta = _build_mock_meta({
        "recon_results": ["id", "result_status", "batch_id", "created_at"]
    })
    stmt = """
    INSERT INTO "ra_ctrl.test_schema".recon_results (id, result_status, batch_id, created_at)
    VALUES (1, 'MATCH', 'B001', CURRENT_TIMESTAMP);
    """
    valid, diag = validate_statement_against_target_schema(meta, "ra_ctrl.test_schema", stmt)
    assert valid is True, f"Expected success for table with defined audit columns: {diag}"
    print("TEST 4 PASS - Table has audit columns: Populated and validated properly")


# ------------------------------------------------------------------------------
# TEST 5: Table has no audit columns
# ------------------------------------------------------------------------------
def test_5_table_has_no_audit_columns():
    meta = _build_mock_meta({
        "simple_lookup": ["code", "description"]
    })
    stmt = """
    INSERT INTO "ra_ctrl.test_schema".simple_lookup (code, description)
    VALUES ('USD', 'US Dollar');
    """
    valid, diag = validate_statement_against_target_schema(meta, "ra_ctrl.test_schema", stmt)
    assert valid is True, f"Expected success when table has no audit columns: {diag}"
    print("TEST 5 PASS - Table has no audit columns: SQL succeeds without injecting audit fields")


# ------------------------------------------------------------------------------
# TEST 6: Table has nullable columns
# ------------------------------------------------------------------------------
def test_6_table_has_nullable_columns():
    meta = _build_mock_meta({
        "products": [
            {"name": "product_id", "is_nullable": False, "default": None},
            {"name": "product_name", "is_nullable": False, "default": None},
            {"name": "discount_notes", "is_nullable": True, "default": None},
            {"name": "expiry_date", "is_nullable": True, "default": None},
        ]
    })
    # Omission of nullable columns in INSERT is fully valid
    stmt = """
    INSERT INTO "ra_ctrl.test_schema".products (product_id, product_name)
    VALUES ('P100', 'Laptop');
    """
    valid, diag = validate_statement_against_target_schema(meta, "ra_ctrl.test_schema", stmt, strict_not_null=True)
    assert valid is True, f"Expected success when omitting nullable columns: {diag}"
    print("TEST 6 PASS - Table has nullable columns: Handled correctly")


# ------------------------------------------------------------------------------
# TEST 7: Table has NOT NULL columns without defaults
# ------------------------------------------------------------------------------
def test_7_table_not_null_without_defaults():
    meta = _build_mock_meta({
        "employee": [
            {"name": "emp_id", "is_nullable": False, "default": None},
            {"name": "tax_id", "is_nullable": False, "default": None},
            {"name": "nickname", "is_nullable": True, "default": None},
        ]
    })
    # Attempting to insert without providing required tax_id
    stmt = """
    INSERT INTO "ra_ctrl.test_schema".employee (emp_id, nickname)
    VALUES (55, 'Bob');
    """
    valid, diag = validate_statement_against_target_schema(meta, "ra_ctrl.test_schema", stmt, strict_not_null=True)
    assert valid is False, "Expected failure when required NOT NULL column is missing"
    assert "tax_id" in diag
    assert "Missing required NOT NULL column(s) without default" in diag
    print("TEST 7 PASS - NOT NULL columns without defaults: Missing required columns detected")


# ------------------------------------------------------------------------------
# TEST 8: Table has identity / generated columns
# ------------------------------------------------------------------------------
def test_8_table_has_generated_columns():
    meta = _build_mock_meta({
        "invoices": [
            {"name": "invoice_id", "is_nullable": False, "is_identity": True},
            {"name": "subtotal", "is_nullable": False},
            {"name": "tax", "is_nullable": False},
            {"name": "total", "is_nullable": False, "is_generated": True},
        ]
    })
    # Attempting to explicitly write into generated computed column 'total'
    stmt = """
    INSERT INTO "ra_ctrl.test_schema".invoices (subtotal, tax, total)
    VALUES (100.0, 10.0, 110.0);
    """
    valid, diag = validate_statement_against_target_schema(meta, "ra_ctrl.test_schema", stmt)
    assert valid is False, "Expected failure when inserting into generated column"
    assert "Cannot insert directly into generated/computed column(s)" in diag
    assert "total" in diag
    print("TEST 8 PASS - Generated / identity columns: Direct insertion prevented")


# ------------------------------------------------------------------------------
# TEST 9: Table has column defaults
# ------------------------------------------------------------------------------
def test_9_table_has_column_defaults():
    meta = _build_mock_meta({
        "audit_ledger": [
            {"name": "entry_id", "is_nullable": False, "default": None},
            {"name": "status", "is_nullable": False, "default": "'ACTIVE'"},
            {"name": "created_at", "is_nullable": False, "default": "CURRENT_TIMESTAMP"},
        ]
    })
    # Valid INSERT providing only entry_id, letting PostgreSQL defaults handle status & created_at
    stmt = """
    INSERT INTO "ra_ctrl.test_schema".audit_ledger (entry_id)
    VALUES ('E101');
    """
    valid, diag = validate_statement_against_target_schema(meta, "ra_ctrl.test_schema", stmt, strict_not_null=True)
    assert valid is True, f"Expected success when allowing database defaults to apply: {diag}"
    print("TEST 9 PASS - Column defaults: PostgreSQL defaults apply cleanly without NULL injection")


# ------------------------------------------------------------------------------
# TEST 10: Two tables have completely different schemas
# ------------------------------------------------------------------------------
def test_10_two_tables_different_schemas():
    meta = _build_mock_meta({
        "table_a": ["id", "name", "created_at"],
        "table_b": ["ctrl_id", "control_name", "execution_schedule", "attr_1_name", "attr_1_value"]
    })

    stmt_a = "INSERT INTO \"ra_ctrl.test_schema\".table_a (id, name, created_at) VALUES (1, 'Test', CURRENT_TIMESTAMP);"
    stmt_b = "INSERT INTO \"ra_ctrl.test_schema\".table_b (ctrl_id, control_name, execution_schedule) VALUES ('C23', 'Reco', 'DAILY');"

    valid_a, diag_a = validate_statement_against_target_schema(meta, "ra_ctrl.test_schema", stmt_a)
    valid_b, diag_b = validate_statement_against_target_schema(meta, "ra_ctrl.test_schema", stmt_b)

    assert valid_a is True, f"Table A should pass: {diag_a}"
    assert valid_b is True, f"Table B should pass: {diag_b}"

    # Verify cross-pollution fails:
    bad_stmt_b = "INSERT INTO \"ra_ctrl.test_schema\".table_b (id, name) VALUES (1, 'Test');"
    bad_valid, bad_diag = validate_statement_against_target_schema(meta, "ra_ctrl.test_schema", bad_stmt_b)
    assert bad_valid is False, "Cross-polluting columns between distinct tables must fail"
    assert "Columns not present in target:" in bad_diag
    print("TEST 10 PASS - Distinct schemas: Independent schema-aware SQL validated")


# ------------------------------------------------------------------------------
# TEST 11: Multiple schemas contain tables with the same name
# ------------------------------------------------------------------------------
def test_11_multiple_schemas_same_table_name():
    meta_schema_prod = _build_mock_meta({
        "orders": ["order_id", "prod_sku", "quantity"]
    }, schema_name="prod_schema")

    meta_schema_dev = _build_mock_meta({
        "orders": ["order_id", "dev_flag", "test_run_id"]
    }, schema_name="dev_schema")

    prod_stmt = "INSERT INTO prod_schema.orders (order_id, prod_sku, quantity) VALUES (1, 'SKU1', 5);"
    dev_stmt = "INSERT INTO dev_schema.orders (order_id, dev_flag, test_run_id) VALUES (1, true, 'TR-99');"

    valid_prod, _ = validate_statement_against_target_schema(meta_schema_prod, "prod_schema", prod_stmt)
    valid_dev, _ = validate_statement_against_target_schema(meta_schema_dev, "dev_schema", dev_stmt)

    assert valid_prod is True, "Prod schema statement should validate against prod metadata"
    assert valid_dev is True, "Dev schema statement should validate against dev metadata"

    # Prod statement against Dev metadata must fail
    cross_valid, cross_diag = validate_statement_against_target_schema(meta_schema_dev, "dev_schema", prod_stmt)
    assert cross_valid is False
    assert "prod_sku" in cross_diag
    print("TEST 11 PASS - Multiple schemas with same table name: Schema isolation verified")


# ------------------------------------------------------------------------------
# TEST 12: Table or column does not exist
# ------------------------------------------------------------------------------
def test_12_table_does_not_exist():
    meta = _build_mock_meta({
        "existing_table": ["col1", "col2"]
    })
    stmt = "INSERT INTO \"ra_ctrl.test_schema\".non_existent_table (col1) VALUES ('X');"
    valid, diag = validate_statement_against_target_schema(meta, "ra_ctrl.test_schema", stmt)
    assert valid is False, "Must fail when table does not exist"
    assert "Table does not exist in target schema" in diag
    assert "non_existent_table" in diag
    assert "Deployment SQL was NOT executed" in diag
    print("TEST 12 PASS - Table does not exist: Aborted before execution with clear diagnostic")


# ------------------------------------------------------------------------------
# TEST 13: End-to-End Generator Generality (Master Table Guard)
# ------------------------------------------------------------------------------
def test_13_generator_skips_master_tables():
    """
    Verifies that generate_transformation_sql does not emit generic dummy INSERTs
    into master configuration tables (e.g. ctrl_config, bucket_config).
    """
    analysis_data = {
        "sources": [{"source_table": "raw_feed", "load_type": "Truncate & load"}],
        "data_model": [
            {
                "table_name": "ctrl_config",
                "stage": "Configuration",
                "description": "Master table storing control configuration parameters",
                "load_type": "Truncate & load",
            },
            {
                "table_name": "dm_stage_recon",
                "stage": "Reconciliation",
                "description": "Dynamic stage table",
                "load_type": "Truncate & load",
            }
        ]
    }
    target_meta = _build_mock_meta({
        "dm_stage_recon": ["id", "batch_id", "execution_cycle_date", "record_status", "source_reference", "kri_flag"]
    })
    sql = generate_transformation_sql(
        target_schema="ra_ctrl.test_schema",
        target_dialect="postgresql",
        sources=analysis_data["sources"],
        rules={},
        mappings=[],
        analysis_data=analysis_data,
        target_meta=target_meta
    )


    # 1. Must NOT contain INSERT INTO ... ctrl_config with batch_id
    assert 'INSERT INTO "ra_ctrl.test_schema".ctrl_config (batch_id' not in sql, \
        "Master table 'ctrl_config' must NOT receive synthetic audit INSERT"

    # 2. Must contain reference comment protecting the master table
    assert "Reference Master Table: ctrl_config" in sql
    assert "Synthetic default INSERT omitted" in sql

    # 3. Non-master data model stage table DOES receive stage sync
    assert 'INSERT INTO "ra_ctrl.test_schema".dm_stage_recon (batch_id' in sql

    print("TEST 13 PASS - Generator generality: Master tables preserved without synthetic INSERTs")


# ------------------------------------------------------------------------------
# TEST 14: Table without audit columns never receives batch_id
# ------------------------------------------------------------------------------
def test_14_table_without_audit_columns_never_receives_batch_id():
    """
    Verifies that any target table lacking batch_id, execution_cycle_date,
    record_status, source_reference, kri_flag NEVER receives them.
    """
    analysis_data = {
        "sources": [{"source_table": "cust_feed", "load_type": "Truncate & load"}],
        "data_model": [
            {
                "table_name": "customer_account_ledger",
                "stage": "Core",
                "description": "Custom business ledger",
                "load_type": "Truncate & load",
            }
        ]
    }
    target_meta = _build_mock_meta({
        "customer_account_ledger": ["account_id", "customer_name", "balance_amount", "currency_code"]
    })
    sql = generate_transformation_sql(
        target_schema="ra_ctrl.test_schema",
        target_dialect="postgresql",
        sources=analysis_data["sources"],
        rules={},
        mappings=[],
        analysis_data=analysis_data,
        target_meta=target_meta
    )

    forbidden_cols = ["batch_id", "execution_cycle_date", "record_status", "source_reference", "kri_flag"]
    for col in forbidden_cols:
        assert f"customer_account_ledger ({col}" not in sql, f"Forbidden column {col} injected into customer_account_ledger"
        assert f"customer_account_ledger\n({col}" not in sql, f"Forbidden column {col} injected into customer_account_ledger"

    # Must contain protective reference comment instead of synthetic dummy INSERT
    assert "Reference Target Entity: customer_account_ledger" in sql
    assert "Synthetic dummy INSERT omitted" in sql

    # Validate all executable statements against target schema
    for stmt in _split_sql_statements(sql):
        clean = stmt.strip()
        if clean and _has_executable_sql(clean):
            # Only validate statements targeting our mock table
            if "customer_account_ledger" in clean:
                valid, diag = validate_statement_against_target_schema(target_meta, "ra_ctrl.test_schema", clean)
                assert valid, f"SQL validation failed on customer_account_ledger: {diag}"

    print("TEST 14 PASS - Table without audit columns never receives batch_id or other generic columns")


# ------------------------------------------------------------------------------
# TEST 15: Table with partial audit columns receives ONLY valid ones
# ------------------------------------------------------------------------------
def test_15_table_with_partial_audit_columns_receives_only_valid_ones():
    """
    Verifies that a table with ONLY batch_id and record_status receives only those two,
    omitting execution_cycle_date, source_reference, kri_flag.
    """
    analysis_data = {
        "sources": [{"source_table": "audit_feed", "load_type": "Truncate & load"}],
        "data_model": [
            {
                "table_name": "partial_audit_entity",
                "stage": "Stage",
                "description": "Partial audit table",
                "load_type": "Truncate & load",
            }
        ]
    }
    target_meta = _build_mock_meta({
        "partial_audit_entity": ["id", "batch_id", "record_status", "payload"]
    })
    sql = generate_transformation_sql(
        target_schema="ra_ctrl.test_schema",
        target_dialect="postgresql",
        sources=analysis_data["sources"],
        rules={},
        mappings=[],
        analysis_data=analysis_data,
        target_meta=target_meta
    )

    # Must contain INSERT with batch_id and record_status
    assert 'INSERT INTO "ra_ctrl.test_schema".partial_audit_entity (batch_id, record_status)' in sql

    # Must NOT contain the other 3 columns
    assert "execution_cycle_date" not in sql.split("partial_audit_entity")[1].split(";")[0]
    assert "source_reference" not in sql.split("partial_audit_entity")[1].split(";")[0]
    assert "kri_flag" not in sql.split("partial_audit_entity")[1].split(";")[0]

    # Validate against target schema
    for stmt in _split_sql_statements(sql):
        clean = stmt.strip()
        if clean and _has_executable_sql(clean) and "partial_audit_entity" in clean:
            valid, diag = validate_statement_against_target_schema(target_meta, "ra_ctrl.test_schema", clean)
            assert valid, f"Validation failed: {diag}"

    print("TEST 15 PASS - Table with partial audit columns receives ONLY existing columns")


# ------------------------------------------------------------------------------
# TEST 16: ctrl_config authoritative schema receives valid configured columns
# ------------------------------------------------------------------------------
def test_16_ctrl_config_authoritative_schema_populates_valid_config_columns():
    """
    Verifies that ctrl_config receives an INSERT using ONLY its actual configured/business columns
    (ctrl_id, control_name, execution_schedule, updated_by, create_dtm, update_dtm)
    and NEVER receives batch_id, execution_cycle_date, record_status, source_reference, kri_flag.
    """
    analysis_data = {
        "control_overview": {
            "identification": {
                "control_number": "CTRL-23",
                "control_title": "Automated Reconciliation Control",
            },
            "frequency": "Daily",
        },
        "sources": [{"source_table": "cmdb_dump", "load_type": "Truncate & load"}],
        "data_model": [
            {
                "table_name": "ctrl_config",
                "stage": "Config",
                "description": "Control configuration table",
                "load_type": "Truncate & load",
            }
        ]
    }
    # Authoritative physical schema of ctrl_config as specified in problem description
    target_meta = _build_mock_meta({
        "ctrl_config": [
            "ctrl_id", "control_name", "execution_schedule",
            "attr_1_name", "attr_1_value", "attr_22_name", "attr_22_value",
            "updated_by", "to_email", "cc_email", "create_dtm", "update_dtm"
        ]
    })
    sql = generate_transformation_sql(
        target_schema="ra_ctrl.test_schema",
        target_dialect="postgresql",
        sources=analysis_data["sources"],
        rules={},
        mappings=[],
        control_overview=analysis_data["control_overview"],
        analysis_data=analysis_data,
        target_meta=target_meta
    )

    # 1. Must NOT contain batch_id on ctrl_config
    assert 'INSERT INTO "ra_ctrl.test_schema".ctrl_config (batch_id' not in sql

    # 2. Must contain INSERT using only valid configured business columns
    assert 'INSERT INTO "ra_ctrl.test_schema".ctrl_config (ctrl_id, control_name, execution_schedule, updated_by, create_dtm, update_dtm)' in sql
    assert "VALUES ('CTRL-23', 'Automated Reconciliation Control', 'Daily', 'SYSTEM', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)" in sql

    # 3. None of the 5 forbidden audit columns must be present in the ctrl_config statement
    ctrl_block = [s for s in _split_sql_statements(sql) if "ctrl_config" in s][0]
    for bad_col in ["batch_id", "execution_cycle_date", "record_status", "source_reference", "kri_flag"]:
        assert bad_col not in ctrl_block, f"{bad_col} unexpectedly found in ctrl_config SQL"

    # 4. Must pass pre-execution schema validation perfectly!
    valid, diag = validate_statement_against_target_schema(target_meta, "ra_ctrl.test_schema", ctrl_block)
    assert valid, f"Validation failed on ctrl_config: {diag}"

    print("TEST 16 PASS - ctrl_config receives ONLY valid physical configured columns and passes validation")


# ------------------------------------------------------------------------------
# TEST 17: Unverified schema never receives audit columns
# ------------------------------------------------------------------------------
def test_17_unverified_schema_never_assumes_audit_columns():
    """
    Verifies that when a table's schema cannot be verified from target_meta or DDL,
    the generator omits synthetic dummy inserts and protects the table from corruption.
    """
    analysis_data = {
        "sources": [{"source_table": "raw_feed", "load_type": "Truncate & load"}],
        "data_model": [
            {
                "table_name": "unverified_legacy_table",
                "stage": "Legacy",
                "description": "Unknown external table",
                "load_type": "Truncate & load",
            }
        ]
    }
    # No target_meta provided, table not in DDL
    sql = generate_transformation_sql(
        target_schema="ra_ctrl.test_schema",
        target_dialect="postgresql",
        sources=analysis_data["sources"],
        rules={},
        mappings=[],
        analysis_data=analysis_data
    )

    assert "unverified_legacy_table (batch_id" not in sql
    assert "TRUNCATE TABLE \"ra_ctrl.test_schema\".unverified_legacy_table" not in sql
    assert "Reference Target Entity: unverified_legacy_table" in sql

    print("TEST 17 PASS - Unverified schema never receives dummy audit columns")


# ------------------------------------------------------------------------------
# TEST 18: Multiple heterogeneous tables in the same run
# ------------------------------------------------------------------------------
def test_18_multiple_heterogeneous_tables_in_same_run():
    """
    Verifies that within a single control run, different tables with completely
    different schemas each receive their respective valid columns without cross-contamination.
    """
    analysis_data = {
        "control_overview": {
            "identification": {"control_number": "CTRL-99", "control_title": "Multi-Schema Control"},
            "frequency": "Weekly",
        },
        "sources": [{"source_table": "feed_a", "load_type": "Truncate & load"}],
        "data_model": [
            {"table_name": "tbl_audit_only", "description": "Audit entity"},
            {"table_name": "tbl_config_only", "description": "Config entity"},
            {"table_name": "tbl_custom_only", "description": "Custom entity"},
        ]
    }
    target_meta = _build_mock_meta({
        "tbl_audit_only": ["id", "batch_id", "record_status"],
        "tbl_config_only": ["ctrl_id", "control_name", "execution_schedule"],
        "tbl_custom_only": ["feature_id", "feature_name", "score"],
    })
    sql = generate_transformation_sql(
        target_schema="ra_ctrl.test_schema",
        target_dialect="postgresql",
        sources=analysis_data["sources"],
        rules={},
        mappings=[],
        control_overview=analysis_data["control_overview"],
        analysis_data=analysis_data,
        target_meta=target_meta
    )

    # 1. tbl_audit_only has batch_id and record_status
    assert 'INSERT INTO "ra_ctrl.test_schema".tbl_audit_only (batch_id, record_status)' in sql
    # 2. tbl_config_only has ctrl_id, control_name, execution_schedule
    assert 'INSERT INTO "ra_ctrl.test_schema".tbl_config_only (ctrl_id, control_name, execution_schedule)' in sql
    # 3. tbl_custom_only has no audit or config columns -> reference comment only
    assert "Reference Target Entity: tbl_custom_only" in sql
    assert 'INSERT INTO "ra_ctrl.test_schema".tbl_custom_only' not in sql

    # Validate statements targeting the mock tables against target_meta
    for stmt in _split_sql_statements(sql):
        clean = stmt.strip()
        if clean and _has_executable_sql(clean):
            if any(t in clean for t in ["tbl_audit_only", "tbl_config_only", "tbl_custom_only"]):
                valid, diag = validate_statement_against_target_schema(target_meta, "ra_ctrl.test_schema", clean)
                assert valid, f"Validation failed: {diag}"


    print("TEST 18 PASS - Multiple heterogeneous tables each receive only their valid columns")


# ------------------------------------------------------------------------------
# RUNNER
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    tests = [
        test_1_table_has_all_requested_columns,
        test_2_table_missing_one_requested_column,
        test_3_table_has_completely_different_columns,
        test_4_table_has_audit_columns,
        test_5_table_has_no_audit_columns,
        test_6_table_has_nullable_columns,
        test_7_table_not_null_without_defaults,
        test_8_table_has_generated_columns,
        test_9_table_has_column_defaults,
        test_10_two_tables_different_schemas,
        test_11_multiple_schemas_same_table_name,
        test_12_table_does_not_exist,
        test_13_generator_skips_master_tables,
        test_14_table_without_audit_columns_never_receives_batch_id,
        test_15_table_with_partial_audit_columns_receives_only_valid_ones,
        test_16_ctrl_config_authoritative_schema_populates_valid_config_columns,
        test_17_unverified_schema_never_assumes_audit_columns,
        test_18_multiple_heterogeneous_tables_in_same_run,
    ]

    passed = failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            import traceback
            print(f"FAIL {t.__name__}: {e}")
            traceback.print_exc()
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed}/{len(tests)} passed, {failed} failed")
    sys.exit(1 if failed else 0)

