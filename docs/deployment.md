# 12-Phase Deployment Engine

## 1. 12 Deployment Phases
- **Phase 1: HLA Parsing**: Ingest workbook into `HLAControl` model.
- **Phase 2: Control Resolution**: Instantiate runtime `ControlContext`.
- **Phase 3: Source Dependency Resolution**: Resolve streams in `SourceRegistry`.
- **Phase 4: Physical Schema Introspection**: Introspect PostgreSQL metadata.
- **Phase 5: Attribute Mapping**: Verify physical column existence for all attributes.
- **Phase 6: Entity Planning**: Determine required stage datasets.
- **Phase 7: DDL Generation**: Generate deterministic DDL with envelope columns.
- **Phase 8: DDL Validation**: Check for forbidden auto-columns or syntax errors.
- **Phase 9: SQL Generation**: Generate 8-stage transformation SQL statements.
- **Phase 10: SQL Validation**: Validate identifiers and parameterization.
- **Phase 11: Deployment Preview**: Return JSON preview of operations and migration plans.
- **Phase 12: Execution**: Execute atomic migrations and DDL creation.

If any phase fails, the pipeline halts immediately and reports structured diagnostic information.
