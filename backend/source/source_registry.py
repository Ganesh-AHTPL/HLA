"""
Source Registry.
Maintains canonical mappings from Logical Source Streams to Physical PostgreSQL Schemas/Tables.
"""

from typing import Dict, Optional, List
from backend.source.source_metadata import LogicalSourceStream


class SourceRegistry:
    """
    Registry for resolving logical stream names to physical database objects.
    Default configurations can be overridden by HLA metadata or dynamic configuration.
    """

    DEFAULT_STREAM_MAPPINGS = {
        "vutm/doos": ("reports", "dl_vdom_firewall_audit_report", "VUTM/VDOM"),
        "vutm": ("reports", "dl_vdom_firewall_audit_report", "VUTM/VDOM"),
        "vdom": ("reports", "dl_vdom_firewall_audit_report", "VUTM/VDOM"),
        "cmdb": ("cmdb", "dl_itsm_cmdb_daily_dump", "ITSM CMDB"),
        "ddos": ("pearl", "dl_pearl_active_profiles", "DDOS / Pearl"),
        "pearl": ("pearl", "dl_pearl_active_profiles", "DDOS / Pearl"),
        "circuit reco": ("ra", "stg_rk_ckt_recon_final", "Circuit Reconciliation"),
        "circuit_reco": ("ra", "stg_rk_ckt_recon_final", "Circuit Reconciliation"),
        "sfdc": ("sfdc", "copf_id", "SFDC COPF"),
        "billing": ("qlik_report", "dl_ra_order_report_daily", "Billing / Qlik Report"),
        "billing order report": ("qlik_report", "dl_ra_order_report_daily", "Billing / Qlik Report"),
    }

    def __init__(self, custom_mappings: Optional[Dict[str, tuple]] = None):
        self._mappings: Dict[str, LogicalSourceStream] = {}
        # Load defaults
        for stream_key, (schema, table, system) in self.DEFAULT_STREAM_MAPPINGS.items():
            self.register_stream(stream_key, schema, table, system)

        # Load overrides
        if custom_mappings:
            for stream_key, (schema, table, system) in custom_mappings.items():
                self.register_stream(stream_key, schema, table, system)

    def register_stream(self, stream_name: str, schema_name: str, table_name: str, source_system: str = "", description: str = ""):
        key = stream_name.strip().lower()
        self._mappings[key] = LogicalSourceStream(
            stream_name=stream_name,
            source_system=source_system or stream_name,
            physical_schema=schema_name.strip().lower(),
            physical_table=table_name.strip().lower(),
            description=description
        )

    def get_stream(self, stream_name: str) -> Optional[LogicalSourceStream]:
        key = stream_name.strip().lower()
        return self._mappings.get(key)

    def list_streams(self) -> List[LogicalSourceStream]:
        return list(self._mappings.values())
