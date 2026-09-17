"""
Core module exports for HLA Studio.
"""

from backend.core.constants import *
from backend.core.exceptions import *
from backend.core.result import *
from backend.core.control_context import ControlContext
from backend.core.execution_context import ExecutionContext

__all__ = [
    "ControlContext",
    "ExecutionContext",
    "ValidationResult",
    "DeploymentResult",
    "ExecutionResult",
    "TableIntrospectionResult",
    "ColumnIntrospectionResult",
    "HLAStudioError",
    "SourceDependencyMissingError",
    "SourceColumnDependencyMissingError",
    "HLAMappingMissingError",
    "DerivationDependencyMissingError",
    "ReconciliationKeyMissingError",
    "TargetSchemaInvalidError",
    "TargetColumnMissingError",
    "DDLValidationFailedError",
    "SQLValidationFailedError",
    "MigrationFailedError",
    "DeploymentFailedError",
    "ExecutionFailedError",
    "PLATFORM_HEADER_COLUMNS",
    "PLATFORM_HEADER_NAMES",
    "PLATFORM_FOOTER_COLUMNS",
    "PLATFORM_FOOTER_NAMES",
    "ALL_PLATFORM_COLUMNS",
    "FORBIDDEN_AUTO_COLUMNS",
    "FORBIDDEN_SYNTHETIC_COLUMN_PREFIXES",
    "CANONICAL_STAGES",
    "STAGE_1_ACQUISITION",
    "STAGE_2_FILTERING",
    "STAGE_3_BALANCE",
    "STAGE_4_RECONCILIATION",
    "STAGE_5_KRI_NON_KRI",
    "STAGE_6_CURRENT_RUN_WORK_ITEM",
    "STAGE_7_HISTORICAL_WORK_ITEM",
    "STAGE_8_REPORTING",
    "PATTERN_ACQUISITION_TABLE",
    "PATTERN_FILTERED_TABLE",
    "PATTERN_FILTER_SUMMARY",
    "PATTERN_BALANCE_TABLE",
    "PATTERN_BALANCE_SUMMARY",
    "PATTERN_WORKING_RL",
    "PATTERN_WORKING_KL",
    "PATTERN_WORK_ITEM_CURRENT_RUN",
    "PATTERN_WORK_ITEM_HISTORICAL",
    "PATTERN_NON_KRI_SUMMARY",
    "PATTERN_NON_KRI_DETAILS",
    "PATTERN_KRI_SUMMARY",
    "PATTERN_CASE_SUMMARY",
    "RECON_MATCH_TYPE_YY",
    "RECON_MATCH_TYPE_YN",
    "RECON_MATCH_TYPE_NY",
]
