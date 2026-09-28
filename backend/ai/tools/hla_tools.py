"""
HLA Tools for HLA Studio AI Architecture.
Provides generic tools to inspect sources, rules, target schemas, and architecture principles.
"""

from typing import Dict, Any, List, Optional
from models import Document, Project, db
from backend.ai.nlu.context_resolver import ContextResolver


class HLAToolRegistry:
    """
    Central HLA Tool Registry providing deterministic domain operations on loaded document metadata.
    """

    @staticmethod
    def get_source_tables(
        control_number: Optional[str] = None,
        document_id: Optional[int] = None,
        project_id: Optional[int] = None
    ) -> Dict[str, Any]:
        _, context = ContextResolver.resolve_control_context(
            control_ref=control_number,
            project_id=project_id,
            document_id=document_id
        )
        sources = context.get("sources", [])
        return {
            "control_number": control_number,
            "document_id": context.get("document_id"),
            "document_name": context.get("document_name"),
            "count": len(sources),
            "sources": sources
        }

    @staticmethod
    def get_reconciliation_logic(
        control_number: Optional[str] = None,
        rule_id: Optional[str] = None,
        document_id: Optional[int] = None,
        project_id: Optional[int] = None
    ) -> Dict[str, Any]:
        _, context = ContextResolver.resolve_control_context(
            control_ref=control_number,
            project_id=project_id,
            document_id=document_id
        )
        rules = context.get("rules", [])
        matched_rules = [
            r for r in rules
            if not rule_id or rule_id.upper() in str(r.get("id", "")).upper() or rule_id.upper() in str(r.get("name", "")).upper()
        ]
        return {
            "control_number": control_number,
            "rule_filter": rule_id,
            "rules": matched_rules,
            "total_rules": len(rules)
        }

    @staticmethod
    def get_control_details(
        control_number: Optional[str] = None,
        document_id: Optional[int] = None,
        project_id: Optional[int] = None
    ) -> Dict[str, Any]:
        doc, context = ContextResolver.resolve_control_context(
            control_ref=control_number,
            project_id=project_id,
            document_id=document_id
        )
        if not doc:
            return {"found": False, "message": "Document / control not found."}

        return {
            "found": True,
            "document_id": doc.id,
            "document_name": doc.original_name,
            "profile": context.get("profile", {}),
            "source_count": len(context.get("sources", [])),
            "rule_count": len(context.get("rules", [])),
            "recent_runs": context.get("recent_runs", [])
        }

    @staticmethod
    def explain_generic_target_principles() -> Dict[str, Any]:
        return {
            "principle": "Do NOT copy source tables directly to target tables.",
            "rules": [
                "1. Target tables must be domain-generic and consolidated rather than mirroring raw source silos.",
                "2. Standard enterprise audit columns must be added (_created_at, _updated_at, _source_system, _batch_id, _recon_status).",
                "3. Heterogeneous source schemas must be mapped through validation/filtering rules and canonical normalization.",
                "4. Balancing rules must execute against normalized target records to calculate variance."
            ]
        }
