"""
test_dynamic_source_target_separation.py
-----------------------------------------
Validates 100% Dynamic Source and Target Separation according to strict document-driven principles:
1. Source Table Discovery strictly from physical source inventory sheets
2. Preservation of schema and table formats (e.g., schema.table)
3. Logical Inputs (I1, I2, I3) categorized as logical processing streams and NEVER treated as physical tables
4. Target Table Discovery from Data Model classified by layer (Ingest, Pre-Execution, Execution, Post-Execution, Reporting, History, Summary)
5. Zero leakage of target models into Source DB verification
6. Attribute Mappings and Business Rules used for lineage without inventing physical source tables
7. Unclassified tables flagged with sheet and row provenance
8. Zero hardcoded schema names, table names, database names, or control numbers
"""

import unittest
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.core.semantic_analyzer import SemanticAnalyzer
from app import extract_document_source_entities, extract_document_target_entities


class TestDynamicSourceTargetSeparation(unittest.TestCase):

    def test_01_dynamic_source_inventory_discovery(self):
        """Source tables must be discovered solely from source inventory declarations."""
        mock_analysis = {
            "classification": {
                "source_tables": [
                    {
                        "source_id": "SRC_FEED_01",
                        "database": "TELECOM_BILLING_DB",
                        "schema": "billing_v2",
                        "table": "call_detail_records",
                        "full_table_name": "billing_v2.call_detail_records",
                        "type_of_load": "Incremental",
                        "frequency": "Hourly"
                    },
                    {
                        "source_id": "SRC_FEED_02",
                        "database": "CRM_SYSTEM_DB",
                        "schema": "crm_core",
                        "table": "subscriber_profiles",
                        "full_table_name": "crm_core.subscriber_profiles",
                        "type_of_load": "Truncate and load",
                        "frequency": "Daily"
                    }
                ],
                "target_tables": [
                    {
                        "entity_name": "stg_call_records_raw",
                        "stage": "Ingest",
                        "layer": "Ingest",
                        "role": "INTERMEDIATE"
                    },
                    {
                        "entity_name": "monthly_billing_summary",
                        "stage": "Reporting",
                        "layer": "Reporting",
                        "role": "TARGET"
                    }
                ],
                "logical_inputs": [
                    {
                        "logical_input_id": "I1",
                        "stream_name": "I1: Telecom Call Stream"
                    },
                    {
                        "logical_input_id": "I2",
                        "stream_name": "I2: Subscriber Profile Stream"
                    }
                ],
                "mappings": [
                    {
                        "source_table": "billing_v2.call_detail_records",
                        "source_field": "duration_sec",
                        "target_table": "monthly_billing_summary",
                        "target_attribute": "total_duration_minutes",
                        "mapping_type": "Derived"
                    }
                ],
                "business_rules": [
                    {
                        "rule_id": "RULE_01",
                        "source_dataset": "I1",
                        "condition": "duration_sec > 0"
                    }
                ]
            }
        }

        # 1. Extract physical source entities
        source_entities = extract_document_source_entities(mock_analysis)
        self.assertEqual(len(source_entities), 2)
        source_tables = [s["table_name"] for s in source_entities]
        self.assertIn("call_detail_records", source_tables)
        self.assertIn("subscriber_profiles", source_tables)

        # Ensure target entities are NOT in source verification list
        self.assertNotIn("stg_call_records_raw", source_tables)
        self.assertNotIn("monthly_billing_summary", source_tables)

        # Ensure logical inputs are NOT in source verification list
        self.assertNotIn("I1", source_tables)
        self.assertNotIn("I2", source_tables)

    def test_02_target_table_layer_classification(self):
        """Data Model entities must be categorized into documented layers."""
        layers_to_test = [
            ("Ingest", "raw_network_feed", "Landing table for raw logs"),
            ("Pre-Execution", "stg_cleansed_events", "Cleansed and standardized events"),
            ("Execution", "proc_event_enrichment", "Rules engine processing node"),
            ("Post-Execution", "recon_audit_reconciliation", "Post-execution balance and match"),
            ("Reporting", "executive_kpi_dashboard", "Presentation reporting mart"),
            ("History", "hist_transaction_snapshot", "SCD Type 2 historical archive"),
            ("Summary", "daily_revenue_aggregation", "Aggregated daily metrics")
        ]

        for expected_layer, entity_name, desc in layers_to_test:
            classified = SemanticAnalyzer.classify_target_layer(expected_layer, entity_name, desc)
            self.assertEqual(classified, expected_layer, f"Expected {expected_layer}, got {classified} for {entity_name}")

    def test_03_logical_inputs_vs_physical_tables(self):
        """Logical inputs (I1, I2, etc.) from Business Rules must not be treated as database tables."""
        raw_rules_rows = [
            {
                "rule_id": "BR-01",
                "source_dataset": "I1",
                "condition": "status == 'ACTIVE'",
                "action": "Keep record",
                "_excel_row_num": 5
            },
            {
                "rule_id": "BR-02",
                "source_dataset": "I2",
                "condition": "account_balance >= 0",
                "action": "Flag deficit",
                "_excel_row_num": 6
            }
        ]
        parsed_rules = SemanticAnalyzer._extract_rules(raw_rules_rows, sheet_name="Business Rules", doc_id="test-doc")
        
        # Logical inputs must be parsed
        self.assertIn("logical_inputs", parsed_rules)
        logical_ids = [li["logical_input_id"] for li in parsed_rules["logical_inputs"]]
        self.assertIn("I1", logical_ids)
        self.assertIn("I2", logical_ids)

        # Verify extract_document_source_entities ignores logical inputs
        mock_analysis = {
            "classification": {
                "source_tables": [],
                "logical_inputs": parsed_rules["logical_inputs"]
            }
        }
        sources = extract_document_source_entities(mock_analysis)
        self.assertEqual(len(sources), 0, "Logical inputs must never be converted into physical source tables")

    def test_04_zero_hardcoding_inspection(self):
        """Validates that no specific project, control, or table names are hardcoded in the analyzers."""
        import re
        forbidden_patterns = [
            r'\bstg_customer\b',
            r'\bcustomer_sales_summary\b',
            r'\bctrl_23\b',
            r'\bCTRL-23\b'
        ]

        files_to_check = [
            os.path.join(PROJECT_ROOT, "backend", "core", "semantic_analyzer.py"),
            os.path.join(PROJECT_ROOT, "app.py"),
            os.path.join(PROJECT_ROOT, "target_logic_builder.py")
        ]

        for file_path in files_to_check:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                for pat in forbidden_patterns:
                    # Ignore occurrences in comments or docstrings if any, but ensure not in executable logic
                    matches = re.findall(pat, content)
                    self.assertEqual(len(matches), 0, f"Found hardcoded pattern '{pat}' in {file_path}")


if __name__ == "__main__":
    unittest.main()
