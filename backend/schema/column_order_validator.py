"""
Column Order Validator.
Validates that table schemas and column lists follow the mandatory 4-prefix and 4-suffix envelope (RULE 19, 39, 58).
"""

from typing import List, Tuple
from backend.core.constants import (
    PLATFORM_HEADER_NAMES,
    PLATFORM_FOOTER_NAMES,
    FORBIDDEN_AUTO_COLUMNS
)
from backend.core.result import ValidationResult


class ColumnOrderValidator:
    """
    Ensures physical and logical tables strictly follow the platform envelope:
    1. ctrl_id
    2. exec_seq
    3. execution_date
    4. execution_schedule
    ... [business columns] ...
    -4. create_dtm
    -3. update_dtm
    -2. updated_by
    -1. processing_date
    """

    @classmethod
    def validate_column_sequence(cls, columns: List[str], table_name: str = "") -> ValidationResult:
        res = ValidationResult(is_valid=True)
        col_lower = [c.strip().lower() for c in columns if c and c.strip()]

        if len(col_lower) < 8:
            res.add_error(
                f"Table '{table_name}' has only {len(col_lower)} columns. Minimum 8 required for platform envelope."
            )
            return res

        # 1. Validate First Four (Header)
        actual_first_four = col_lower[:4]
        for i, (expected, actual) in enumerate(zip(PLATFORM_HEADER_NAMES, actual_first_four)):
            if expected != actual:
                res.add_error(
                    f"Table '{table_name}' position {i+1} must be '{expected}', found '{actual}'."
                )

        # 2. Validate Last Four (Footer)
        actual_last_four = col_lower[-4:]
        for i, (expected, actual) in enumerate(zip(PLATFORM_FOOTER_NAMES, actual_last_four)):
            if expected != actual:
                pos_from_end = 4 - i
                res.add_error(
                    f"Table '{table_name}' position -{pos_from_end} must be '{expected}', found '{actual}'."
                )

        # 3. Check for forbidden columns in business columns
        business_cols = col_lower[4:-4]
        for col in business_cols:
            if col in FORBIDDEN_AUTO_COLUMNS:
                res.add_warning(
                    f"Table '{table_name}' contains potentially forbidden auto-column '{col}' in business section."
                )

        return res

    @classmethod
    def enforce_envelope(cls, business_columns: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
        """
        Takes list of (col_name, col_type) for business columns and wraps them
        with the mandatory platform header and footer.
        Filters out any accidentally repeated envelope columns.
        """
        from backend.core.constants import PLATFORM_HEADER_COLUMNS, PLATFORM_FOOTER_COLUMNS

        seen = set(PLATFORM_HEADER_NAMES + PLATFORM_FOOTER_NAMES)
        filtered_business: List[Tuple[str, str]] = []

        for name, col_type in business_columns:
            name_clean = name.strip().lower()
            if name_clean not in seen:
                filtered_business.append((name_clean, col_type))
                seen.add(name_clean)

        return PLATFORM_HEADER_COLUMNS + filtered_business + PLATFORM_FOOTER_COLUMNS
