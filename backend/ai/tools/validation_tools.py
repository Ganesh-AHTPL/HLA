"""
Validation Tools for HLA Studio AI Architecture.
Validates SQL safety, schema constraints, and business rules.
"""

import re
from typing import Dict, Any, List

DANGEROUS_SQL_PATTERNS = re.compile(
    r"\b(DROP\s+TABLE|DROP\s+DATABASE|TRUNCATE|DELETE\s+FROM|ALTER\s+TABLE.*DROP|GRANT|REVOKE)\b",
    re.IGNORECASE
)


class ValidationTools:
    """
    Validation utilities to ensure zero unsafe execution.
    """

    @staticmethod
    def validate_sql_safety(sql: str) -> Dict[str, Any]:
        if not sql or not sql.strip():
            return {"safe": False, "reason": "SQL is empty"}

        match = DANGEROUS_SQL_PATTERNS.search(sql)
        if match:
            return {
                "safe": False,
                "reason": f"Disallowed destructive SQL keyword detected: '{match.group(1)}'"
            }

        return {"safe": True, "reason": "Passed read/safe DDL inspection"}
