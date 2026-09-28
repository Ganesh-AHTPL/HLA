"""
Common NLU Intent Parser for HLA Studio.
Provider-independent intent classification supporting both deterministic pattern matching
and structured LLM classification without changing any HLA business logic.
Zero hardcoding of specific document names or numbers.
"""

import re
import json
import logging
from typing import Dict, Any, Tuple, Optional

logger = logging.getLogger("hla_ai.nlu.intent")

# Standardized HLA & Generic Architecture Intent Definitions
INTENT_LIST_COMPONENTS = "LIST_COMPONENTS"
INTENT_LIST_REQUIREMENTS = "LIST_REQUIREMENTS"
INTENT_COMPONENT_INPUT = "COMPONENT_INPUT"
INTENT_COMPONENT_OUTPUT = "COMPONENT_OUTPUT"
INTENT_EXPLAIN_ARCHITECTURE = "EXPLAIN_ARCHITECTURE"
INTENT_LIST_DEPENDENCIES = "LIST_DEPENDENCIES"
INTENT_LIST_SOURCE_TABLES = "LIST_SOURCE_TABLES"
INTENT_ANALYZE_NULL_VALUES = "ANALYZE_NULL_VALUES"
INTENT_BUILD_TARGET = "BUILD_TARGET"
INTENT_RECONCILIATION_LOGIC = "RECONCILIATION_LOGIC"
INTENT_CHECK_CONTROL = "CHECK_CONTROL"
INTENT_EXPLAIN_FAILURE = "EXPLAIN_FAILURE"
INTENT_MAKE_GENERIC = "MAKE_GENERIC"
INTENT_SUMMARIZE_PROJECT = "SUMMARIZE_PROJECT"
INTENT_GENERAL_HLA_EXPLAIN = "GENERAL_HLA_EXPLAIN"

INTENT_PATTERNS = [
    # 1. Architecture Components Queries
    (
        r"(?:show|list|get|find|what(?:\s+are)?)\s+(?:me\s+)?(?:the\s+)?(?:architecture\s+)?(?:components?|systems?|services?|modules?|layers?)",
        INTENT_LIST_COMPONENTS,
        0.96
    ),
    # 2. Requirements Queries
    (
        r"(?:show|list|get|find|what(?:\s+are)?)\s+(?:me\s+)?(?:the\s+)?(?:requirements?|acceptance\s+criteria|user\s+stories|specs?)",
        INTENT_LIST_REQUIREMENTS,
        0.96
    ),
    # 3. Component Input Queries ("what goes into validation service?", "input to X")
    (
        r"(?:what\s+(?:goes\s+into|is\s+the\s+input\s+to|does\s+.*receive|is\s+consumed\s+by)|input\s+(?:to|for))\s+([a-zA-Z0-9_\s\-]+)",
        INTENT_COMPONENT_INPUT,
        0.95
    ),
    # 4. Component Output Queries ("what comes out of processing layer?", "output of X")
    (
        r"(?:what\s+(?:comes\s+out\s+of|is\s+the\s+output\s+of|does\s+.*produce|is\s+emitted\s+by)|output\s+(?:from|of))\s+([a-zA-Z0-9_\s\-]+)",
        INTENT_COMPONENT_OUTPUT,
        0.95
    ),
    # 5. Architecture Explanation & Document Overview
    (
        r"(?:explain\s+(?:this\s+)?architecture|what\s+does\s+this\s+document\s+contain|explain\s+(?:this\s+)?document|describe\s+the\s+architecture|overview\s+of\s+(?:this\s+)?(?:document|architecture))",
        INTENT_EXPLAIN_ARCHITECTURE,
        0.95
    ),
    # 6. Dependencies & Interactions
    (
        r"(?:what\s+are\s+the\s+dependencies|show\s+(?:me\s+)?(?:the\s+)?(?:dependencies|interactions?|data\s+flow|inputs?\s+and\s+outputs?)|how\s+do\s+components\s+interact)",
        INTENT_LIST_DEPENDENCIES,
        0.95
    ),
    # 7. Build Target / Database Structure / Table Generation / Mappings
    (
        r"(?:make\s+(?:a\s+)?database\s+structure|create\s+tables|build\s+(?:the\s+)?target|generate\s+target|generate\s+ddl|create\s+target\s+schema|generate\s+sql|build\s+target\s+logic|show\s+mappings?|explain\s+(?:this\s+)?transformation)",
        INTENT_BUILD_TARGET,
        0.95
    ),
    # 8. Source Tables queries (all natural variations)
    (
        r"(?:(?:show|list|get|find|what|which|tell\s+me)\s+(?:are\s+)?(?:me\s+)?(?:the\s+)?(?:source\s+tables?|input\s+(?:tables?|datasets?|feeds?)|sources?|datasets?|tables?|streams?|raw\s+feeds?)|tables?\s+(?:that\s+are\s+sources|are\s+sources|coming\s+in|are\s+coming\s+in)|what\s+tables?\s+(?:are\s+)?coming\s+in)",
        INTENT_LIST_SOURCE_TABLES,
        0.95
    ),
    # 9. Null Value analysis
    (
        r"(?:why\s+is\s+.*null|analyze\s+null|check\s+null|null\s+values?|missing\s+values?)",
        INTENT_ANALYZE_NULL_VALUES,
        0.94
    ),
    # 10. Reconciliation logic & Rules (all natural variations)
    (
        r"(?:reconciliation\s+(?:logic|rules?|engine)|recon\s+logic|explain\s+(?:the\s+)?rules?|how\s+does\s+reconciliation\s+work|what\s+happens\s+after\s+filtering|explain\s+r1[0-5]|r1[0-5]|balance\s+rules?|business\s+rules?|filter\s+rules?)",
        INTENT_RECONCILIATION_LOGIC,
        0.94
    ),
    # 11. Explain failure / Run diagnostics
    (
        r"(?:why\s+(?:did\s+)?(?:(?:this\s+)?(?:process|job|run|it|control.*|execution.*)|this|it)?\s*fail|failure\s+reason|diagnose\s+(?:the\s+)?(?:failure|error|run)|what\s+went\s+wrong|execution\s+error)",
        INTENT_EXPLAIN_FAILURE,
        0.95
    ),
    # 12. Generic schema design rule
    (
        r"(?:make\s+(?:this|it)\s+generic|don['’]t\s+copy\s+source\s+directly|generic\s+(?:schema|design|tables?)|genericize)",
        INTENT_MAKE_GENERIC,
        0.96
    ),
    # 13. Check / Inspect specific control or component
    (
        r"(?:check|inspect|validate|review|describe|explain)\s+(?:control|ctrl|doc|component)\s*[-#_]?\s*[a-zA-Z0-9_\-]+",
        INTENT_CHECK_CONTROL,
        0.92
    ),
    # 14. Summarize project / workspace / document
    (
        r"(?:give\s+(?:me\s+)?(?:a\s+)?summary|summarize\s+(?:this\s+)?(?:project|workspace|document|controls?|hla)|list\s+(?:all\s+)?controls|project\s+(?:summary|status|controls))",
        INTENT_SUMMARIZE_PROJECT,
        0.94
    ),
]


