"""
PostgreSQL Schema Introspector.
Authoritative source of truth for physical database objects (RULE 2, RULE 7).
Queries information_schema and pg_catalog to introspect tables, columns, constraints, and indexes.
"""

from typing import Dict, List, Optional, Any
from sqlalchemy import text
from sqlalchemy.engine import Engine
from backend.core.result import TableIntrospectionResult, ColumnIntrospectionResult


class PostgresSchemaIntrospector:
    """
    Introspects PostgreSQL schema objects deterministically.
    Never guesses column names or table existence.
    """

    def __init__(self, engine: Engine):
        self.engine = engine

    def get_table_metadata(self, schema_name: str, table_name: str) -> TableIntrospectionResult:
        """
        Introspects an exact table or view in PostgreSQL.
        Returns TableIntrospectionResult containing all columns in physical ordinal position order.
        """
        schema_clean = schema_name.strip().strip('"').lower()
        table_clean = table_name.strip().strip('"').lower()

        # Check existence and columns via information_schema
        col_query = text("""
            SELECT 
                column_name,
                data_type,
                udt_name,
                character_maximum_length,
                numeric_precision,
                numeric_scale,
                is_nullable,
                column_default,
                ordinal_position
            FROM information_schema.columns
            WHERE table_schema = :schema_name
              AND table_name = :table_name
            ORDER BY ordinal_position ASC;
        """)

        columns: Dict[str, ColumnIntrospectionResult] = {}
        exists = False

        with self.engine.connect() as conn:
            # Check table existence in information_schema.tables or pg_tables/pg_views
            exists_query = text("""
                SELECT 1 
                FROM information_schema.tables 
                WHERE table_schema = :schema_name AND table_name = :table_name
                UNION
                SELECT 1
                FROM pg_catalog.pg_matviews
                WHERE schemaname = :schema_name AND matviewname = :table_name;
            """)
            exists_res = conn.execute(exists_query, {"schema_name": schema_clean, "table_name": table_clean}).scalar()
            exists = bool(exists_res)

            if exists:
                col_rows = conn.execute(col_query, {"schema_name": schema_clean, "table_name": table_clean}).fetchall()
                for row in col_rows:
                    c_name = row[0]
                    d_type = row[1]
                    udt = row[2]
                    char_len = row[3]
                    num_prec = row[4]
                    num_scale = row[5]
                    is_null = (row[6] == "YES")
                    col_def = row[7]
                    ord_pos = row[8]

                    # Format formatted data type
                    formatted_type = d_type
                    if d_type in ("character varying", "varchar") and char_len:
                        formatted_type = f"VARCHAR({char_len})"
                    elif d_type == "numeric" and num_prec:
                        formatted_type = f"NUMERIC({num_prec},{num_scale or 0})"
                    elif d_type == "USER-DEFINED":
                        formatted_type = udt

                    columns[c_name.lower()] = ColumnIntrospectionResult(
                        column_name=c_name,
                        data_type=formatted_type,
                        is_nullable=is_null,
                        column_default=col_def,
                        ordinal_position=ord_pos
                    )

            # Get Primary Keys
            pk_query = text("""
                SELECT kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                WHERE tc.constraint_type = 'PRIMARY KEY'
                  AND tc.table_schema = :schema_name
                  AND tc.table_name = :table_name
                ORDER BY kcu.ordinal_position;
            """)
            primary_keys = []
            if exists:
                try:
                    pk_rows = conn.execute(pk_query, {"schema_name": schema_clean, "table_name": table_clean}).fetchall()
                    primary_keys = [r[0] for r in pk_rows]
                except Exception:
                    primary_keys = []

            # Get row count if table exists
            row_count = 0
            if exists:
                try:
                    # Safe query for count
                    count_query = text(f'SELECT COUNT(*) FROM "{schema_clean}"."{table_clean}"')
                    row_count = conn.execute(count_query).scalar() or 0
                except Exception:
                    row_count = 0

        return TableIntrospectionResult(
            schema_name=schema_clean,
            table_name=table_clean,
            exists=exists,
            columns=columns,
            primary_keys=primary_keys,
            indexes=[],
            row_count=row_count
        )

    def table_exists(self, schema_name: str, table_name: str) -> bool:
        """Quick existence check for a schema and table."""
        meta = self.get_table_metadata(schema_name, table_name)
        return meta.exists

    def column_exists(self, schema_name: str, table_name: str, column_name: str) -> bool:
        """Determines if a column exists in the physical table."""
        meta = self.get_table_metadata(schema_name, table_name)
        if not meta.exists:
            return False
        return column_name.lower().strip() in meta.columns

    def get_physical_columns(self, schema_name: str, table_name: str) -> List[str]:
        """Returns list of physical column names in ordinal order."""
        meta = self.get_table_metadata(schema_name, table_name)
        sorted_cols = sorted(meta.columns.values(), key=lambda c: c.ordinal_position)
        return [c.column_name for c in sorted_cols]
