"""
Internal HLA Model.
Structured representation of an HLA workbook/control specification (RULE 1, RULE 5, RULE 12).
Separates logical streams, attributes, filtering rules, reconciliation rules, KRI rules, and target entities.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple


@dataclass
class HLASourceStreamDef:
    stream_name: str
    source_system: str
    description: str = ""
    is_primary: bool = False
    attributes: List[str] = field(default_factory=list)


@dataclass
class HLAAttributeDef:
    attribute_name: str
    source_stream: str
    target_field_name: str
    data_type: str = "TEXT"
    is_derived: bool = False
    derivation_rule: Optional[str] = None
    sheet_reference: Optional[str] = None
    row_reference: Optional[int] = None


@dataclass
class HLAFilterRuleDef:
    rule_id: str
    entity_name: str
    filter_condition: str
    description: str = ""
    exclusion_type: str = "ROW_FILTER"  # NULL_KEY, DEDUPLICATION, CONFIG_EXCLUSION


@dataclass
class HLABalanceRuleDef:
    rule_id: str
    entity_name: str
    source_entity: str
    balance_logic: str = ""
    description: str = ""


@dataclass
class HLAReconciliationRuleDef:
    rule_id: str
    reconciliation_name: str
    primary_entity: str
    secondary_entity: str
    reconciliation_key_attributes: List[str] = field(default_factory=list)
    join_type: str = "FULL_OUTER_JOIN"
    comparison_attributes: List[str] = field(default_factory=list)
    output_fields: List[str] = field(default_factory=list)


@dataclass
class HLAKRIRuleDef:
    kri_id: str
    kri_name: str
    condition_expression: str
    outcome_classification: str
    impact_level: str = "MEDIUM"
    description: str = ""


@dataclass
class HLAWorkItemRuleDef:
    rule_id: str
    target_table_name: str
    source_stage: str
    retention_policy: str = "HISTORICAL"  # CURRENT_RUN, HISTORICAL


@dataclass
class HLAReportRuleDef:
    report_name: str
    report_type: str  # SUMMARY, DETAILS, KRI_SUMMARY, CASE_SUMMARY
    source_entity: str
    group_by_columns: List[str] = field(default_factory=list)
    aggregation_expressions: Dict[str, str] = field(default_factory=dict)


@dataclass
class HLAEntityDef:
    entity_name: str
    stage: str
    table_pattern: str
    business_columns: List[Tuple[str, str]] = field(default_factory=list)
    source_streams: List[str] = field(default_factory=list)
    description: str = ""


@dataclass
class HLAControl:
    """
    Complete in-memory model of an HLA specification.
    """
    control_id: Any
    control_name: str
    hla_version: str = "1.0"
    source_streams: Dict[str, HLASourceStreamDef] = field(default_factory=dict)
    attributes: List[HLAAttributeDef] = field(default_factory=list)
    entities: Dict[str, HLAEntityDef] = field(default_factory=dict)
    filter_rules: List[HLAFilterRuleDef] = field(default_factory=list)
    balance_rules: List[HLABalanceRuleDef] = field(default_factory=list)
    reconciliation_rules: List[HLAReconciliationRuleDef] = field(default_factory=list)
    kri_rules: List[HLAKRIRuleDef] = field(default_factory=list)
    work_items: List[HLAWorkItemRuleDef] = field(default_factory=list)
    reports: List[HLAReportRuleDef] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_source_stream_names(self) -> List[str]:
        return list(self.source_streams.keys())
