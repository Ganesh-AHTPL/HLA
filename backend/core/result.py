"""
Result models for validation, planning, migration, deployment, and execution.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime


@dataclass
class ValidationResult:
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def add_error(self, error: str):
        self.is_valid = False
        self.errors.append(error)

    def add_warning(self, warning: str):
        self.warnings.append(warning)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "details": self.details
        }


@dataclass
class ColumnIntrospectionResult:
    column_name: str
    data_type: str
    is_nullable: bool
    column_default: Optional[str] = None
    ordinal_position: int = 0
    is_primary_key: bool = False


@dataclass
class TableIntrospectionResult:
    schema_name: str
    table_name: str
    exists: bool
    columns: Dict[str, ColumnIntrospectionResult] = field(default_factory=dict)
    primary_keys: List[str] = field(default_factory=list)
    indexes: List[Dict[str, Any]] = field(default_factory=list)
    row_count: int = 0


@dataclass
class DeploymentResult:
    success: bool
    control_id: Any
    deployment_id: Optional[str] = None
    executed_statements: List[str] = field(default_factory=list)
    created_entities: List[str] = field(default_factory=list)
    migrated_entities: List[str] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "control_id": self.control_id,
            "deployment_id": self.deployment_id,
            "executed_statements": self.executed_statements,
            "created_entities": self.created_entities,
            "migrated_entities": self.migrated_entities,
            "errors": self.errors,
            "warnings": self.warnings,
            "duration_seconds": (self.end_time - self.start_time).total_seconds() if self.start_time and self.end_time else 0
        }


@dataclass
class ExecutionResult:
    success: bool
    control_id: Any
    exec_seq: int
    execution_date: str
    execution_schedule: str
    stages_executed: List[Dict[str, Any]] = field(default_factory=list)
    total_records_processed: int = 0
    errors: List[Dict[str, Any]] = field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "control_id": self.control_id,
            "exec_seq": self.exec_seq,
            "execution_date": self.execution_date,
            "execution_schedule": self.execution_schedule,
            "stages_executed": self.stages_executed,
            "total_records_processed": self.total_records_processed,
            "errors": self.errors,
            "duration_seconds": (self.end_time - self.start_time).total_seconds() if self.start_time and self.end_time else 0
        }
