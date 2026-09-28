"""
test_generic_different_workbooks.py
-----------------------------------
Validates that completely distinct HLA workbooks (e.g. Healthcare, Airlines, Telecomm)
are interpreted dynamically without code modifications:
- Dynamic discovery of sources, mappings, rules, and target entities
- Target DDL generated strictly from workbook data model
- Zero synthetic envelope columns (ctrl_id, exec_seq, etc.)
- Zero config_tables generated as target database tables
"""

import os
import unittest
from backend.core.semantic_analyzer import SemanticAnalyzer
from target_logic_builder import (
    discover_target_entities,
    generate_target_ddl,
    parse_canonical_table_ref
)


class TestGenericDifferentWorkbooks(unittest.TestCase):

    def test_01_healthcare_clinical_model(self):
        """Test a completely custom Healthcare HLA model without any CRM/Sales assumptions."""
        healthcare_analysis = {
            "document_title": "Hospital Clinical ETL Architecture",
            "sources": [
                {
                    "source_id": "SRC_EMR_01",
                    "source_system": "EPIC_EMR",
                    "source_table": "clinical.patient_admissions",
                    "load_type": "Incremental",
                    "frequency": "Hourly"
                },
                {
                    "source_id": "SRC_LAB_01",
                    "source_system": "LAB_SYSTEM",
                    "source_table": "laboratory.test_results",
                    "load_type": "Append",
                    "frequency": "Real-Time"
                }
            ],
            "data_model": [
                {
                    "dataset_table_entity_name": "patient_stay_fact",
                    "stage": "Curated",
                    "load_type": "Incremental",
                    "description": "Curated patient stay records",
                    "columns": [
                        {"name": "admission_id", "type": "VARCHAR(64)", "nullable": "NOT NULL"},
                        {"name": "patient_mrn", "type": "VARCHAR(32)", "nullable": "NOT NULL"},
                        {"name": "department_code", "type": "VARCHAR(16)"},
                        {"name": "length_of_stay_days", "type": "INTEGER"},
                        {"name": "total_charge_amt", "type": "DECIMAL(12,2)"}
                    ]
                },
                {
                    "dataset_table_entity_name": "clinical_anomalies",
                    "stage": "Exception",
                    "load_type": "Append",
                    "description": "Patient records with invalid vitals or dates",
                    "columns": [
                        {"name": "anomaly_id", "type": "BIGINT GENERATED ALWAYS AS IDENTITY"},
                        {"name": "patient_mrn", "type": "VARCHAR(32)"},
                        {"name": "anomaly_reason", "type": "TEXT"}
                    ]
                }
            ],
            "mappings": [
                {
                    "source_table": "clinical.patient_admissions",
                    "source_field": "adm_id",
                    "target_table": "patient_stay_fact",
                    "target_attribute": "admission_id"
                },
                {
                    "source_table": "clinical.patient_admissions",
                    "source_field": "mrn",
                    "target_table": "patient_stay_fact",
                    "target_attribute": "patient_mrn"
                }
            ],
            "rules": {
                "business_rules": [
                    {
                        "rule_id": "VITAL_CHK_01",
                        "condition": "length_of_stay_days >= 0",
                        "rule_name": "Valid Length of Stay"
                    }
                ]
            }
        }

        # 1. Discover target entities
        targets = discover_target_entities(healthcare_analysis, healthcare_analysis["mappings"])
        target_names = [t["table_name"] for t in targets]
        self.assertEqual(len(targets), 2)
        self.assertIn("patient_stay_fact", target_names)
        self.assertIn("clinical_anomalies", target_names)

        # Prohibited synthetic/hardcoded tables
        self.assertNotIn("stg_customer", target_names)
        self.assertNotIn("customer_sales_summary", target_names)
        self.assertNotIn("config_tables", target_names)
        self.assertNotIn("ctrl_balanced_dataset", target_names)

        # 2. Generate Target DDL
        ddl = generate_target_ddl("clinical_mart", "postgresql", healthcare_analysis["sources"], healthcare_analysis["rules"], healthcare_analysis["mappings"], analysis_data=healthcare_analysis)

        self.assertIn("CREATE TABLE IF NOT EXISTS clinical_mart.patient_stay_fact", ddl)
        self.assertIn("admission_id VARCHAR(64) NOT NULL", ddl)
        self.assertIn("patient_mrn VARCHAR(32) NOT NULL", ddl)
        self.assertIn("length_of_stay_days INTEGER", ddl)
        self.assertIn("total_charge_amt DECIMAL(12,2)", ddl)

        # Zero envelope columns
        self.assertNotIn("ctrl_id", ddl)
        self.assertNotIn("exec_seq", ddl)
        self.assertNotIn("execution_schedule", ddl)
        self.assertNotIn("config_tables", ddl)

    def test_02_airline_operations_model(self):
        """Test Airline Operations HLA model."""
        airline_analysis = {
            "document_title": "Flight Operations & Crew Scheduling",
            "sources": [
                {
                    "source_id": "SRC_OPS_01",
                    "source_system": "FLIGHT_OPS_DB",
                    "source_table": "operations.flight_schedule",
                    "load_type": "Truncate & load"
                }
            ],
            "data_model": [
                {
                    "dataset_table_entity_name": "flight_kpi_summary",
                    "stage": "Reporting",
                    "columns": [
                        {"name": "flight_number", "type": "VARCHAR(20)", "nullable": "NOT NULL"},
                        {"name": "departure_airport", "type": "VARCHAR(10)"},
                        {"name": "delay_minutes", "type": "INTEGER"},
                        {"name": "on_time_status", "type": "VARCHAR(20)"}
                    ]
                }
            ]
        }

        ddl = generate_target_ddl("airline_ops", "postgresql", airline_analysis["sources"], {}, [], analysis_data=airline_analysis)
        self.assertIn("CREATE TABLE IF NOT EXISTS airline_ops.flight_kpi_summary", ddl)
        self.assertIn("flight_number VARCHAR(20) NOT NULL", ddl)
        self.assertIn("delay_minutes INTEGER", ddl)
        self.assertNotIn("ctrl_id", ddl)
        self.assertNotIn("config_tables", ddl)


if __name__ == "__main__":
    unittest.main()
