"""
End-to-End Multi-Control Generic Test Suite
============================================
Validates that HLA Studio dynamically handles any control (CTRL-23, CTRL-24, CTRL-25, CTRL-26, CTRL-88, CTRL-99, etc.)
with identical code paths, dynamic ctrl_id resolution, runtime execution context, correct physical column envelopes,
and zero hardcoded control assumptions.
"""

import sys
import os
import re
from datetime import datetime, date

sys.path.insert(0, os.path.abspath("."))

from target_logic_builder import (
    generate_target_ddl,
    generate_transformation_sql,
    validate_statement_against_target_schema,
    _split_sql_statements,
    _has_executable_sql,
    _parse_required_objects_from_ddl,
    build_table_columns_with_standard_envelope,
    _STANDARD_ENVELOPE_COLUMNS
)
from schema_migration_service import ENVELOPE_HEADER_COLS, ENVELOPE_FOOTER_COLS, UNWANTED_GENERIC_COLUMNS


def create_mock_analysis_for_control(ctrl_number: str, ctrl_title: str, freq: str, tables: list):
    """Generates dynamic HLA analysis data for any arbitrary control."""
    sources = []
    source_cols_map = {}
    for tbl_name, cols in tables:
        sources.append({
            "source_system": f"SYS_{tbl_name.upper()}",
            "source_db": "test_db",
            "source_schema": "public",
            "source_table": tbl_name,
            "type_of_load": "Truncate and load",
            "frequency": freq,
        })
        source_cols_map[tbl_name] = cols

    m_dig = re.search(r'\d+', ctrl_number)
    digits = m_dig.group(0) if m_dig else "99"

    return {
        "control_overview": {
            "identification": {
                "control_number": ctrl_number,
                "control_title": ctrl_title,
                "purpose": f"Automated data governance and reconciliation for {ctrl_number}",
                "target_schema": f"ra_ctrl.ctrl_{digits}"
            },
            "control_digits": digits,
            "frequency": freq,
        },
        "sources": sources,
        "rules": {
            "input_streams": [{"rule_id": "I1", "data_stream": "Stream A"}],
            "filter_rules": [{"rule_id": "R1", "rule_statement": "Deduplicate"}],
            "balance_rules": [{"rule_id": "B1", "rule_statement": "Reconcile balance"}],
            "reconciliation_flows": []
        },
        "mappings": [
            {"report_table_name": f"rep_{digits}_summary", "target_column": "summary_id", "mapping_type": "Direct", "source_field": "summary_id"},
            {"report_table_name": f"rep_{digits}_summary", "target_column": "metric_value", "mapping_type": "Derived", "derivation_logic": "SUM(b.balance_amt)"}
        ],
        "config_tables": [
            {"table_name": f"cfg_{digits}_thresholds", "target_column": "threshold_val", "description": "Threshold config"}
        ],
        "data_model": [
            {"table_name": f"dm_{digits}_stage", "stage": "Stage 1", "load_type": "Truncate and load", "columns": [{"name": "payload_code", "type": "VARCHAR(50)"}]}
        ],
        "source_cols_map": source_cols_map,
        "introspected_sources": {
            tbl: {
                "table_found": True,
                "found_in_db": "test_db",
                "columns": cols
            }
            for tbl, cols in source_cols_map.items()
        }
    }


