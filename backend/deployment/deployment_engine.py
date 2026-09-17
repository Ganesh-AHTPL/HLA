"""
Deployment Engine and Orchestrator.
Executes the 12-Phase deployment quality gate workflow (RULE 10, RULE 25, RULE 40).
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.engine import Engine
from backend.core.control_context import ControlContext
from backend.core.result import DeploymentResult, ValidationResult
from backend.core.exceptions import DeploymentFailedError
from backend.hla.hla_parser import HLAParser
from backend.hla.hla_model import HLAControl
from backend.pipeline.pipeline_planner import PipelinePlanner
from backend.schema.migration_engine import MigrationEngine
from backend.schema.schema_validator import SchemaValidator


class DeploymentEngine:
    """
    Orchestrates the deterministic 12-phase deployment quality gate.
    """

    def __init__(self, engine: Engine):
        self.engine = engine
        self.planner = PipelinePlanner(engine)
        self.migration_engine = MigrationEngine(engine)

    def preview_deployment(self, hla: HLAControl, context: ControlContext) -> Dict[str, Any]:
        """
        Phases 1-11: Parses, resolves, plans, generates, and validates without executing.
        """
        # Validate target schema
        schema_val = SchemaValidator.validate_target_schema_name(context.target_schema)
        if not schema_val.is_valid:
            return {
                "success": False,
                "can_deploy": False,
                "control_id": context.control_id,
                "errors": schema_val.errors,
                "phase": "PHASE_2_CONTROL_RESOLUTION"
            }

        # Plan pipeline (handles Phases 3-10)
        plan = self.planner.plan_pipeline(hla, context)
        dep_val = plan["dependency_validation"]

        # Inspect table migration status for each planned table
        entity_statuses = []
        for ddl_info in plan["ddl_statements"]:
            tbl_name = ddl_info["table_name"]
            mig_plan = self.migration_engine.plan_table_migration(
                schema_name=context.target_schema,
                table_name=tbl_name,
                target_business_columns=ddl_info["business_columns"]
            )
            entity_statuses.append({
                "entity": ddl_info["entity"],
                "table_name": tbl_name,
                "action": mig_plan["action"],
                "migration_needed": mig_plan["migration_needed"],
                "row_count": mig_plan["row_count"]
            })

        return {
            "success": dep_val["is_valid"],
            "can_deploy": dep_val["is_valid"],
            "control_id": context.control_id,
            "control_name": context.control_name,
            "hla_version": hla.hla_version,
            "dependency_validation": dep_val,
            "entities": entity_statuses,
            "ddl_statements_count": len(plan["ddl_statements"]),
            "sql_statements_count": len(plan["transformation_sql"]),
            "plan": plan
        }

    def execute_deployment(self, hla: HLAControl, context: ControlContext, dry_run: bool = False) -> DeploymentResult:
        """
        Phases 1-12: Full execution of DDL and schema creation with idempotency (RULE 40).
        """
        start_t = datetime.now(timezone.utc)
        result = DeploymentResult(
            success=False,
            control_id=context.control_id,
            deployment_id=f"DEP_{context.control_id}_{int(start_t.timestamp())}",
            start_time=start_t
        )

        preview = self.preview_deployment(hla, context)
        if not preview["can_deploy"]:
            result.errors = [{"phase": "PRE_FLIGHT_VALIDATION", "errors": preview.get("errors") or preview["dependency_validation"].get("errors")}]
            result.end_time = datetime.now(timezone.utc)
            return result

        if dry_run:
            result.success = True
            result.warnings.append("Dry run executed successfully. No changes made.")
            result.end_time = datetime.now(timezone.utc)
            return result

        # Execute safe table creations and migrations
        plan = preview["plan"]
        try:
            for ddl_info in plan["ddl_statements"]:
                tbl_name = ddl_info["table_name"]
                mig_res = self.migration_engine.execute_migration(
                    schema_name=context.target_schema,
                    table_name=tbl_name,
                    target_business_columns=ddl_info["business_columns"],
                    dry_run=False
                )
                if mig_res["action"] == "CREATE":
                    result.created_entities.append(tbl_name)
                elif mig_res["action"] == "REBUILD":
                    result.migrated_entities.append(tbl_name)
                result.executed_statements.append(f"{mig_res['action']} -> {tbl_name}")

            result.success = True
        except Exception as e:
            result.success = False
            result.errors.append({"error": str(e)})
            raise DeploymentFailedError(
                f"Deployment execution failed for control {context.control_id}: {str(e)}",
                control_id=context.control_id
            )
        finally:
            result.end_time = datetime.now(timezone.utc)

        return result
