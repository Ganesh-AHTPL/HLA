"""
Pipeline Planner.
Orchestrates the 8 canonical stages of ETL and Reconciliation for an active HLA Control.
"""

from typing import List, Dict, Any, Tuple
from sqlalchemy.engine import Engine
from backend.core.control_context import ControlContext
from backend.hla.hla_model import HLAControl
from backend.source.dependency_resolver import DependencyResolver
from backend.source.source_metadata import AttributeMapping
from backend.sql.sql_generator import SQLGenerator
from backend.schema.ddl_generator import DDLGenerator
from backend.schema.schema_validator import SchemaValidator
from backend.schema.column_order_validator import ColumnOrderValidator
from backend.core.exceptions import (
    SourceDependencyMissingError,
    SourceColumnDependencyMissingError,
    SQLValidationFailedError
)


class PipelinePlanner:
    """
    Constructs the end-to-end staged execution and DDL plan for an HLA Control.
    """

    def __init__(self, engine: Engine):
        self.engine = engine
        self.dep_resolver = DependencyResolver(engine)

    def plan_pipeline(self, hla: HLAControl, context: ControlContext) -> Dict[str, Any]:
        """
        Builds the complete deployment and execution plan across all 8 stages.
        """
        # 1. Convert HLA attributes to AttributeMappings
        attribute_mappings: List[AttributeMapping] = []
        for attr in hla.attributes:
            attribute_mappings.append(AttributeMapping(
                logical_attribute_name=attr.attribute_name,
                logical_source_stream=attr.source_stream,
                target_field_name=attr.target_field_name,
                target_data_type=attr.data_type,
                is_derived=attr.is_derived,
                derivation_rule=attr.derivation_rule,
                hla_sheet_reference=attr.sheet_reference,
                hla_row_reference=attr.row_reference
            ))

        # 2. Validate dependencies
        dep_val = self.dep_resolver.validate_dependencies(
            context=context,
            required_streams=hla.get_source_stream_names(),
            attribute_mappings=attribute_mappings
        )

        # 3. Generate DDL for each required stage entity
        ddl_statements: List[Dict[str, Any]] = []
        for ent_name, ent_def in hla.entities.items():
            tbl_name = context.format_table_name(ent_def.table_pattern, ent_name)
            
            # Default business columns for the entity if not custom
            biz_cols: List[Tuple[str, str]] = []
            if ent_def.stage == "STAGE_1_ACQUISITION":
                stream = ent_def.source_streams[0] if ent_def.source_streams else "DEFAULT"
                stream_attrs = [a for a in attribute_mappings if a.logical_source_stream.lower() == stream.lower() and not a.is_derived]
                biz_cols = [(a.target_field_name, a.target_data_type) for a in stream_attrs]
                if not biz_cols:
                    biz_cols = [("raw_payload", "JSONB"), ("source_record_id", "VARCHAR(100)")]
            elif ent_def.stage in ("STAGE_2_FILTERING", "STAGE_3_BALANCE"):
                stream = ent_def.source_streams[0] if ent_def.source_streams else "DEFAULT"
                stream_attrs = [a for a in attribute_mappings if a.logical_source_stream.lower() == stream.lower()]
                biz_cols = [(a.target_field_name, a.target_data_type) for a in stream_attrs]
                if not biz_cols:
                    biz_cols = [("status", "VARCHAR(50)")]
            elif ent_def.stage == "STAGE_4_RECONCILIATION":
                biz_cols = [("key_value", "TEXT"), ("balance_type", "VARCHAR(10)"), ("source_name", "VARCHAR(100)")]
            elif ent_def.stage == "STAGE_5_KRI_NON_KRI":
                biz_cols = [("key_value", "TEXT"), ("balance_type", "VARCHAR(10)"), ("source_name", "VARCHAR(100)"), ("kri_status", "VARCHAR(50)")]
            elif ent_def.stage in ("STAGE_6_CURRENT_RUN_WORK_ITEM", "STAGE_7_HISTORICAL_WORK_ITEM"):
                biz_cols = [("key_value", "TEXT"), ("balance_type", "VARCHAR(10)"), ("source_name", "VARCHAR(100)"), ("kri_status", "VARCHAR(50)"), ("item_status", "VARCHAR(50)")]
            elif ent_def.stage == "STAGE_8_REPORTING":
                biz_cols = [("balance_type", "VARCHAR(10)"), ("record_count", "INTEGER")]

            ddl = DDLGenerator.generate_create_table_ddl(context.target_schema, tbl_name, biz_cols)
            ddl_statements.append({
                "entity": ent_name,
                "table_name": tbl_name,
                "stage": ent_def.stage,
                "ddl": ddl,
                "business_columns": biz_cols
            })

        # 4. Generate stage transformation SQL
        sql_statements: List[Dict[str, Any]] = []

        # Stage 1 SQL
        for stream_name in hla.get_source_stream_names():
            if stream_name.lower() in ("derived", "formula", "calculated", "system"):
                continue
            stream_obj = self.dep_resolver.source_resolver.registry.get_stream(stream_name)
            if stream_obj:
                cols = [a.target_field_name for a in attribute_mappings if a.logical_source_stream.lower() == stream_name.lower() and not a.is_derived]
                if not cols:
                    cols = ["status"]
                tbl, sql = SQLGenerator.generate_stage1_acquisition_sql(
                    context=context,
                    stream_name=stream_name,
                    source_schema=stream_obj.physical_schema,
                    source_table=stream_obj.physical_table,
                    source_columns=cols
                )
                sql_statements.append({"stage": "STAGE_1_ACQUISITION", "target_table": tbl, "sql": sql})

        # Stage 4 SQL
        streams = [s for s in hla.get_source_stream_names() if s.lower() not in ("derived", "formula", "calculated", "system")]
        prim = streams[0] if streams else "STREAM_A"
        sec = streams[1] if len(streams) > 1 else (streams[0] if streams else "STREAM_B")
        tbl4, sql4 = SQLGenerator.generate_stage4_reconciliation_sql(
            context=context,
            primary_stream=prim,
            secondary_stream=sec,
            recon_keys=["status"],
            primary_columns=[],
            secondary_columns=[]
        )
        sql_statements.append({"stage": "STAGE_4_RECONCILIATION", "target_table": tbl4, "sql": sql4})

        # Stage 5 SQL
        tbl5, sql5 = SQLGenerator.generate_stage5_kri_sql(context)
        sql_statements.append({"stage": "STAGE_5_KRI_NON_KRI", "target_table": tbl5, "sql": sql5})

        # Stage 6 SQL
        tbl6, sql6 = SQLGenerator.generate_stage6_work_item_current_run_sql(context)
        sql_statements.append({"stage": "STAGE_6_CURRENT_RUN_WORK_ITEM", "target_table": tbl6, "sql": sql6})

        # Stage 7 SQL
        tbl7, sql7 = SQLGenerator.generate_stage7_historical_work_item_sql(context)
        sql_statements.append({"stage": "STAGE_7_HISTORICAL_WORK_ITEM", "target_table": tbl7, "sql": sql7})

        # Stage 8 SQL
        tbl8, sql8 = SQLGenerator.generate_stage8_report_summary_sql(context)
        sql_statements.append({"stage": "STAGE_8_REPORTING", "target_table": tbl8, "sql": sql8})

        return {
            "control_id": context.control_id,
            "control_name": context.control_name,
            "dependency_validation": dep_val.to_dict(),
            "ddl_statements": ddl_statements,
            "transformation_sql": sql_statements,
            "can_deploy": dep_val.is_valid
        }
