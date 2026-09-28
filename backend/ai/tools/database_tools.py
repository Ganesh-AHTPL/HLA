"""
Database Tools for HLA Studio AI Architecture.
Safe, read-only database schema inspection and connection status.
"""

from typing import Dict, Any, List, Optional
from models import DBConnection, Project, db
from backend.ai.nlu.context_resolver import ContextResolver


class DatabaseTools:
    """
    Tools for inspecting database connections and table schemas safely.
    """

    @staticmethod
    def list_connections(project_id: Optional[int] = None) -> List[Dict[str, Any]]:
        query = DBConnection.query
        if project_id:
            query = query.filter_by(project_id=project_id)
        conns = query.all()
        return [ContextResolver.sanitize_payload(c.to_dict()) for c in conns]

    @staticmethod
    def verify_document_table_against_database(
        table_name: str,
        project_id: Optional[int] = None,
        connection_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Verifies if an object defined in the HLA document exists in the connected database.
        Never fabricates placeholder tables.
        """
        from db_fetcher import find_table_across_databases, fetch_table_metadata

        if not table_name:
            return {
                "verified": False,
                "status": "No table specified",
                "message": "No table identifier provided for database verification."
            }

        found, db_name, schema_name = find_table_across_databases(table_name, project_id=project_id)
        if found:
            return {
                "table_name": table_name,
                "verified": True,
                "database": db_name,
                "schema": schema_name,
                "status": "VERIFIED",
                "message": f"Object '{table_name}' verified in database '{db_name}.{schema_name}'."
            }
        else:
            return {
                "table_name": table_name,
                "verified": False,
                "status": "NOT_FOUND",
                "message": "Defined in HLA document but not found in connected database."
            }
