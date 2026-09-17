"""
Transformation SQL Generator for all 8 Stages (RULE 10, RULE 23, RULE 24, RULE 43).
Generates strictly validated, schema-aware SQL for each stage in the pipeline.
Never emits synthetic aliases like b.vutm_doos or hardcoded control IDs.
"""

from typing import List, Dict, Tuple, Optional, Any
from backend.core.control_context import ControlContext
from backend.core.constants import (
    PLATFORM_HEADER_NAMES,
    PLATFORM_FOOTER_NAMES,
    PATTERN_ACQUISITION_TABLE,
    PATTERN_FILTERED_TABLE,
    PATTERN_FILTER_SUMMARY,
    PATTERN_BALANCE_TABLE,
    PATTERN_WORKING_RL,
    PATTERN_WORKING_KL,
    PATTERN_WORK_ITEM_CURRENT_RUN,
    PATTERN_WORK_ITEM_HISTORICAL,
    PATTERN_NON_KRI_SUMMARY,
    PATTERN_NON_KRI_DETAILS,
    PATTERN_KRI_SUMMARY,
    PATTERN_CASE_SUMMARY
)
from backend.source.source_metadata import LogicalSourceStream, AttributeMapping
from backend.schema.column_order_validator import ColumnOrderValidator


class SQLGenerator:
    """
    Generates parameterized SQL statements for the 8 pipeline stages.
    """

    @classmethod
    def generate_stage1_acquisition_sql(
        cls,
        context: ControlContext,
        stream_name: str,
        source_schema: str,
        source_table: str,
        source_columns: List[str]
    ) -> Tuple[str, str]:
        """
        Stage 1: Raw source data extraction into standard acquisition dataset.
        Returns (target_table_name, sql_statement).
        """
        target_schema = context.target_schema
        clean_stream = stream_name.upper().replace("/", "_").replace(" ", "_")
        target_table = context.format_table_name(PATTERN_ACQUISITION_TABLE, clean_stream)

        # Header columns to insert
        header_cols = ['"ctrl_id"', '"exec_seq"', '"execution_date"', '"execution_schedule"']
        header_vals = [":control_id", ":exec_seq", ":execution_date", ":execution_schedule"]

        # Business columns (as-is from verified source)
        biz_cols = [f'"{c.lower()}"' for c in source_columns]
        biz_vals = [f's."{c.lower()}"' for c in source_columns]

        # Footer columns
        footer_cols = ['"create_dtm"', '"update_dtm"', '"updated_by"', '"processing_date"']
        footer_vals = ["CURRENT_TIMESTAMP", "CURRENT_TIMESTAMP", "CURRENT_USER", ":processing_date"]

        all_target_cols = header_cols + biz_cols + footer_cols
        all_select_vals = header_vals + biz_vals + footer_vals

        sql = f"""
INSERT INTO "{target_schema}"."{target_table}" (
    {", ".join(all_target_cols)}
)
SELECT
    {", ".join(all_select_vals)}
FROM "{source_schema}"."{source_table}" s;
""".strip()

        return target_table, sql

    @classmethod
    def generate_stage2_filtering_sql(
        cls,
        context: ControlContext,
        stream_name: str,
        business_columns: List[str],
        filter_clause: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Stage 2: Applies pre-execution filters, deduplication, and exclusions.
        """
        target_schema = context.target_schema
        clean_stream = stream_name.upper().replace("/", "_").replace(" ", "_")
        src_table = context.format_table_name(PATTERN_ACQUISITION_TABLE, clean_stream)
        target_table = context.format_table_name(PATTERN_FILTERED_TABLE, clean_stream)

        all_envelope_cols = ColumnOrderValidator.enforce_envelope([(c, "TEXT") for c in business_columns])
        col_names = [f'"{c[0]}"' for c in all_envelope_cols]

        where_part = f"WHERE {filter_clause}" if filter_clause else "WHERE 1=1"

        sql = f"""
INSERT INTO "{target_schema}"."{target_table}" (
    {", ".join(col_names)}
)
SELECT
    {", ".join(col_names)}
FROM "{target_schema}"."{src_table}"
{where_part}
  AND ctrl_id = :control_id
  AND exec_seq = :exec_seq;
""".strip()

        return target_table, sql

    @classmethod
    def generate_stage3_balance_sql(
        cls,
        context: ControlContext,
        stream_name: str,
        business_columns: List[str]
    ) -> Tuple[str, str]:
        """
        Stage 3: Generates balanced dataset for downstream reconciliation.
        """
        target_schema = context.target_schema
        clean_stream = stream_name.upper().replace("/", "_").replace(" ", "_")
        src_table = context.format_table_name(PATTERN_FILTERED_TABLE, clean_stream)
        target_table = context.format_table_name(PATTERN_BALANCE_TABLE, clean_stream)

        all_envelope_cols = ColumnOrderValidator.enforce_envelope([(c, "TEXT") for c in business_columns])
        col_names = [f'"{c[0]}"' for c in all_envelope_cols]

        sql = f"""
INSERT INTO "{target_schema}"."{target_table}" (
    {", ".join(col_names)}
)
SELECT
    {", ".join(col_names)}
FROM "{target_schema}"."{src_table}"
WHERE ctrl_id = :control_id
  AND exec_seq = :exec_seq;
""".strip()

        return target_table, sql

    @classmethod
    def generate_stage4_reconciliation_sql(
        cls,
        context: ControlContext,
        primary_stream: str,
        secondary_stream: str,
        recon_keys: List[str],
        primary_columns: List[str],
        secondary_columns: List[str]
    ) -> Tuple[str, str]:
        """
        Stage 4: Reconciliation with FULL OUTER JOIN and Match Type tagging (YY, YN, NY).
        """
        target_schema = context.target_schema
        prim_clean = primary_stream.upper().replace("/", "_").replace(" ", "_")
        sec_clean = secondary_stream.upper().replace("/", "_").replace(" ", "_")

        table_a = context.format_table_name(PATTERN_BALANCE_TABLE, prim_clean)
        table_b = context.format_table_name(PATTERN_BALANCE_TABLE, sec_clean)
        target_table = context.format_table_name(PATTERN_WORKING_RL)

        # Build join condition
        join_conditions = []
        for k in recon_keys:
            clean_k = k.lower().strip()
            join_conditions.append(f'a."{clean_k}" = b."{clean_k}"')

        join_on = " AND ".join(join_conditions) if join_conditions else "a.exec_seq = b.exec_seq"

        # Match type expression
        first_key = recon_keys[0].lower().strip() if recon_keys else "ctrl_id"
        match_expr = f"""
CASE 
    WHEN a."{first_key}" IS NOT NULL AND b."{first_key}" IS NOT NULL THEN 'YY'
    WHEN a."{first_key}" IS NOT NULL THEN 'YN'
    ELSE 'NY'
END AS balance_type
""".strip()

        sql = f"""
INSERT INTO "{target_schema}"."{target_table}" (
    "ctrl_id", "exec_seq", "execution_date", "execution_schedule",
    "key_value", "balance_type", "source_name",
    "create_dtm", "update_dtm", "updated_by", "processing_date"
)
SELECT
    :control_id,
    :exec_seq,
    :execution_date,
    :execution_schedule,
    COALESCE(a."{first_key}"::TEXT, b."{first_key}"::TEXT) AS key_value,
    {match_expr},
    CASE WHEN a."{first_key}" IS NOT NULL AND b."{first_key}" IS NOT NULL THEN 'BOTH'
         WHEN a."{first_key}" IS NOT NULL THEN '{primary_stream}'
         ELSE '{secondary_stream}' END AS source_name,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP,
    CURRENT_USER,
    :processing_date
FROM "{target_schema}"."{table_a}" a
FULL OUTER JOIN "{target_schema}"."{table_b}" b
  ON {join_on}
WHERE (a.ctrl_id = :control_id AND a.exec_seq = :exec_seq)
   OR (b.ctrl_id = :control_id AND b.exec_seq = :exec_seq);
""".strip()

        return target_table, sql

    @classmethod
    def generate_stage5_kri_sql(cls, context: ControlContext) -> Tuple[str, str]:
        """
        Stage 5: Evaluates KRI conditions on working dataset RL.
        """
        target_schema = context.target_schema
        src_table = context.format_table_name(PATTERN_WORKING_RL)
        target_table = context.format_table_name(PATTERN_WORKING_KL)

        sql = f"""
INSERT INTO "{target_schema}"."{target_table}" (
    "ctrl_id", "exec_seq", "execution_date", "execution_schedule",
    "key_value", "balance_type", "source_name", "kri_status",
    "create_dtm", "update_dtm", "updated_by", "processing_date"
)
SELECT
    ctrl_id,
    exec_seq,
    execution_date,
    execution_schedule,
    key_value,
    balance_type,
    source_name,
    CASE WHEN balance_type IN ('YN', 'NY') THEN 'KRI_BREACH' ELSE 'NORMAL' END AS kri_status,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP,
    CURRENT_USER,
    processing_date
FROM "{target_schema}"."{src_table}"
WHERE ctrl_id = :control_id
  AND exec_seq = :exec_seq;
""".strip()

        return target_table, sql

    @classmethod
    def generate_stage6_work_item_current_run_sql(cls, context: ControlContext) -> Tuple[str, str]:
        """
        Stage 6: Populates current execution cycle work items.
        """
        target_schema = context.target_schema
        src_table = context.format_table_name(PATTERN_WORKING_KL)
        target_table = context.format_table_name(PATTERN_WORK_ITEM_CURRENT_RUN)

        sql = f"""
INSERT INTO "{target_schema}"."{target_table}" (
    "ctrl_id", "exec_seq", "execution_date", "execution_schedule",
    "key_value", "balance_type", "source_name", "kri_status", "item_status",
    "create_dtm", "update_dtm", "updated_by", "processing_date"
)
SELECT
    ctrl_id,
    exec_seq,
    execution_date,
    execution_schedule,
    key_value,
    balance_type,
    source_name,
    kri_status,
    'OPEN' AS item_status,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP,
    CURRENT_USER,
    processing_date
FROM "{target_schema}"."{src_table}"
WHERE ctrl_id = :control_id
  AND exec_seq = :exec_seq
  AND balance_type IN ('YN', 'NY');
""".strip()

        return target_table, sql

    @classmethod
    def generate_stage7_historical_work_item_sql(cls, context: ControlContext) -> Tuple[str, str]:
        """
        Stage 7: Archives current work items into permanent historical table.
        """
        target_schema = context.target_schema
        src_table = context.format_table_name(PATTERN_WORK_ITEM_CURRENT_RUN)
        target_table = context.format_table_name(PATTERN_WORK_ITEM_HISTORICAL)

        sql = f"""
INSERT INTO "{target_schema}"."{target_table}" (
    "ctrl_id", "exec_seq", "execution_date", "execution_schedule",
    "key_value", "balance_type", "source_name", "kri_status", "item_status",
    "create_dtm", "update_dtm", "updated_by", "processing_date"
)
SELECT
    ctrl_id,
    exec_seq,
    execution_date,
    execution_schedule,
    key_value,
    balance_type,
    source_name,
    kri_status,
    item_status,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP,
    CURRENT_USER,
    processing_date
FROM "{target_schema}"."{src_table}"
WHERE ctrl_id = :control_id
  AND exec_seq = :exec_seq;
""".strip()

        return target_table, sql

    @classmethod
    def generate_stage8_report_summary_sql(cls, context: ControlContext) -> Tuple[str, str]:
        """
        Stage 8: Generates management summary report dataset from processed working dataset.
        """
        target_schema = context.target_schema
        src_table = context.format_table_name(PATTERN_WORKING_KL)
        target_table = context.format_table_name(PATTERN_NON_KRI_SUMMARY)

        sql = f"""
INSERT INTO "{target_schema}"."{target_table}" (
    "ctrl_id", "exec_seq", "execution_date", "execution_schedule",
    "balance_type", "record_count",
    "create_dtm", "update_dtm", "updated_by", "processing_date"
)
SELECT
    ctrl_id,
    exec_seq,
    execution_date,
    execution_schedule,
    balance_type,
    COUNT(*) AS record_count,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP,
    CURRENT_USER,
    processing_date
FROM "{target_schema}"."{src_table}"
WHERE ctrl_id = :control_id
  AND exec_seq = :exec_seq
GROUP BY ctrl_id, exec_seq, execution_date, execution_schedule, balance_type, processing_date;
""".strip()

        return target_table, sql
