"""
Workspace Context Manager for HLA Studio.
Builds sanitized summaries of active workspace projects, documents, schedules, and connections.
"""

from typing import Dict, Any, List, Optional
from models import Project, Document, DBConnection, ControlSchedule, db
from backend.ai.nlu.context_resolver import ContextResolver


class WorkspaceContext:
    """
    Assembles high-level project and workspace context for AI requests.
    """

    @staticmethod
    def get_project_summary(project_id: int) -> Dict[str, Any]:
        proj = db.session.get(Project, project_id)
        if not proj:
            return {}

        docs = Document.query.filter_by(project_id=project_id).all()
        conns = DBConnection.query.filter_by(project_id=project_id).all()
        schedules = ControlSchedule.query.filter_by(project_id=project_id).all()

        controls_list = []
        for d in docs:
            c_num = ""
            c_name = d.original_name
            if d.analysis_data:
                ctrl_ov = d.analysis_data.get("control_overview") or d.analysis_data.get("overview") or {}
                ident = ctrl_ov.get("identification") or ctrl_ov if isinstance(ctrl_ov, dict) else {}
                c_num = ident.get("control_number") or ident.get("id") or ""
                c_name = ident.get("control_name") or d.original_name
            controls_list.append({
                "document_id": d.id,
                "control_number": c_num,
                "control_name": c_name,
                "status": d.status
            })

        return {
            "project_id": proj.id,
            "project_name": proj.name,
            "description": proj.description or "",
            "control_count": len(controls_list),
            "controls": controls_list,
            "connection_count": len(conns),
            "schedule_count": len(schedules)
        }
