"""
HLA Reconciliation Parser.
Extracts reconciliation definitions, participating datasets, keys, and comparison attributes.
"""

from typing import List, Dict, Any
from backend.hla.hla_model import HLAReconciliationRuleDef


class ReconciliationParser:
    """
    Parses reconciliation specifications from HLA workbooks.
    """

    @classmethod
    def parse_reconciliation_rules(cls, rows: List[Dict[str, Any]]) -> List[HLAReconciliationRuleDef]:
        rules: List[HLAReconciliationRuleDef] = []
        for idx, row in enumerate(rows, start=1):
            rule_id = str(row.get("rule_id") or f"RECON_{idx}").strip()
            name = str(row.get("reconciliation_name") or row.get("name") or rule_id).strip()
            primary = str(row.get("primary_entity") or row.get("dataset_a") or "PRIMARY").strip()
            secondary = str(row.get("secondary_entity") or row.get("dataset_b") or "SECONDARY").strip()
            key_raw = row.get("reconciliation_key") or row.get("key_value") or row.get("matching_keys") or []

            if isinstance(key_raw, str):
                keys = [k.strip() for k in key_raw.split(",") if k.strip()]
            elif isinstance(key_raw, list):
                keys = [str(k).strip() for k in key_raw if str(k).strip()]
            else:
                keys = []

            join_type = str(row.get("join_type") or "FULL_OUTER_JOIN").strip().upper()

            rules.append(HLAReconciliationRuleDef(
                rule_id=rule_id,
                reconciliation_name=name,
                primary_entity=primary,
                secondary_entity=secondary,
                reconciliation_key_attributes=keys,
                join_type=join_type
            ))

        return rules
