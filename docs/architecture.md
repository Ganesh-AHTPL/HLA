# Generic HLA-Driven ETL & Reconciliation Architecture

## 1. System Overview
HLA Studio is a generic, HLA-driven ETL, reconciliation, and reporting engine. It translates High-Level Architecture (HLA) specifications into parameterized, schema-validated, and deterministic PostgreSQL pipelines.

```
HLA Specification (.xlsx)
      ↓
HLAParser (Excel Analyzer)
      ↓
ControlContext (Dynamic Control Identifier)
      ↓
Logical Source Stream Resolution (SourceRegistry)
      ↓
Physical Source Table Resolution (PhysicalSourceResolver)
      ↓
PostgreSQL Schema Introspection (PostgresSchemaIntrospector)
      ↓
Physical Column Resolution (ColumnResolver)
      ↓
Pre-Flight Dependency Validation (DependencyResolver)
      ↓
Staged Pipeline Planner (PipelinePlanner)
      ↓
Deterministic DDL Generation (DDLGenerator)
      ↓
Transformation SQL Generation (SQLGenerator)
      ↓
Schema and SQL Validation (SchemaValidator)
      ↓
Deployment Engine (12-Phase Quality Gate)
      ↓
Multi-Stage Execution (StageManager)
      ↓
Audit & Telemetry (ExecutionContext)
      ↓
Management Reporting
```

## 2. Strict Domain Separation
1. **Logical Source Stream**: Abstract business entity name from HLA (e.g., `VUTM/DOOS`, `CMDB`, `Circuit Reco`).
2. **Physical Source Table**: Real PostgreSQL table/view (e.g., `reports.dl_vdom_firewall_audit_report`, `cmdb.dl_itsm_cmdb_daily_dump`).
3. **Physical Source Column**: Real introspected column in PostgreSQL (e.g., `vdom`, `hostname`, `ip`).
4. **Acquisition Dataset**: Raw extracted staging dataset with platform envelope (`CTRL_{X}_SOURCE_DATASET_*`).
5. **Filtered Dataset**: Cleaned, deduplicated, rule-applied dataset (`CTRL_{X}_FILTERED_DATASET_*`).
6. **Balance Dataset**: Balanced entity dataset ready for matching (`CTRL_{X}_BALANCE_DATASET_*`).
7. **Reconciliation Dataset**: Matched working dataset with `YY`, `YN`, `NY` balance typing (`CTRL_{X}_WORKING_DATASET_RL`).
8. **KRI Dataset**: Outcome dataset after applying KRI rules (`CTRL_{X}_WORKING_DATASET_KL`).
9. **Work Item Datasets**: Current cycle and permanent historical tracking (`CTRL_{X}_WORK_ITEM_CURRENT_RUN`, `CTRL_{X}_WORK_ITEM`).
10. **Report Datasets**: Downstream aggregated reporting (`CTRL_{X}_NON_KRI_SUMMARY`, `CTRL_{X}_KRI_SUMMARY`, etc.).

## 3. Platform Envelope Standard
Every generated table physically contains:
- **First Four (Header)**: `ctrl_id`, `exec_seq`, `execution_date`, `execution_schedule`
- **Middle**: HLA-defined source and business columns
- **Last Four (Footer)**: `create_dtm`, `update_dtm`, `updated_by`, `processing_date`
