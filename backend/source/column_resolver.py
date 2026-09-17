"""
Physical Column Resolver.
Resolves HLA attributes to verified physical columns in PostgreSQL (RULE 4, RULE 8, RULE 42).
Never guesses column names; strictly relies on verified introspection and mapping definitions.
"""

from typing import Dict, Optional, Any, List
from sqlalchemy.engine import Engine
from backend.source.source_metadata import AttributeMapping, LogicalSourceStream
from backend.source.physical_source_resolver import PhysicalSourceResolver
from backend.schema.postgres_introspector import PostgresSchemaIntrospector
from backend.core.exceptions import (
    SourceColumnDependencyMissingError,
    HLAMappingMissingError,
    DerivationDependencyMissingError
)


class ColumnResolver:
    """
    Deterministic column resolver validating each attribute mapping against real PostgreSQL tables.
    """

    # Canonical dictionary of known logical-to-physical column resolutions per stream
    # Sourced from authoritative HLA metadata and validated against schema
    CANONICAL_FIELD_MAPPINGS: Dict[str, Dict[str, str]] = {
        "vutm/doos": {
            "application_name": "vdom",
            "host_name": "hostname",
            "ip": "ip",
            "ckt_id": "ckt_id",
            "service_type": "service_type",
            "vdom": "vdom",
            "hostname": "hostname",
            "status": "status"
        },
        "cmdb": {
            "cmdb_production_ip": "production_ip",
            "cmdb_profile_name": "profile_name",
            "cmdb_copf": "copf",
            "cmdb_ckt_id": "circuit_id",
            "production_ip": "production_ip",
            "profile_name": "profile_name",
            "copf": "copf",
            "circuit_id": "circuit_id",
            "status": "status"
        },
        "ddos": {
            "application_name": "profile_name",
            "host_name": "customer_name",
            "ip": "ip_address",
            "profile_name": "profile_name",
            "customer_name": "customer_name",
            "ip_address": "ip_address"
        },
        "circuit reco": {
            "ckt_circuit_id": "circuit_id",
            "ckt_circuit_status": "circuit_status",
            "ckt_copf": "copf_id",
            "ckt_source_system": "source_system",
            "ckt_product": "product",
            "ckt_additional_remarks": "additional_remarks",
            "ckt_customer_name": "customer_name",
            "ckt_final_remarks": "final_remarks",
            "ckt_recon_remark_provisioning": "recon_remark_provisioning",
            "circuit_id": "circuit_id",
            "circuit_status": "circuit_status",
            "copf_id": "copf_id"
        },
        "sfdc": {
            "sfdc_mrc": "mrc",
            "sfdc_nrc": "nrc",
            "sfdc_copf_created_dt": "copf_created_dt",
            "sfdc_status": "status",
            "mrc": "mrc",
            "nrc": "nrc",
            "copf_created_dt": "copf_created_dt",
            "copf_id": "copf_id",
            "status": "status"
        },
        "billing": {
            "found_in_billing": "billing_status",
            "product_billing": "product",
            "billing_status": "billing_status",
            "product": "product",
            "order_number": "order_number",
            "customer_name": "customer_name"
        }
    }

    def __init__(self, engine: Engine, source_resolver: Optional[PhysicalSourceResolver] = None):
        self.engine = engine
        self.source_resolver = source_resolver or PhysicalSourceResolver(engine)
        self.introspector = PostgresSchemaIntrospector(engine)

    def resolve_mapping(
        self,
        mapping: AttributeMapping,
        control_id: Any = None
    ) -> AttributeMapping:
        """
        Resolves an AttributeMapping against physical PostgreSQL columns.
        Raises SourceColumnDependencyMissingError if the column does not physically exist.
        """
        if mapping.is_derived:
            mapping.resolution_status = "RESOLVED"
            return mapping

        stream_key = mapping.logical_source_stream.strip().lower()

        # If stream is "derived", mark as derived
        if stream_key in ("derived", "formula", "calculated", "system"):
            mapping.is_derived = True
            mapping.resolution_status = "RESOLVED"
            return mapping

        # Resolve physical source stream
        resolved_stream = self.source_resolver.resolve_stream(mapping.logical_source_stream, control_id=control_id)
        phys_table = resolved_stream.resolved_physical_table

        if not phys_table:
            raise HLAMappingMissingError(
                f"Stream '{mapping.logical_source_stream}' could not be resolved to a physical table.",
                control_id=control_id,
                source=mapping.logical_source_stream,
                target=mapping.target_field_name
            )

        # Look up physical column candidate
        target_clean = mapping.target_field_name.strip().lower()
        candidate_col = mapping.physical_column_name

        if not candidate_col:
            # Check canonical mapping table for this stream
            stream_dict = self.CANONICAL_FIELD_MAPPINGS.get(stream_key, {})
            candidate_col = stream_dict.get(target_clean)

        if not candidate_col:
            # Check if target column name directly matches a physical column in the source table
            if target_clean in phys_table.columns:
                candidate_col = target_clean

        if not candidate_col:
            raise SourceColumnDependencyMissingError(
                f"Attribute '{mapping.target_field_name}' from stream '{mapping.logical_source_stream}' could not be resolved to any column on \"{phys_table.schema_name}\".\"{phys_table.table_name}\".",
                control_id=control_id,
                source=f"{phys_table.schema_name}.{phys_table.table_name}",
                target=mapping.target_field_name,
                hla_reference=mapping.hla_sheet_reference
            )

        # Validate that the candidate column ACTUALLY exists in PostgreSQL metadata
        if candidate_col.lower() not in phys_table.columns:
            raise SourceColumnDependencyMissingError(
                f"Physical column '{candidate_col}' does not exist on source table \"{phys_table.schema_name}\".\"{phys_table.table_name}\" for attribute '{mapping.target_field_name}'.",
                control_id=control_id,
                source=f"{phys_table.schema_name}.{phys_table.table_name}",
                column=candidate_col,
                target=mapping.target_field_name,
                hla_reference=mapping.hla_sheet_reference
            )

        mapping.physical_column_name = candidate_col.lower()
        mapping.resolution_status = "RESOLVED"
        return mapping