def test_multi_control_ddl_and_column_envelope():
    """Verify that multiple controls (23, 24, 25, 26, 88, 99) all produce valid envelopes and zero unwanted generic columns."""
    test_controls = [
        ("CTRL-23", "VUTM Firewall Reconciliation", "Daily", [("feed_firewall", [{"name": "vdom", "type": "VARCHAR(50)"}, {"name": "ip_addr", "type": "VARCHAR(50)"}])]),
        ("CTRL-24", "Billing Subledger Parity", "Monthly", [("billing_feed", [{"name": "invoice_id", "type": "VARCHAR(50)"}, {"name": "amount", "type": "NUMERIC(18,2)"}])]),
        ("CTRL-25", "Asset Inventory Audit", "Weekly", [("asset_inventory", [{"name": "asset_tag", "type": "VARCHAR(50)"}, {"name": "location_code", "type": "VARCHAR(50)"}])]),
        ("CTRL-26", "Customer Contract Sync", "Quarterly", [("contract_master", [{"name": "contract_id", "type": "VARCHAR(50)"}, {"name": "contract_val", "type": "NUMERIC(18,2)"}])]),
        ("CTRL-88", "Cross-Border Settlement", "Daily", [("settlement_feed", [{"name": "txn_ref", "type": "VARCHAR(50)"}, {"name": "fx_rate", "type": "NUMERIC(18,6)"}])]),
        ("CTRL-99", "Enterprise Universal Audit", "Hourly", [("telemetry_stream", [{"name": "node_id", "type": "VARCHAR(50)"}, {"name": "event_code", "type": "VARCHAR(50)"}])]),
    ]

    for ctrl_num, ctrl_title, freq, tables in test_controls:
        mock = create_mock_analysis_for_control(ctrl_num, ctrl_title, freq, tables)
        target_schema = mock["control_overview"]["identification"]["target_schema"]

        ddl = generate_target_ddl(
            target_schema,
            "postgresql",
            mock["sources"],
            mock["rules"],
            mock["mappings"],
            mock["introspected_sources"],
            mock,
        )

        objects = _parse_required_objects_from_ddl(ddl)
        assert len(objects) >= 3, f"Expected at least 3 objects generated for {ctrl_num}, got {len(objects)}"

        m_dig = re.search(r'\d+', ctrl_num)
        digits = m_dig.group(0)

        for obj in objects:
            tbl_name = obj["bare_name"]
            cols = [c["name"] for c in obj["columns"]]

            # Check exact 4-prefix and 4-suffix envelope
            assert cols[:4] == ENVELOPE_HEADER_COLS, f"Header envelope failed on {ctrl_num}:{tbl_name} -> {cols[:4]}"
            assert cols[-4:] == ENVELOPE_FOOTER_COLS, f"Footer envelope failed on {ctrl_num}:{tbl_name} -> {cols[-4:]}"

            # Check that no unwanted generic columns were injected
            for bad_col in UNWANTED_GENERIC_COLUMNS:
                if bad_col == "id" and (tbl_name.startswith("cfg_") or "recon_" in tbl_name):
                    continue  # config and recon matches have specific config_id / match_id, not generic id
                assert bad_col not in cols, f"Unwanted column {bad_col} found in {ctrl_num}:{tbl_name}!"

        print(f"PASS: {ctrl_num} ({ctrl_title}) generated {len(objects)} tables with exact envelope standard.")


def test_multi_control_transformation_sql_and_validation():
    """Verify that transformation SQL generation dynamically uses runtime control context and passes schema validation."""
    test_controls = [
        ("CTRL-23", "Daily", 23),
        ("CTRL-24", "Monthly", 24),
        ("CTRL-25", "Weekly", 25),
        ("CTRL-26", "Quarterly", 26),
        ("CTRL-88", "Daily", 88),
        ("CTRL-99", "Hourly", 99),
    ]

    for ctrl_num, freq, digits in test_controls:
        mock = create_mock_analysis_for_control(ctrl_num, f"Test Control {digits}", freq, [(f"stream_{digits}", [{"name": f"col_{digits}", "type": "VARCHAR(50)"}])])
        target_schema = mock["control_overview"]["identification"]["target_schema"]

        ddl = generate_target_ddl(
            target_schema,
            "postgresql",
            mock["sources"],
            mock["rules"],
            mock["mappings"],
            mock["introspected_sources"],
            mock,
        )

        sql = generate_transformation_sql(
            target_schema,
            "postgresql",
            mock["sources"],
            mock["rules"],
            mock["mappings"],
            mock["config_tables"],
            mock["control_overview"],
            mock,
            ddl_script=ddl
        )

        # Check that SQL references the correct schema and control
        assert f'"{target_schema}"' in sql or target_schema in sql
        assert f"CTRL-{digits}" in sql or f"{ctrl_num}" in sql

        # Parse DDL tables to create target_meta
        objects = _parse_required_objects_from_ddl(ddl)
        formatted_tables = {}
        for obj in objects:
            tbl_lower = obj["bare_name"].lower()
            cols = []
            for col in obj["columns"]:
                cols.append({
                    "name": col["name"].lower(),
                    "data_type": col.get("type", "varchar(255)").lower(),
                    "is_nullable": True,
                    "default": None,
                    "is_identity": False,
                    "is_generated": False,
                })
            formatted_tables[tbl_lower] = {
                "exists": True,
                "columns": cols,
                "column_names": {c["name"] for c in cols},
            }

        target_meta = {
            "schema_exists": True,
            "schema_name": target_schema,
            "tables": formatted_tables,
        }

        # Run strict schema validator on all statements
        statements = _split_sql_statements(sql)
        for stmt in statements:
            clean_stmt = stmt.strip()
            if not clean_stmt or not _has_executable_sql(clean_stmt):
                continue
            is_valid, diag_msg = validate_statement_against_target_schema(
                target_meta,
                target_schema,
                clean_stmt,
                strict_not_null=False,
            )
            assert is_valid, f"Statement validation failed for {ctrl_num}:\nStmt: {clean_stmt[:200]}\nDiag: {diag_msg}"

        print(f"PASS: {ctrl_num} SQL validated 100% against target schema with zero errors.")


if __name__ == "__main__":
    print("==================================================")
    print("RUNNING MULTI-CONTROL GENERIC E2E TEST SUITE")
    print("==================================================")
    test_multi_control_ddl_and_column_envelope()
    test_multi_control_transformation_sql_and_validation()
    print("\n==================================================")
    print("ALL MULTI-CONTROL GENERIC E2E TESTS PASSED (100%)!")
    print("==================================================")
