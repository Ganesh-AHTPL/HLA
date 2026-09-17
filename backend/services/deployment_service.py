"""
Deployment and Execution Services.
Orchestrates deployment and multi-stage pipeline executions.
"""

from typing import Dict, Any, Optional
from sqlalchemy.engine import Engine
from backend.core.control_context import ControlContext
from backend.core.execution_context import ExecutionContext
from backend.hla.hla_model import HLAControl
from backend.deployment.deployment_engine import DeploymentEngine
from backend.pipeline.stage_manager import StageManager
from backend.pipeline.pipeline_planner import PipelinePlanner


class DeploymentService:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.deployment_engine = DeploymentEngine(engine)

    def preview(self, hla: HLAControl, context: ControlContext) -> Dict[str, Any]:
        return self.deployment_engine.preview_deployment(hla, context)

    def deploy(self, hla: HLAControl, context: ControlContext, dry_run: bool = False) -> Dict[str, Any]:
        res = self.deployment_engine.execute_deployment(hla, context, dry_run=dry_run)
        return res.to_dict()


class ExecutionService:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.planner = PipelinePlanner(engine)
        self.stage_manager = StageManager(engine)

    def execute_pipeline(self, hla: HLAControl, context: ControlContext, execution_id: str) -> Dict[str, Any]:
        exec_ctx = ExecutionContext(control_context=context, execution_id=execution_id)
        plan = self.planner.plan_pipeline(hla, context)

        # Execute stage SQLs
        for sql_item in plan["transformation_sql"]:
            self.stage_manager.execute_stage_sql(
                exec_context=exec_ctx,
                stage_name=sql_item["stage"],
                entity_name=sql_item["target_table"],
                sql_statement=sql_item["sql"]
            )

        exec_ctx.mark_completed()
        return {
            "success": exec_ctx.status == "COMPLETED",
            "control_id": context.control_id,
            "execution_id": execution_id,
            "stages_executed": exec_ctx.stage_results,
            "record_counts": exec_ctx.record_counts
        }
