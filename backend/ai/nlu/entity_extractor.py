"""
Generic Entity Extractor for HLA Studio.
Extracts identifiers, components, requirements, table references, column names, rule codes,
and parameters dynamically from natural language without assuming hardcoded IDs.
"""

import re
from typing import Dict, Any, Optional


class EntityExtractor:
    """
    Extracts structured entities dynamically from natural language queries.
    """

    # Matches various identifier styles: "Control 23", "CTRL-24", "Doc 4", "Job 12", "Section A", "Process P1"
    IDENTIFIER_PATTERN = re.compile(
        r"\b(?:control|ctrl|doc|document|job|process|item)\s*[-#_]?\s*([a-zA-Z0-9_\-]+)\b",
        re.IGNORECASE
    )

    # Component pattern: e.g. "validation service", "processing layer", "landing zone", "quality monitor", "consumer layer"
    COMPONENT_QUERY_PATTERN = re.compile(
        r"(?:into|to|from|of|for|inside|in)\s+(?:the\s+)?([a-zA-Z0-9_\s]{3,35}?)(?:\?|\.|$|\s+and|\s+or|\s+receive|\s+produce|\s+work)",
        re.IGNORECASE
    )

    # Generic Rule pattern: "Rule 1", "R1", "BR-05", "Rule #12", "Rule_A", "REQ-01"
    RULE_PATTERN = re.compile(
        r"\b(?:rule|br|filter|transformation)\s*[-#_]?\s*([a-zA-Z0-9_\-]+)\b|\b(r\d{1,3})\b|\b(req[-_ ]?\d{1,3})\b",
        re.IGNORECASE
    )

    # Requirement pattern: "REQ-01", "REQ 2", "Requirement 1"
    REQ_PATTERN = re.compile(
        r"\b(?:requirement|req)\s*[-#_]?\s*(\d{1,3}|[a-zA-Z0-9_\-]+)\b",
        re.IGNORECASE
    )

    # Column / Attribute pattern
    COLUMN_PATTERN = re.compile(
        r"\b(?:column|attribute|field)\s+['\"]?([a-zA-Z0-9_]+)['\"]?",
        re.IGNORECASE
    )

    # Table / Dataset pattern
    TABLE_PATTERN = re.compile(
        r"\b(?:table|dataset|view|stream|file)\s+['\"]?([a-zA-Z0-9_\.]+)['\"]?",
        re.IGNORECASE
    )

    # Environment pattern
    ENV_PATTERN = re.compile(
        r"\b(dev(?:elopment)?|prod(?:uction)?|sandbox|test|staging|qa)\b",
        re.IGNORECASE
    )

    @classmethod
    def extract_control_number(cls, text: str) -> Optional[str]:
        if not text:
            return None
        m = cls.IDENTIFIER_PATTERN.search(text)
        if m:
            val = m.group(1).strip()
            if val.isdigit():
                return str(int(val))
            return val
        return None

    @classmethod
    def extract_entities(cls, text: str) -> Dict[str, Any]:
        """
        Extracts all identifiable architectural entities from the query.
        """
        clean_text = (text or "").strip()
        entities = {}

        # Generic Identifier / Control
        ident = cls.extract_control_number(clean_text)
        if ident:
            entities["control_number"] = ident
            entities["component_id"] = ident

        # Component Name detection from phrases like "what goes into validation service?"
        comp_m = cls.COMPONENT_QUERY_PATTERN.search(clean_text)
        if comp_m:
            raw_target = comp_m.group(1).strip()
            # Clean trailing words
            raw_target = re.sub(r"\b(service|layer|zone|monitor|engine|platform|component)\b", r"\1", raw_target, flags=re.IGNORECASE)
            if len(raw_target) >= 3 and not any(w in raw_target.lower() for w in ["the", "this", "that", "what", "which"]):
                entities["component_name"] = raw_target

        # Requirement detection
        req_m = cls.REQ_PATTERN.search(clean_text)
        if req_m:
            matched_req = req_m.group(0).upper().replace(" ", "-")
            entities["requirement_id"] = matched_req

        # Generic Rule
        rule_m = cls.RULE_PATTERN.search(clean_text)
        if rule_m:
            entities["rule_id"] = (rule_m.group(1) or rule_m.group(2) or rule_m.group(3) or "").upper()

        # Environment
        env_m = cls.ENV_PATTERN.search(clean_text)
        if env_m:
            env_val = env_m.group(1).lower()
            if "prod" in env_val:
                entities["environment"] = "prod"
            elif "dev" in env_val:
                entities["environment"] = "dev"
            else:
                entities["environment"] = env_val

        # Column / Field
        col_m = cls.COLUMN_PATTERN.search(clean_text)
        if col_m:
            entities["column"] = col_m.group(1)
        else:
            null_col_m = re.search(r"why\s+is\s+([a-zA-Z0-9_]+)\s+null", clean_text, re.IGNORECASE)
            if null_col_m:
                entities["column"] = null_col_m.group(1)

        # Table / Dataset
        tab_m = cls.TABLE_PATTERN.search(clean_text)
        if tab_m:
            entities["table_name"] = tab_m.group(1)

        return entities
