"""
Source metadata models separating Logical Stream, Physical Table, and Physical Column.
Enforces RULE 4 (no guessing) and RULE 5 (no stream names as column names).
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class PhysicalSourceColumn:
    column_name: str
    data_type: str
    is_nullable: bool = True
    ordinal_position: int = 0


@dataclass
class PhysicalSourceTable:
    schema_name: str
    table_name: str
    source_system: str
    columns: Dict[str, PhysicalSourceColumn] = field(default_factory=dict)
    exists_in_database: bool = False

    @property
    def qualified_name(self) -> str:
        return f'"{self.schema_name}"."{self.table_name}"'


@dataclass
class LogicalSourceStream:
    stream_name: str  # e.g. "VUTM/DOOS", "CMDB", "DDOS", "Circuit Reco", "SFDC", "Billing"
    source_system: str
    physical_schema: str
    physical_table: str
    description: str = ""
    is_required: bool = True
    resolved_physical_table: Optional[PhysicalSourceTable] = None


@dataclass
class AttributeMapping:
    logical_attribute_name: str
    logical_source_stream: str
    target_field_name: str
    target_data_type: str = "TEXT"
    physical_column_name: Optional[str] = None
    transformation_expression: Optional[str] = None
    is_derived: bool = False
    derivation_rule: Optional[str] = None
    hla_sheet_reference: Optional[str] = None
    hla_row_reference: Optional[int] = None
    resolution_status: str = "PENDING"  # PENDING, RESOLVED, UNRESOLVED