def normalize_query_text(text: str) -> str:
    """
    Normalizes natural language variations, typos, abbreviations, and informal phrasing
    while preserving factual entity identifiers.
    """
    if not text:
        return ""
    
    t = text.lower().strip()
    
    # 1. Expand contractions
    t = re.sub(r"\bwhat['’]s\b", "what is", t)
    t = re.sub(r"\bthere['’]s\b", "there is", t)
    t = re.sub(r"\bhow['’]s\b", "how is", t)
    t = re.sub(r"\bdon['’]t\b", "do not", t)
    t = re.sub(r"\bcan['’]t\b", "cannot", t)

    # 2. Common informal abbreviations & typos
    typo_map = {
        r"\bwht\b": "what",
        r"\bshw\b": "show",
        r"\blst\b": "list",
        r"\bplz\b": "please",
        r"\bpls\b": "please",
        r"\btbls\b": "tables",
        r"\btbl\b": "table",
        r"\bsrcs\b": "sources",
        r"\bsrc\b": "source",
        r"\btgts\b": "targets",
        r"\btgt\b": "target",
        r"\breqs\b": "requirements",
        r"\breq\b": "requirement",
        r"\brqmnts\b": "requirements",
        r"\brqmnt\b": "requirement",
        r"\bcomps\b": "components",
        r"\bcomp\b": "component",
        r"\bdeps\b": "dependencies",
        r"\bdep\b": "dependency",
        r"\brecon\b": "reconciliation",
        r"\breco\b": "reconciliation",
    }
    for pattern, repl in typo_map.items():
        t = re.sub(pattern, repl, t)

    # 3. Clean extraneous whitespace
    t = re.sub(r"\s+", " ", t)
    return t


class IntentParser:
    """
    Parses user queries into structured intents with confidence scores.
    """

    @classmethod
    def parse_intent(cls, message: str) -> Tuple[str, float]:
        raw_text = (message or "").strip()
        if not raw_text:
            return INTENT_GENERAL_HLA_EXPLAIN, 0.5

        norm_text = normalize_query_text(raw_text)

        for pattern, intent, conf in INTENT_PATTERNS:
            if re.search(pattern, raw_text, re.IGNORECASE) or re.search(pattern, norm_text, re.IGNORECASE):
                return intent, conf

        return INTENT_GENERAL_HLA_EXPLAIN, 0.7

    @classmethod
    def parse_structured_json(cls, raw_llm_response: str) -> Optional[Dict[str, Any]]:
        if not raw_llm_response or "{" not in raw_llm_response:
            return None

        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_llm_response, re.DOTALL)
        candidate = json_match.group(1) if json_match else None

        if not candidate:
            json_match = re.search(r"(\{[\s\S]*\})", raw_llm_response)
            if json_match:
                candidate = json_match.group(1)

        if candidate:
            try:
                data = json.loads(candidate)
                if isinstance(data, dict) and "intent" in data:
                    return data
            except Exception:
                pass
        return None
