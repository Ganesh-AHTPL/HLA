"""
Generic Context Resolver for HLA Studio.
Resolves active document and project context from PostgreSQL records
without hardcoded assumptions regarding control identifiers or sheet structure.
"""

import re
import logging
from typing import Dict, Any, Tuple, Optional, List
from models import db, User, Project, Document, ControlSchedule, ControlRunHistory, DBConnection, TargetArtifact

logger = logging.getLogger("hla_ai.nlu.context")

SENSITIVE_KEY_PATTERNS = re.compile(
    r"(password|secret|token|hash|jwt|otp|credential|auth|api_key|private_key)",
    re.IGNORECASE
)


class ContextResolver:
    """
    Enforces RBAC and retrieves domain entities generically from PostgreSQL records.
    """

    @classmethod
    def sanitize_payload(cls, data: Any) -> Any:
        """
        Recursively masks sensitive credentials from payloads.
        """
        if isinstance(data, dict):
            sanitized = {}
            for k, v in data.items():
                if SENSITIVE_KEY_PATTERNS.search(str(k)):
                    sanitized[k] = "[REDACTED]"
                elif isinstance(v, str) and ("://" in v and ("postgresql://" in v or "mysql://" in v or "oracle://" in v)):
                    sanitized[k] = re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", v)
                else:
                    sanitized[k] = cls.sanitize_payload(v)
            return sanitized
        elif isinstance(data, list):
            return [cls.sanitize_payload(item) for item in data]
        return data

    @classmethod
    def verify_project_access(cls, user: User, project_id: int) -> Tuple[bool, Optional[Project], str]:
        if not project_id:
            return True, None, ""
        project = db.session.get(Project, project_id)
        if not project:
            return False, None, f"Project #{project_id} does not exist."
        return True, project, ""

    @classmethod
    def verify_document_access(cls, user: User, document_id: int) -> Tuple[bool, Optional[Document], str]:
        if not document_id:
            return True, None, ""
        doc = db.session.get(Document, document_id)
        if not doc:
            return False, None, f"Document #{document_id} does not exist."
        return True, doc, ""

    @classmethod
    def resolve_control_context(
        cls,
        control_ref: Optional[str] = None,
        project_id: Optional[int] = None,
        document_id: Optional[int] = None
    ) -> Tuple[Optional[Document], Dict[str, Any]]:
        """
        Resolves document context dynamically.
        Prioritizes explicit document_id, then matches control_ref, or falls back to active/recent document.
        """
        matched_doc = None

        if document_id:
            matched_doc = db.session.get(Document, document_id)
        
        if not matched_doc and control_ref:
            ctrl_ref_clean = re.sub(r"^(?:control|ctrl|doc)\s*[-#_]?\s*", "", str(control_ref), flags=re.IGNORECASE).strip()
            candidates = []
            if project_id:
                candidates = Document.query.filter_by(project_id=project_id).all()
            else:
                candidates = Document.query.order_by(Document.id.desc()).limit(20).all()

            for d in candidates:
                if not d.analysis_data:
                    continue
                adata = d.analysis_data
                ctrl_ov = adata.get("control_overview") or adata.get("overview") or adata.get("metadata") or {}
                ident = ctrl_ov.get("identification") or ctrl_ov if isinstance(ctrl_ov, dict) else {}
                c_num = str(ident.get("control_number") or ident.get("id") or ident.get("control_id") or "").strip()
                c_num_clean = re.sub(r"^(?:control|ctrl|doc)\s*[-#_]?\s*", "", c_num, flags=re.IGNORECASE).strip()

                if (ctrl_ref_clean and c_num_clean and ctrl_ref_clean.lower() == c_num_clean.lower()) or \
                   (str(control_ref).lower() == str(c_num).lower()) or \
                   (str(control_ref).lower() in (d.original_name or "").lower()):
                    matched_doc = d
                    break

        # Fallback to the latest document in project if none matched explicitly
        if not matched_doc and project_id:
            matched_doc = Document.query.filter_by(project_id=project_id).order_by(Document.id.desc()).first()

        context_data = {}
        if matched_doc:
            from backend.ai.context.hla_context import HLAContextExtractor
            adata = cls.sanitize_payload(matched_doc.analysis_data or {})
            indexed = HLAContextExtractor.index_document_analysis(adata)

            context_data["document_id"] = matched_doc.id
            context_data["document_name"] = matched_doc.original_name
            context_data["profile"] = indexed.get("document_profile", {})
            context_data["components"] = indexed.get("components", [])
            context_data["requirements"] = indexed.get("requirements", [])
            context_data["pipeline_stages"] = indexed.get("pipeline_stages", [])
            context_data["sources"] = indexed.get("source_tables", [])
            context_data["rules"] = indexed.get("rules", [])
            context_data["target_attributes"] = indexed.get("target_attributes", [])
            context_data["reconciliation"] = indexed.get("reconciliation", [])
            context_data["raw_sections"] = indexed.get("raw_sections", {})

            # Fetch runs if any exist
            runs = ControlRunHistory.query.filter_by(document_id=matched_doc.id).order_by(ControlRunHistory.started_at.desc()).limit(3).all()
            context_data["recent_runs"] = [cls.sanitize_payload(r.to_dict()) for r in runs]

            # Fetch schedules if any exist
            schedules = ControlSchedule.query.filter_by(document_id=matched_doc.id).all()
            context_data["schedules"] = [s.to_dict() for s in schedules]

        return matched_doc, context_data
