"""
Control Service.
Provides business logic operations for discovering, loading, and analyzing HLA controls.
"""

from typing import Dict, Any, List, Optional
from sqlalchemy.engine import Engine
from backend.core.control_context import ControlContext
from backend.hla.hla_parser import HLAParser
from backend.hla.hla_model import HLAControl
from backend.source.dependency_resolver import DependencyResolver


class ControlService:
    """
    High-level service for HLA Control lifecycle and analysis.
    """

    def __init__(self, engine: Engine):
        self.engine = engine
        self.dep_resolver = DependencyResolver(engine)

    def analyze_hla_file(self, file_path: str, control_id_override: Optional[Any] = None) -> HLAControl:
        """
        Parses an uploaded HLA Excel file into the structured HLAControl model.
        """
        return HLAParser.parse_workbook(file_path, control_id_override=control_id_override)

    def validate_control_dependencies(self, hla: HLAControl, context: ControlContext) -> Dict[str, Any]:
        """
        Validates all external source streams and columns against PostgreSQL.
        """
        from backend.source.source_metadata import AttributeMapping
        attr_mappings = [
            AttributeMapping(
                logical_attribute_name=a.attribute_name,
                logical_source_stream=a.source_stream,
                target_field_name=a.target_field_name,
                target_data_type=a.data_type,
                is_derived=a.is_derived,
                derivation_rule=a.derivation_rule
            )
            for a in hla.attributes
        ]
        res = self.dep_resolver.validate_dependencies(
            context=context,
            required_streams=hla.get_source_stream_names(),
            attribute_mappings=attr_mappings
        )
        return res.to_dict()
