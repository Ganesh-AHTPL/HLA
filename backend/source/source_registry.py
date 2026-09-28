"""
Source Registry.
Maintains mappings from Logical Source Streams to Physical Database Schemas/Tables.
100% Document-Driven and Generic — Zero Hardcoded Sources.
"""

from typing import Dict, Optional, List, Any
from backend.source.source_metadata import LogicalSourceStream


class SourceRegistry:
    """
    Registry for resolving logical stream names to physical database objects.
    All stream mappings are populated dynamically from uploaded HLA document metadata.
    """

    def __init__(self, custom_mappings: Optional[Dict[str, tuple]] = None, sources_list: Optional[List[Dict[str, Any]]] = None):
        self._mappings: Dict[str, LogicalSourceStream] = {}

        # Register from parsed document sources if provided
        if sources_list:
            self.register_sources_from_analysis(sources_list)

        # Register custom overrides if provided
        if custom_mappings:
            for stream_key, mapping_val in custom_mappings.items():
                if len(mapping_val) == 3:
                    schema, table, system = mapping_val
                    src_id = ""
                elif len(mapping_val) >= 4:
                    schema, table, system, src_id = mapping_val[:4]
                else:
                    schema, table = mapping_val[:2]
                    system = stream_key
                    src_id = ""
                self.register_stream(stream_key, schema, table, system, source_id=src_id)

    def register_stream(
        self,
        stream_name: str = "",
        schema_name: str = "",
        table_name: str = "",
        source_system: str = "",
        description: str = "",
        source_id: str = "",
        logical_name: str = "",
        physical_schema: str = "",
        physical_table: str = ""
    ):
        st_name = stream_name or logical_name
        sch_name = schema_name or physical_schema
        tbl_name = table_name or physical_table

        clean_schema = sch_name.strip().lower() if sch_name else "public"
        clean_table = tbl_name.strip().lower() if tbl_name else ""

        # Strip accidental duplicate schema prefix from table name
        if clean_schema and clean_table.startswith(clean_schema + "."):
            clean_table = clean_table[len(clean_schema)+1:].strip()

        key = st_name.strip().lower()
        stream_obj = LogicalSourceStream(
            stream_name=st_name.strip(),
            source_system=source_system or st_name,
            physical_schema=clean_schema,
            physical_table=clean_table,
            source_id=source_id,
            description=description
        )
        self._mappings[key] = stream_obj

        # Also register by table name, full qualified name, and source_id for flexible lookup
        if clean_table and clean_table != key:
            self._mappings[clean_table] = stream_obj
        if clean_schema and clean_table:
            full_key = f"{clean_schema}.{clean_table}"
            if full_key != key:
                self._mappings[full_key] = stream_obj
        if source_id:
            self._mappings[source_id.strip().lower()] = stream_obj

    def register_sources_from_analysis(self, sources_list: Any):
        items = sources_list
        if isinstance(sources_list, dict):
            items = sources_list.get("sources") or sources_list.get("source_systems") or []

        if not isinstance(items, list):
            return

        for s in items:
            if not isinstance(s, dict):
                continue
            src_id = s.get("source_id") or ""
            sys_name = s.get("source_name") or s.get("source_system") or s.get("database") or "Default"
            schema = s.get("schema") or s.get("schema_name") or s.get("source_schema") or "public"
            table = s.get("table") or s.get("table_name") or s.get("source_table") or s.get("source_table_name") or ""
            raw_t = s.get("full_table_name") or table

            if "." in raw_t:
                parts = raw_t.split(".", 1)
                if not schema or schema == "public":
                    schema = parts[0]
                table = parts[1]

            if schema and table.startswith(schema + "."):
                table = table[len(schema)+1:]

            st_name = s.get("stream_name") or raw_t or table
            self.register_stream(
                stream_name=st_name,
                schema_name=schema,
                table_name=table,
                source_system=sys_name,
                source_id=src_id
            )

    def get_stream(self, stream_name: str) -> Optional[LogicalSourceStream]:
        key = stream_name.strip().lower()
        return self._mappings.get(key)

    def list_streams(self) -> List[LogicalSourceStream]:
        # Return unique stream objects
        seen = set()
        res = []
        for s in self._mappings.values():
            sig = (s.source_system, s.physical_schema, s.physical_table)
            if sig not in seen:
                seen.add(sig)
                res.append(s)
        return res
