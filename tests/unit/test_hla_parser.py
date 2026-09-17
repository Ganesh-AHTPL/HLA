"""
Unit tests for HLAParser and HLA internal models.
"""

import unittest
from backend.hla.hla_model import HLAControl, HLASourceStreamDef, HLAAttributeDef
from backend.hla.attribute_mapper import AttributeMapper
from backend.hla.rule_parser import RuleParser
from backend.hla.reconciliation_parser import ReconciliationParser
from backend.hla.entity_parser import EntityParser


class TestHLAParser(unittest.TestCase):

    def test_attribute_mapper_parsing(self):
        sample_rows = [
            {
                "attribute_name": "Application_Name",
                "source_stream": "VUTM/DOOS",
                "target_field": "application_name",
                "data_type": "TEXT"
            },
            {
                "attribute_name": "Final_CMDB_Remarks",
                "source_stream": "Derived",
                "target_field": "final_cmdb_remarks",
                "derivation_rule": "COALESCE(remarks, 'N/A')"
            }
        ]
        attrs = AttributeMapper.parse_attributes_from_rows(sample_rows)
        self.assertEqual(len(attrs), 2)
        self.assertEqual(attrs[0].target_field_name, "application_name")
        self.assertFalse(attrs[0].is_derived)
        self.assertTrue(attrs[1].is_derived)

    def test_rule_parser_filter_and_kri(self):
        filter_rows = [
            {"rule_id": "R1", "condition": "status != 'INACTIVE'", "description": "Exclude inactive"}
        ]
        kri_rows = [
            {"kri_id": "KRI_01", "name": "Mismatched Status", "condition": "balance_type = 'YN'", "impact": "HIGH"}
        ]

        filters = RuleParser.parse_filter_rules(filter_rows)
        kris = RuleParser.parse_kri_rules(kri_rows)

        self.assertEqual(len(filters), 1)
        self.assertEqual(filters[0].rule_id, "R1")
        self.assertEqual(len(kris), 1)
        self.assertEqual(kris[0].impact_level, "HIGH")

    def test_entity_parser_stages(self):
        hla = HLAControl(
            control_id=99,
            control_name="Test Control 99",
            source_streams={
                "CMDB": HLASourceStreamDef(stream_name="CMDB", source_system="ITSM"),
                "VUTM": HLASourceStreamDef(stream_name="VUTM", source_system="Firewall")
            }
        )
        entities = EntityParser.plan_entities_for_control(hla)
        self.assertIn("SOURCE_CMDB", entities)
        self.assertIn("SOURCE_VUTM", entities)
        self.assertIn("WORKING_RL", entities)
        self.assertIn("WORKING_KL", entities)
        self.assertIn("WORK_ITEM_CURRENT_RUN", entities)
        self.assertIn("WORK_ITEM_HISTORICAL", entities)
        self.assertIn("NON_KRI_SUMMARY", entities)


if __name__ == "__main__":
    unittest.main()
