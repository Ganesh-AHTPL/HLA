"""
HLA Attribute Mapper.
Extracts and normalizes attribute definitions from HLA workbook data.
"""

from typing import List, Dict, Any, Optional
from backend.hla.hla_model import HLAAttributeDef


class AttributeMapper:
    """
    Parses and standardizes HLA attribute mappings.
    """

    @classmethod
    def parse_attributes_from_rows(cls, rows: List[Dict[str, Any]], sheet_name: str = "Attribute Mapping") -> List[HLAAttributeDef]:
        attributes: List[HLAAttributeDef] = []

        for idx, row in enumerate(rows, start=1):
            attr_name = str(row.get("attribute_name") or row.get("field_name") or row.get("target_attribute") or "").strip()
            if not attr_name:
                continue

            source_stream = str(row.get("source_stream") or row.get("source_system") or row.get("source_field") or "Derived").strip()
            target_field = str(row.get("target_field") or row.get("target_column") or attr_name).strip().lower().replace(" ", "_")
            data_type = str(row.get("data_type") or "TEXT").strip().upper()
            derivation = row.get("derivation_rule") or row.get("business_logic") or row.get("transformation")
            is_derived = bool(derivation or source_stream.lower() in ("derived", "formula", "calculated", "system"))

            attributes.append(HLAAttributeDef(
                attribute_name=attr_name,
                source_stream=source_stream,
                target_field_name=target_field,
                data_type=data_type,
                is_derived=is_derived,
                derivation_rule=str(derivation) if derivation else None,
                sheet_reference=sheet_name,
                row_reference=idx
            ))

        return attributes
