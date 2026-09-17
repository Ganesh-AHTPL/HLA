"""
Deterministic DDL Generator.
Produces CREATE TABLE and INDEX statements strictly conforming to the 4-prefix and 4-suffix platform envelope.
"""

from typing import List, Tuple, Dict, Any, Optional
from backend.schema.column_order_validator import ColumnOrderValidator
from backend.core.constants import PLATFORM_HEADER_COLUMNS, PLATFORM_FOOTER_COLUMNS


class DDLGenerator:
    """
    Generates deterministic, compliant PostgreSQL DDL for HLA Studio target entities.
    """

    @classmethod
    def generate_create_table_ddl(
        cls,
        schema_name: str,
        table_name: str,
        business_columns: List[Tuple[str, str]],
        primary_key_columns: Optional[List[str]] = None,
        create_indexes: bool = True
    ) -> str:
        """
        Generates full CREATE TABLE DDL with envelope columns, clean types, and index statements.
        """
        schema_clean = schema_name.strip().strip('"').lower()
        table_clean = table_name.strip().strip('"').lower()

        # Enforce envelope columns
        full_columns = ColumnOrderValidator.enforce_envelope(business_columns)

        col_defs = []
        for col_name, col_type in full_columns:
            clean_name = col_name.strip().lower()
            clean_type = col_type.strip()
            col_defs.append(f'    "{clean_name}" {clean_type}')

        # Add composite primary key if specified
        if primary_key_columns:
            pk_cols_quoted = [f'"{col.strip().lower()}"' for col in primary_key_columns]
            col_defs.append(f'    PRIMARY KEY ({", ".join(pk_cols_quoted)})')

        lines = [
            f'CREATE SCHEMA IF NOT EXISTS "{schema_clean}";',
            f'CREATE TABLE IF NOT EXISTS "{schema_clean}"."{table_clean}" (',
            ",\n".join(col_defs),
            ');'
        ]

        # Add standard envelope index for performance
        if create_indexes:
            idx_name = f'idx_{table_clean[:40]}_exec'
            lines.append(
                f'CREATE INDEX IF NOT EXISTS "{idx_name}" ON "{schema_clean}"."{table_clean}" ("ctrl_id", "exec_seq", "execution_date");'
            )

        return "\n".join(lines)
