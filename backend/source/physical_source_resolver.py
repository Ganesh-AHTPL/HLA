"""
Physical Source Resolver.
Resolves Logical Source Streams to physical database tables with introspection verification.
"""

from typing import Optional, Dict, Any
from sqlalchemy.engine import Engine
from backend.source.source_registry import SourceRegistry
from backend.source.source_metadata import LogicalSourceStream, PhysicalSourceTable, PhysicalSourceColumn
from backend.schema.postgres_introspector import PostgresSchemaIntrospector
from backend.core.exceptions import SourceDependencyMissingError


class PhysicalSourceResolver:
    """
    Validates that logical source streams map to real physical database tables.
    """

    def __init__(self, engine: Engine, registry: Optional[SourceRegistry] = None):
        self.engine = engine
        self.registry = registry or SourceRegistry()
        self.introspector = PostgresSchemaIntrospector(engine)

    def resolve_stream(self, logical_stream_name: str, control_id: Any = None) -> LogicalSourceStream:
        stream = self.registry.get_stream(logical_stream_name)
        if not stream:
            raise SourceDependencyMissingError(
                f"No physical source mapping found in registry for logical stream '{logical_stream_name}'.",
                control_id=control_id,
                source=logical_stream_name
            )

        # Introspect table in PostgreSQL
        meta = self.introspector.get_table_metadata(stream.physical_schema, stream.physical_table)
        if not meta.exists:
            raise SourceDependencyMissingError(
                f"Physical source table \"{stream.physical_schema}\".\"{stream.physical_table}\" does not exist in database for stream '{logical_stream_name}'.",
                control_id=control_id,
                source=f"{stream.physical_schema}.{stream.physical_table}"
            )

        # Populate physical columns
        phys_table = PhysicalSourceTable(
            schema_name=meta.schema_name,
            table_name=meta.table_name,
            source_system=stream.source_system,
            exists_in_database=True
        )

        for col_name, col_meta in meta.columns.items():
            phys_table.columns[col_name.lower()] = PhysicalSourceColumn(
                column_name=col_meta.column_name,
                data_type=col_meta.data_type,
                is_nullable=col_meta.is_nullable,
                ordinal_position=col_meta.ordinal_position
            )

        stream.resolved_physical_table = phys_table
        return stream
