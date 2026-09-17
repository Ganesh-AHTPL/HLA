"""
Stage Manager.
Executes individual pipeline stages against PostgreSQL with execution tracking and error isolation.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import time
from sqlalchemy import text
from sqlalchemy.engine import Engine
from backend.core.control_context import ControlContext
from backend.core.execution_context import ExecutionContext
from backend.core.exceptions import ExecutionFailedError


class StageManager:
    """
    Executes stages sequentially within an execution context.
    """

    def __init__(self, engine: Engine):
        self.engine = engine

    def execute_stage_sql(
        self,
        exec_context: ExecutionContext,
        stage_name: str,
        entity_name: str,
        sql_statement: str,
        params: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Executes a stage SQL statement with parameterized control context.
        """
        ctx = exec_context.control_context
        exec_params = {
            "control_id": ctx.control_id,
            "exec_seq": ctx.exec_seq,
            "execution_date": ctx.execution_date,
            "execution_schedule": ctx.execution_schedule,
            "processing_date": ctx.processing_date
        }
        if params:
            exec_params.update(params)

        start_t = time.time()
        try:
            with self.engine.begin() as conn:
                res = conn.execute(text(sql_statement), exec_params)
                rows_affected = res.rowcount if hasattr(res, 'rowcount') and res.rowcount is not None and res.rowcount >= 0 else 0

            dur = time.time() - start_t
            exec_context.log_stage_completion(stage_name, entity_name, rows_affected, dur)
            return rows_affected
        except Exception as e:
            dur = time.time() - start_t
            err = {
                "stage": stage_name,
                "entity": entity_name,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            exec_context.mark_failed(err)
            raise ExecutionFailedError(
                f"Execution failed at {stage_name} ({entity_name}): {str(e)}",
                control_id=ctx.control_id,
                stage=stage_name,
                entity=entity_name
            )
