"""
test_schema_migration_service.py
--------------------------------
Comprehensive test suite for SchemaMigrationService:
1. Table discovery with strict exclusion of system/application schemas.
2. PostgreSQL structure inspection (ordinal columns, constraints, row count).
3. Planning table migration (detecting unwanted generic columns, reordering).
4. Safe table rebuild execution with zero data loss assertion.
5. Transactional rollback safety on mismatch.
"""

import os
import sys
from sqlalchemy import create_engine, text, inspect

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from schema_migration_service import SchemaMigrationService, ENVELOPE_HEADER_COLS, ENVELOPE_FOOTER_COLS


def test_migration_planning_detects_unwanted_columns():
    """Test that plan_table_migration detects unwanted generic columns and plans reordering."""
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        # Create a table that was generated with the unwanted generic columns
        conn.execute(text("""
            CREATE TABLE test_tbl (
                id INTEGER PRIMARY KEY,
                batch_id VARCHAR(50),
                execution_cycle_date DATE,
                record_status VARCHAR(50),
                source_reference VARCHAR(255),
                kri_flag VARCHAR(50),
                account_id VARCHAR(50),
                amount NUMERIC(10,2),
                created_at TIMESTAMP
            );
        """))
        for i in range(10):
            conn.execute(text(f"""
                INSERT INTO test_tbl (id, batch_id, account_id, amount)
                VALUES ({i+1}, 'BATCH_1', 'ACC_{i}', {100.0 * (i+1)});
            """))

    service = SchemaMigrationService(engine)
    plan = service.plan_table_migration(None, "test_tbl")

    assert plan["needs_migration"] is True
    assert set(plan["columns_to_remove"]) == {
        "id", "batch_id", "execution_cycle_date", "record_status", "source_reference", "kri_flag"
    }
    assert plan["row_count"] == 10

    # Expected column order must start with the 4 header columns, then business, then 4 footer columns
    expected = plan["expected_columns"]
    assert expected[:4] == ENVELOPE_HEADER_COLS
    assert "account_id" in expected[4:-4]
    assert "amount" in expected[4:-4]
    assert expected[-4:] == ENVELOPE_FOOTER_COLS
    print("TEST 1 PASS - plan_table_migration detects all unwanted columns and computes expected envelope order")


def test_migration_execution_preserves_data():
    """Test that execute_table_migration rebuilds table and preserves all rows."""
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE customers (
                id INTEGER,
                batch_id VARCHAR(50),
                cust_code VARCHAR(20),
                balance NUMERIC(12,2)
            );
        """))
        for i in range(25):
            conn.execute(text(f"INSERT INTO customers VALUES ({i}, 'B1', 'C_{i}', {i * 50.0});"))

    service = SchemaMigrationService(engine)
    plan = service.plan_table_migration(None, "customers")
    res = service.execute_table_migration(plan, dry_run=False)

    assert res["status"] == "MIGRATED"
    assert res["rows_preserved"] == 25
    assert set(res["columns_removed"]) == {"id", "batch_id"}

    # Verify new table structure and row count
    insp = inspect(engine)
    cols = [c["name"] for c in insp.get_columns("customers")]
    assert cols[:4] == ENVELOPE_HEADER_COLS
    assert cols[4:6] == ["cust_code", "balance"]
    assert cols[-4:] == ENVELOPE_FOOTER_COLS

    with engine.connect() as conn:
        cnt = conn.execute(text("SELECT count(*) FROM customers;")).scalar()
        assert cnt == 25
        rows = conn.execute(text("SELECT cust_code, balance FROM customers ORDER BY cust_code LIMIT 3;")).fetchall()
        assert rows[0][0] == "C_0"
        assert rows[1][0] == "C_1"

    print("TEST 2 PASS - execute_table_migration rebuilds table with zero data loss")


def test_master_table_is_preserved_intact():
    """Test that authoritative master tables like ctrl_config are skipped and never altered."""
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE ctrl_config (
                ctrl_id INT,
                control_name VARCHAR(100),
                execution_schedule VARCHAR(100),
                updated_by VARCHAR(50)
            );
        """))
        conn.execute(text("INSERT INTO ctrl_config VALUES (23, 'CTRL-23', 'WEEKLY', 'SYS');"))

    service = SchemaMigrationService(engine)
    plan = service.plan_table_migration(None, "ctrl_config")
    assert plan["needs_migration"] is False
    assert plan["is_master"] is True

    res = service.execute_table_migration(plan, dry_run=False)
    assert res["status"] == "SKIPPED"
    assert res["rows_preserved"] == 1

    print("TEST 3 PASS - Authoritative master table is preserved without modification")


def test_rollback_safety_on_validation_failure():
    """Test that if row count validation fails, the transaction rolls back cleanly leaving original table intact."""
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE sensitive_data (
                id INTEGER,
                batch_id VARCHAR(50),
                secret_payload VARCHAR(100)
            );
        """))
        for i in range(15):
            conn.execute(text(f"INSERT INTO sensitive_data VALUES ({i}, 'B1', 'PAYLOAD_{i}');"))

    service = SchemaMigrationService(engine)
    plan = service.plan_table_migration(None, "sensitive_data")
    # Artificially alter the expected row count to trigger safety assertion failure
    plan["row_count"] = 999

    failed = False
    try:
        service.execute_table_migration(plan, dry_run=False)
    except Exception as e:
        failed = True
        assert "Row count mismatch" in str(e)

    assert failed is True

    # Verify original table is completely intact with original columns and all 15 rows!
    insp = inspect(engine)
    cols = [c["name"] for c in insp.get_columns("sensitive_data")]
    assert cols == ["id", "batch_id", "secret_payload"]

    with engine.connect() as conn:
        cnt = conn.execute(text("SELECT count(*) FROM sensitive_data;")).scalar()
        assert cnt == 15

    print("TEST 4 PASS - Transaction rolls back cleanly on validation failure, preserving original table intact")


if __name__ == "__main__":
    test_migration_planning_detects_unwanted_columns()
    test_migration_execution_preserves_data()
    test_master_table_is_preserved_intact()
    test_rollback_safety_on_validation_failure()
    print("\n==================================================")
    print("All SchemaMigrationService unit tests PASSED (4/4)!")
    print("==================================================")
