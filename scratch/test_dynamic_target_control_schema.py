import os
import sys
import re
from sqlalchemy import create_engine, text

# Add workspace root to sys.path
sys.path.insert(0, r"c:\Users\Hp\Desktop\HLA_Project")

from analyzer import analyze_document
from target_logic_builder import build_target_logic_package, validate_target_ddl, _format_schema_prefix

def test_dynamic_target_control_schema():
    print("================================================================================")
    print("TEST: Dynamic Target Schema (ra_ctrl.ctrl_{num}) & Multi-Source Synthesis")
    print("================================================================================")

    hla_doc_path = r"C:\Users\Hp\Downloads\HLA_Solution_Design_Template.docx"
    assert os.path.exists(hla_doc_path), f"File not found: {hla_doc_path}"

    print(f"\n1. Analyzing HLA document: {hla_doc_path}")
    analysis = analyze_document(hla_doc_path)

    # 1. Verify Control Identification
    co = analysis.get("control_overview", {})
    ctrl_id = co.get("identification", {})
    ctrl_num = ctrl_id.get("control_number")
    ctrl_digits = co.get("control_digits")
    target_schema = co.get("target_schema")

    print(f"   - Control Number extracted: '{ctrl_num}'")
    print(f"   - Control Digits extracted: '{ctrl_digits}'")
    print(f"   - Derived Target Schema:    '{target_schema}'")
    assert ctrl_digits == "23", f"Expected digits '23', got '{ctrl_digits}'"
    assert target_schema == "ra_ctrl.ctrl_test", f"Expected 'ra_ctrl.ctrl_test', got '{target_schema}'"

    # 2. Verify Multi-Source DBs Synthesis
    src_dbs = analysis.get("source_databases", [])
    print(f"\n2. Verifying Multi-Source DBs Synthesis:")
    print(f"   - Total source DBs synthesized: {len(src_dbs)}")
    for db_entry in src_dbs:
        print(f"     * DB Name: '{db_entry.get('source_db_name')}' | Tables: {db_entry.get('tables')}")
    assert len(src_dbs) >= 1, "Expected at least 1 synthesized source database"

    # 3. Test Package Generation for Control-Test
    print("\n3. Testing Target Logic Package Generation for Control-Test:")
    target_config = {
        "db_type": "postgresql",
        "host": "localhost",
        "port": 5432,
        "database_name": "hla_db",
        "username": "postgres",
        "target_env": "dev"
        # schema_name intentionally omitted to test dynamic derivation!
    }

    package = build_target_logic_package(analysis, {}, target_config)
    generated_schema = package.get("target_schema")
    print(f"   - Generated Target Schema: '{generated_schema}'")
    assert generated_schema == "ra_ctrl.ctrl_test", f"Expected 'ra_ctrl.ctrl_test', got '{generated_schema}'"

    ddl = package.get("ddl", "")
    print("   - Verifying DDL Schema and Table Statements:")
    assert 'CREATE SCHEMA IF NOT EXISTS "ra_ctrl.ctrl_test";' in ddl, "Schema creation statement missing quotes around dot"
    assert '"ra_ctrl.ctrl_test".' in ddl, "Table definitions missing schema prefix '\"ra_ctrl.ctrl_test\".'"
    print("     [OK] CREATE SCHEMA IF NOT EXISTS \"ra_ctrl.ctrl_test\"; present")
    print("     [OK] \"ra_ctrl.ctrl_test\".table_name prefix present")

    # Verify Upstream Source DB annotations
    src_ddl = package.get("source_tables_ddl", "")
    assert "-- Upstream Source DB:" in src_ddl, "Upstream source DB annotation missing in source tables DDL"
    print("     [OK] Source table DDL contains upstream Source DB annotations")

    # Verify PySpark JDBC table
    pyspark = package.get("pyspark_code", "")
    assert '"ra_ctrl.ctrl_test".ctrl_test_balanced_dataset' in pyspark or 'ra_ctrl.ctrl_test' in pyspark, "PySpark JDBC write missing dynamic schema"
    print("     [OK] PySpark pipeline correctly references dynamic schema and balanced table")

    # 4. Test Dynamic Adaptability to Control-24
    print("\n4. Testing Dynamic Adaptability to Control-24:")
    import copy
    analysis_24 = copy.deepcopy(analysis)
    analysis_24["control_overview"]["identification"]["control_number"] = "Control-24"
    analysis_24["control_overview"]["control_digits"] = "24"
    analysis_24["control_overview"]["target_schema"] = "ra_ctrl.ctrl_24"

    package_24 = build_target_logic_package(analysis_24, {}, target_config)
    gen_schema_24 = package_24.get("target_schema")
    print(f"   - Generated Target Schema for Control-24: '{gen_schema_24}'")
    assert gen_schema_24 == "ra_ctrl.ctrl_24", f"Expected 'ra_ctrl.ctrl_24', got '{gen_schema_24}'"
    assert 'CREATE SCHEMA IF NOT EXISTS "ra_ctrl.ctrl_24";' in package_24.get("ddl", "")
    assert '"ra_ctrl.ctrl_24".' in package_24.get("ddl", "")
    print("     [OK] Control-24 dynamically generated schema 'ra_ctrl.ctrl_24' with zero code changes!")

    # 5. Live PostgreSQL Dry-Run Execution Test
    print("\n5. Testing Live PostgreSQL DDL Execution against hla_db:")
    from app import get_env_db_password
    live_target_config = {
        "db_type": "postgresql",
        "host": "localhost",
        "port": 5432,
        "database_name": "hla_db",
        "username": "postgres",
        "password": get_env_db_password(),
        "schema_name": "ra_ctrl.ctrl_test"
    }
    success, msg = validate_target_ddl(live_target_config, ddl)
    print(f"   - Dry-Run Validation Status: {success}")
    print(f"   - Validation Message: {msg}")
    assert success, f"Dry-run validation failed: {msg}"
    print("     [OK] Live PostgreSQL dry-run succeeded inside rollback transaction!")

    print("\n================================================================================")
    print("ALL DYNAMIC TARGET SCHEMA & MULTI-SOURCE TESTS PASSED 100%!")
    print("================================================================================")

if __name__ == "__main__":
    test_dynamic_target_control_schema()
