"""
Dependency Resolver and Pre-Flight Quality Gate.
Enforces RULE 6, RULE 7, RULE 9, and RULE 10 before any DDL/SQL is generated or deployed.
"""

from typing import List, Dict, Any, Optional
from sqlalchemy.engine import Engine
from backend.source.physical_source_resolver import PhysicalSourceResolver
from backend.source.column_resolver import ColumnResolver
from backend.source.source_metadata import AttributeMapping, LogicalSourceStream
from backend.core.control_context import ControlContext
from backend.core.result import ValidationResult
from backend.core.exceptions import (
    SourceDependencyMissingError,
    SourceColumnDependencyMissingError,
    HLAMappingMissingError,
    DerivationDependencyMissingError
)


class DependencyResolver:
    """
    Validates all external source streams and attribute mappings against real PostgreSQL metadata.
    """

    def __init__(self, engine: Engine):
        self.engine = engine
        self.source_resolver = PhysicalSourceResolver(engine)
        self.column_resolver = ColumnResolver(engine, self.source_resolver)

    def validate_dependencies(
        self,
        context: ControlContext,
        required_streams: List[str],
        attribute_mappings: List[AttributeMapping]
    ) -> ValidationResult:
        """
        Validates all tables and columns needed for the control.
        Returns ValidationResult with detailed diagnostics.
        """
        res = ValidationResult(is_valid=True)
        resolved_streams: Dict[str, LogicalSourceStream] = {}

        # 1. Validate External Source Tables
        for stream_name in required_streams:
            if not stream_name or stream_name.lower() in ("derived", "formula", "calculated", "system"):
                continue
            try:
                stream_obj = self.source_resolver.resolve_stream(stream_name, control_id=context.control_id)
                resolved_streams[stream_name.lower()] = stream_obj
            except SourceDependencyMissingError as e:
                res.add_error(f"SOURCE_DEPENDENCY_MISSING: {e.message}")
            except Exception as e:
                res.add_error(f"SOURCE_DEPENDENCY_ERROR for '{stream_name}': {str(e)}")

        # 2. Validate Attribute Mappings and Physical Columns
        for mapping in attribute_mappings:
            try:
                self.column_resolver.resolve_mapping(mapping, control_id=context.control_id)
            except SourceColumnDependencyMissingError as e:
                res.add_error(f"SOURCE_COLUMN_DEPENDENCY_MISSING: {e.message}")
            except HLAMappingMissingError as e:
                res.add_error(f"HLA_MAPPING_MISSING: {e.message}")
            except Exception as e:
                res.add_error(f"MAPPING_ERROR on '{mapping.target_field_name}': {str(e)}")

        res.details = {
            "control_id": context.control_id,
            "validated_streams_count": len(resolved_streams),
            "validated_attributes_count": len(attribute_mappings),
            "resolved_streams": list(resolved_streams.keys())
        }

        return res
