"""
Migration Engine.
Performs safe, zero-data-loss schema migrations and physical column reordering (RULE 11, 20, 21).
"""

from typing import List, Tuple, Dict, Any, Optional
from sqlalchemy import text
from sqlalchemy.engine import Engine
from backend.schema.postgres_introspector import PostgresSchemaIntrospector
from backend.schema.column_order_validator import ColumnOrderValidator
from backend.schema.ddl_generator import DDLGenerator
from backend.core.result import ValidationResult
from backend.core.exceptions import MigrationFailedError


class MigrationEngine:
    """
    Safely migrates existing database tables to match the generic platform standard:
    - Removes obsolete auto-columns (e.g. id, batch_id) if not part of HLA
    - Enforces 4-prefix and 4-suffix envelope
    - Reorders physical columns safely using PostgreSQL table rebuild pattern
    - Preserves all rows and row count with transaction safety
    """

    def __init__(self, engine: Engine):
        self.engine = engine
        self.introspector = PostgresSchemaIntrospector(engine)

    def plan_table_migration(
        self,
        schema_name: str,
        table_name: str,
        target_business_columns: List[Tuple[str, str]]
    ) -> Dict[str, Any]:
        """
        Compares existing table structure with target schema and generates a migration plan.
        """
        current_meta = self.introspector.get_table_metadata(schema_name, table_name)
        if not current_meta.exists:
            # Table doesn't exist; simple CREATE is needed
            ddl = DDLGenerator.generate_create_table_ddl(schema_name, table_name, target_business_columns)
            return {
                "action": "CREATE",
                "schema_name": schema_name,
                "table_name": table_name,
                "current_columns": [],
                "target_columns": [c[0] for c in ColumnOrderValidator.enforce_envelope(target_business_columns)],
                "row_count": 0,
                "migration_needed": True,
                "sql_plan": [ddl]
            }

        # Table exists; compare physical columns
        current_cols = [c.lower() for c in self.introspector.get_physical_columns(schema_name, table_name)]
        target_envelope_cols = ColumnOrderValidator.enforce_envelope(target_business_columns)
        target_col_names = [c[0].lower() for c in target_envelope_cols]

        needs_rebuild = False
        if current_cols != target_col_names:
            needs_rebuild = True

        # Determine common columns to copy
        common_cols = [c for c in target_col_names if c in current_cols]

        return {
            "action": "REBUILD" if needs_rebuild else "NO_OP",
            "schema_name": schema_name,
            "table_name": table_name,
            "current_columns": current_cols,
            "target_columns": target_col_names,
            "common_columns": common_cols,
            "row_count": current_meta.row_count,
            "migration_needed": needs_rebuild
        }

    def execute_migration(
        self,
        schema_name: str,
        table_name: str,
        target_business_columns: List[Tuple[str, str]],
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Executes a zero-data-loss table rebuild migration if needed.
        """
        plan = self.plan_table_migration(schema_name, table_name, target_business_columns)
        if not plan["migration_needed"]:
            return {
                "success": True,
                "action": "NO_OP",
                "message": f"Table {schema_name}.{table_name} is already in canonical format.",
                "rows_preserved": plan["row_count"]
            }

        if dry_run:
            return {
                "success": True,
                "action": plan["action"],
                "dry_run": True,
                "plan": plan
            }

        schema_clean = schema_name.strip().strip('"').lower()
        table_clean = table_name.strip().strip('"').lower()

        if plan["action"] == "CREATE":
            ddl = DDLGenerator.generate_create_table_ddl(schema_clean, table_clean, target_business_columns)
            with self.engine.begin() as conn:
                conn.execute(text(ddl))
            return {
                "success": True,
                "action": "CREATE",
                "message": f"Table {schema_clean}.{table_clean} created successfully.",
                "rows_preserved": 0
            }

        # REBUILD process
        tmp_table = f"{table_clean}_rebuild_tmp"
        ddl_tmp = DDLGenerator.generate_create_table_ddl(
            schema_clean,
            tmp_table,
            target_business_columns,
            create_indexes=False
        )

        common_cols = plan["common_columns"]
        if not common_cols:
            raise MigrationFailedError(
                f"Cannot rebuild {schema_clean}.{table_clean}: no common columns found between existing and target schema.",
                entity=table_clean
            )

        cols_str = ", ".join([f'"{c}"' for c in common_cols])
        copy_sql = f'INSERT INTO "{schema_clean}"."{tmp_table}" ({cols_str}) SELECT {cols_str} FROM "{schema_clean}"."{table_clean}";'

        idx_name = f'idx_{table_clean[:40]}_exec'
        create_idx_sql = f'CREATE INDEX IF NOT EXISTS "{idx_name}" ON "{schema_clean}"."{table_clean}" ("ctrl_id", "exec_seq", "execution_date");'

        try:
            with self.engine.begin() as conn:
                # 1. Drop existing tmp if left from previous aborted run
                conn.execute(text(f'DROP TABLE IF EXISTS "{schema_clean}"."{tmp_table}" CASCADE;'))
                
                # 2. Create tmp table with new schema
                conn.execute(text(ddl_tmp))

                # 3. Copy existing data
                conn.execute(text(copy_sql))

                # 4. Verify count
                tmp_count = conn.execute(text(f'SELECT COUNT(*) FROM "{schema_clean}"."{tmp_table}"')).scalar()
                if tmp_count != plan["row_count"]:
                    raise MigrationFailedError(
                        f"Row count mismatch during migration of {table_clean}: original {plan['row_count']}, copied {tmp_count}",
                        entity=table_clean
                    )

                # 5. Drop original and rename tmp
                conn.execute(text(f'DROP TABLE "{schema_clean}"."{table_clean}" CASCADE;'))
                conn.execute(text(f'ALTER TABLE "{schema_clean}"."{tmp_table}" RENAME TO "{table_clean}";'))

                # 6. Recreate indexes
                conn.execute(text(create_idx_sql))

            return {
                "success": True,
                "action": "REBUILD",
                "message": f"Table {schema_clean}.{table_clean} migrated and reordered with zero data loss.",
                "rows_preserved": plan["row_count"]
            }
        except Exception as e:
            # Clean up tmp table if it failed
            try:
                with self.engine.begin() as conn:
                    conn.execute(text(f'DROP TABLE IF EXISTS "{schema_clean}"."{tmp_table}" CASCADE;'))
            except Exception:
                pass
            raise MigrationFailedError(
                f"Failed migrating table {schema_clean}.{table_clean}: {str(e)}",
                entity=table_clean
            )
