"""
Execution Tools for HLA Studio AI Architecture.
Fetches run histories and failure diagnostics generically.
"""

from typing import Dict, Any, List, Optional
from models import ControlRunHistory, Document, db
from backend.ai.nlu.context_resolver import ContextResolver


class ExecutionTools:
    """
    Tools to inspect control execution runs and failure logs.
    """

    @staticmethod
    def get_run_history(
        control_number: Optional[str] = None,
        document_id: Optional[int] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        query = ControlRunHistory.query
        if document_id:
            query = query.filter_by(document_id=document_id)
        elif control_number:
            query = query.filter(ControlRunHistory.control_number.ilike(f"%{control_number}%"))
        
        runs = query.order_by(ControlRunHistory.started_at.desc()).limit(limit).all()
        return [ContextResolver.sanitize_payload(r.to_dict()) for r in runs]

    @staticmethod
    def diagnose_failure(
        control_number: Optional[str] = None,
        run_id: Optional[int] = None
    ) -> Dict[str, Any]:
        if run_id:
            run = db.session.get(ControlRunHistory, run_id)
        elif control_number:
            run = ControlRunHistory.query.filter(
                ControlRunHistory.control_number.ilike(f"%{control_number}%")
            ).order_by(ControlRunHistory.started_at.desc()).first()
        else:
            run = ControlRunHistory.query.filter_by(status="FAILED").order_by(ControlRunHistory.started_at.desc()).first()

        if not run:
            return {
                "found": False,
                "message": "No failed execution runs found in database records."
            }

        data = ContextResolver.sanitize_payload(run.to_dict())
        log_text = data.get("execution_log", "")
        
        causes = []
        if "relation" in log_text.lower() and "does not exist" in log_text.lower():
            causes.append("Missing source table or schema mismatch in database.")
        if "connection" in log_text.lower() and ("refused" in log_text.lower() or "timeout" in log_text.lower()):
            causes.append("Database connectivity error or network timeout.")
        if data.get("tables_missing_count", 0) > 0:
            causes.append(f"{data.get('tables_missing_count')} expected source tables were missing during run.")

        return {
            "found": True,
            "run_id": run.id,
            "status": run.status,
            "environment": run.environment,
            "duration_seconds": run.duration_seconds,
            "summary_message": run.summary_message,
            "probable_causes": causes or ["Detailed in execution log tail"],
            "log_tail": log_text[-600:].strip() if log_text else ""
        }
