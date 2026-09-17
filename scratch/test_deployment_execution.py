import sys, os
sys.path.insert(0, os.path.abspath('.'))

from sqlalchemy import create_engine, text, inspect
from target_logic_builder import (
    generate_target_ddl,
    generate_transformation_sql,
    validate_transformation_pipeline_against_schema,
    inspect_target_schema,
    idempotent_deploy,
    _split_sql_statements,
    _has_executable_sql
)
from db_fetcher import build_connection_url

# Load target configuration from DB connection #2 (Target DEV)
target_cfg = {
    "db_type": "postgresql",
    "host": "13.127.198.137",
    "port": 5432,
    "database_name": "hla",
    "username": "hla_user",
    "password": "ganesh",
    "schema_name": "ra_ctrl.ctrl_23",
    "target_env": "dev"
}

t_url = build_connection_url(target_cfg)
t_eng = create_engine(t_url, connect_args={"connect_timeout": 15})

# Fetch document analysis data
app_eng = create_engine('postgresql://postgres:ganesh@localhost:5432/hla_db')
with app_eng.connect() as conn:
    row = conn.execute(text('SELECT analysis_data FROM public.documents WHERE analysis_data IS NOT NULL LIMIT 1')).fetchone()
    analysis = row[0]

sources = analysis.get("sources", [])
rules = analysis.get("rules", {})
mappings = analysis.get("mappings", [])
cfg_tables = analysis.get("config_tables")
ctrl_overview = analysis.get("control_overview")

# 1. Generate Target DDL with updated envelope
ddl = generate_target_ddl(
    "ra_ctrl.ctrl_23",
    "postgresql",
    sources,
    rules,
    mappings,
    {},
    analysis_data=analysis
)

# 2. Inspect live target schema
live_meta = inspect_target_schema(t_eng, "ra_ctrl.ctrl_23")

# 3. Generate Transformation SQL
exec_id = "test-migration-verify-001"
transform_sql = generate_transformation_sql(
    "ra_ctrl.ctrl_23",
    "postgresql",
    sources,
    rules,
    mappings,
    cfg_tables,
    ctrl_overview,
    analysis_data=analysis,
    execution_id=exec_id,
    target_meta=live_meta,
    ddl_script=ddl
)

print(f"Generated transformation SQL length: {len(transform_sql)} chars")

# 4. Run Schema Validator
is_valid, msg, diags = validate_transformation_pipeline_against_schema(
    target_cfg,
    transform_sql,
    strict_not_null=False
)

print(f"Schema Validation Result: valid={is_valid}")
if not is_valid:
    print(f"Validator message: {msg}")
    print(f"Diags: {diags}")
else:
    print("Schema validation passed cleanly with 0 errors!")

assert is_valid, f"Schema validation failed: {msg}"

# 5. Execute transformation SQL against live target database
stmts = _split_sql_statements(transform_sql.replace(":execution_id", f"'{exec_id}'"))
executed_steps = 0
with t_eng.connect() as conn:
    for stmt in stmts:
        clean = stmt.strip()
        if clean and _has_executable_sql(clean):
            conn.execute(text(clean))
            conn.commit()
            executed_steps += 1

print(f"Transformation executed successfully: {executed_steps} steps completed!")
print("ALL VERIFICATION CHECKS PASSED!")
