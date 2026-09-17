"""
Schema and DDL Validator.
Ensures zero violations of platform standards before any DDL is executed (RULE 10).
"""

import re
from typing import List, Set
from backend.core.result import ValidationResult
from backend.core.constants import (
    FORBIDDEN_SYNTHETIC_COLUMN_PREFIXES,
    FORBIDDEN_AUTO_COLUMNS
)

# External source schemas that must NEVER be created as target tables (RULE 6, RULE 44)
EXTERNAL_SOURCE_SCHEMAS: Set[str] = {
    "cmdb",
    "pearl",
    "sfdc",
    "qlik_report",
    "ra",
    "reports"
}


class SchemaValidator:
    """
    Validates table schemas, column configurations, and DDL scripts.
    """

    @classmethod
    def validate_target_schema_name(cls, schema_name: str) -> ValidationResult:
        res = ValidationResult(is_valid=True)
        schema_clean = schema_name.strip().strip('"').lower()

        if schema_clean in EXTERNAL_SOURCE_SCHEMAS:
            res.add_error(
                f"Invalid target schema '{schema_name}'. Cannot target external source schema (RULE 6, RULE 44)."
            )

        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_\.]*$', schema_clean):
            res.add_error(f"Target schema name '{schema_name}' contains illegal characters.")

        return res

    @classmethod
    def validate_ddl_statement(cls, ddl: str) -> ValidationResult:
        res = ValidationResult(is_valid=True)
        ddl_lower = ddl.lower()

        # Check for forbidden synthetic prefixes
        for prefix in FORBIDDEN_SYNTHETIC_COLUMN_PREFIXES:
            if prefix.lower() in ddl_lower:
                res.add_error(f"DDL contains forbidden synthetic column reference: '{prefix}'")

        # Check for forbidden destructive commands
        if "drop database" in ddl_lower:
            res.add_error("DDL contains forbidden DROP DATABASE statement.")

        return res
