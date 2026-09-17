"""
Authoritative HLA Parser.
Parses Excel workbooks into structured HLAControl models (RULE 1, RULE 52).
Ensures downstream generators operate strictly on structured metadata and never raw unvalidated text.
"""

import os
from typing import Dict, Any, List, Optional
import openpyxl
from backend.hla.hla_model import (
    HLAControl,
    HLASourceStreamDef,
    HLAAttributeDef,
    HLAEntityDef,
    HLAFilterRuleDef,
    HLABalanceRuleDef,
    HLAReconciliationRuleDef,
    HLAKRIRuleDef,
    HLAWorkItemRuleDef,
    HLAReportRuleDef
)
from backend.hla.attribute_mapper import AttributeMapper
from backend.hla.rule_parser import RuleParser
from backend.hla.reconciliation_parser import ReconciliationParser
from backend.hla.entity_parser import EntityParser
import excel_analyzer


class HLAParser:
    """
    Parses HLA Excel specifications into a strongly-typed HLAControl object.
    """

    @classmethod
    def parse_workbook(cls, file_path: str, control_id_override: Optional[Any] = None) -> HLAControl:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"HLA Excel file not found: {file_path}")

        # Run core dynamic Excel analysis
        analysis = excel_analyzer.analyze_excel_specification(file_path)

        control_meta = analysis.get("control_metadata", {})
        cid = control_id_override or control_meta.get("control_id") or "UNKNOWN"
        cname = control_meta.get("control_name") or f"Control {cid}"
        hver = control_meta.get("hla_version") or "1.0"

        hla = HLAControl(
            control_id=cid,
            control_name=cname,
            hla_version=hver,
            metadata=analysis
        )

        # 1. Parse Source Systems and Logical Streams
        source_systems_raw = analysis.get("source_systems", [])
        for s in source_systems_raw:
            sname = s.get("source_name") or s.get("system_name") or "Unknown"
            hla.source_streams[sname] = HLASourceStreamDef(
                stream_name=sname,
                source_system=s.get("system_name") or sname,
                description=s.get("description", "")
            )

        # 2. Parse Attribute Mappings
        attr_rows = analysis.get("attribute_mappings", [])
        if attr_rows:
            hla.attributes = AttributeMapper.parse_attributes_from_rows(attr_rows)
            # Ensure any stream referenced in attributes is registered in source_streams
            for attr in hla.attributes:
                stream_name = attr.source_stream.strip()
                if stream_name and stream_name.lower() not in ("derived", "formula", "calculated", "system"):
                    if stream_name not in hla.source_streams:
                        hla.source_streams[stream_name] = HLASourceStreamDef(
                            stream_name=stream_name,
                            source_system=stream_name
                        )

        # 3. Parse Filter Rules
        filter_rows = analysis.get("filtering_rules", []) or analysis.get("filter_rules", [])
        if filter_rows:
            hla.filter_rules = RuleParser.parse_filter_rules(filter_rows)

        # 4. Parse Reconciliation Rules
        recon_rows = analysis.get("reconciliation_rules", [])
        if recon_rows:
            hla.reconciliation_rules = ReconciliationParser.parse_reconciliation_rules(recon_rows)

        # 5. Parse KRI Rules
        kri_rows = analysis.get("kri_rules", [])
        if kri_rows:
            hla.kri_rules = RuleParser.parse_kri_rules(kri_rows)

        # 6. Plan target entities for the 8 stages
        hla.entities = EntityParser.plan_entities_for_control(hla)

        return hla
