"""
HLA Rule Parser.
Extracts Filtering Rules and KRI/Non-KRI definitions from HLA structured sheets.
"""

from typing import List, Dict, Any
from backend.hla.hla_model import HLAFilterRuleDef, HLAKRIRuleDef, HLABalanceRuleDef


class RuleParser:
    """
    Parses business rules, filter criteria, and KRI rules from HLA inputs.
    """

    @classmethod
    def parse_filter_rules(cls, rows: List[Dict[str, Any]]) -> List[HLAFilterRuleDef]:
        rules: List[HLAFilterRuleDef] = []
        for idx, row in enumerate(rows, start=1):
            rule_id = str(row.get("rule_id") or f"R{idx}").strip()
            entity = str(row.get("entity_name") or row.get("dataset") or "PRIMARY").strip()
            condition = str(row.get("condition") or row.get("filter_condition") or row.get("logic") or "").strip()
            desc = str(row.get("description") or row.get("remarks") or "").strip()
            ex_type = str(row.get("exclusion_type") or "ROW_FILTER").strip()

            if condition or desc:
                rules.append(HLAFilterRuleDef(
                    rule_id=rule_id,
                    entity_name=entity,
                    filter_condition=condition,
                    description=desc,
                    exclusion_type=ex_type
                ))
        return rules

    @classmethod
    def parse_kri_rules(cls, rows: List[Dict[str, Any]]) -> List[HLAKRIRuleDef]:
        kris: List[HLAKRIRuleDef] = []
        for idx, row in enumerate(rows, start=1):
            kri_id = str(row.get("kri_id") or f"KRI_{idx}").strip()
            kri_name = str(row.get("kri_name") or row.get("name") or kri_id).strip()
            condition = str(row.get("condition") or row.get("logic") or "").strip()
            outcome = str(row.get("outcome") or row.get("classification") or "KRI").strip()
            impact = str(row.get("impact") or "MEDIUM").strip()
            desc = str(row.get("description") or "").strip()

            if condition or kri_name:
                kris.append(HLAKRIRuleDef(
                    kri_id=kri_id,
                    kri_name=kri_name,
                    condition_expression=condition,
                    outcome_classification=outcome,
                    impact_level=impact,
                    description=desc
                ))
        return kris
