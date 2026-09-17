"""
Source resolution and dependency validation exports.
"""

from backend.source.source_metadata import (
    PhysicalSourceColumn,
    PhysicalSourceTable,
    LogicalSourceStream,
    AttributeMapping
)
from backend.source.source_registry import SourceRegistry
from backend.source.physical_source_resolver import PhysicalSourceResolver
from backend.source.column_resolver import ColumnResolver
from backend.source.dependency_resolver import DependencyResolver

__all__ = [
    "PhysicalSourceColumn",
    "PhysicalSourceTable",
    "LogicalSourceStream",
    "AttributeMapping",
    "SourceRegistry",
    "PhysicalSourceResolver",
    "ColumnResolver",
    "DependencyResolver",
]
