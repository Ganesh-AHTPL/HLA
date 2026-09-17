"""
Structured exception hierarchy for HLA Studio generic ETL & Reconciliation Engine.
Enforces RULE 7 (no silent fallback), RULE 9, RULE 10 (validation before exec).
"""

from typing import Optional, Dict, Any


class HLAStudioError(Exception):
    """Base exception for all HLA Studio domain and operational errors."""
    error_code: str = "HLA_STUDIO_ERROR"

    def __init__(
        self,
        message: str,
        control_id: Optional[Any] = None,
        stage: Optional[str] = None,
        entity: Optional[str] = None,
        source: Optional[str] = None,
        target: Optional[str] = None,
        column: Optional[str] = None,
        hla_reference: Optional[str] = None,
        reason: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.control_id = control_id
        self.stage = stage
        self.entity = entity
        self.source = source
        self.target = target
        self.column = column
        self.hla_reference = hla_reference
        self.reason = reason or message
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_code": self.error_code,
            "message": self.message,
            "control_id": self.control_id,
            "stage": self.stage,
            "entity": self.entity,
            "source": self.source,
            "target": self.target,
            "column": self.column,
            "hla_reference": self.hla_reference,
            "reason": self.reason,
            "details": self.details
        }


class SourceDependencyMissingError(HLAStudioError):
    """Raised when an external source table or view does not exist in PostgreSQL."""
    error_code = "SOURCE_DEPENDENCY_MISSING"


class SourceColumnDependencyMissingError(HLAStudioError):
    """Raised when a referenced column does not exist on the verified physical source table."""
    error_code = "SOURCE_COLUMN_DEPENDENCY_MISSING"


class HLAMappingMissingError(HLAStudioError):
    """Raised when an attribute required by HLA has no valid mapping to a logical/physical stream."""
    error_code = "HLA_MAPPING_MISSING"


class DerivationDependencyMissingError(HLAStudioError):
    """Raised when a derived business field or KRI calculation cannot resolve its input dependencies."""
    error_code = "DERIVATION_DEPENDENCY_MISSING"


class ReconciliationKeyMissingError(HLAStudioError):
    """Raised when participating reconciliation datasets lack a resolved matching KEY_VALUE."""
    error_code = "RECONCILIATION_KEY_MISSING"


class TargetSchemaInvalidError(HLAStudioError):
    """Raised when the target schema is invalid, inaccessible, or conflicts with external source schemas."""
    error_code = "TARGET_SCHEMA_INVALID"


class TargetColumnMissingError(HLAStudioError):
    """Raised when target physical schema lacks a required column during validation."""
    error_code = "TARGET_COLUMN_MISSING"


class DDLValidationFailedError(HLAStudioError):
    """Raised when generated DDL violates envelope ordering, constraints, or contains forbidden columns."""
    error_code = "DDL_VALIDATION_FAILED"


class SQLValidationFailedError(HLAStudioError):
    """Raised when generated SQL syntax, identifier, or schema validation fails before execution."""
    error_code = "SQL_VALIDATION_FAILED"


class MigrationFailedError(HLAStudioError):
    """Raised when a safe table migration or column reordering step fails."""
    error_code = "MIGRATION_FAILED"


class DeploymentFailedError(HLAStudioError):
    """Raised when any deployment phase fails quality gates or execution."""
    error_code = "DEPLOYMENT_FAILED"


class ExecutionFailedError(HLAStudioError):
    """Raised when pipeline execution encounters a runtime failure during stage processing."""
    error_code = "EXECUTION_FAILED"
