import sys, os
sys.path.insert(0, os.path.abspath('.'))

from app import app, db, Document, TargetArtifact, DBConnection, resolve_source_database_configs, find_table_across_databases
from target_logic_builder import build_target_logic_package

with app.app_context():
    doc = db.session.get(Document, 1)
    analysis = doc.analysis_data or {}
    source_configs = resolve_source_database_configs(doc.project_id)
    sources = analysis.get('sources') or []
    introspected_schemas = {}
    for s in sources:
        s_db = s.get('source_db', '')
        s_table = s.get('source_table') or s.get('full_table_name') or ''
        s_schema = s.get('source_schema', 'public')
        if s_table:
            meta = find_table_across_databases(source_configs, s_schema, s_table)
            introspected_schemas[s_table] = meta
            if s_db:
                introspected_schemas[f'{s_db}.{s_table}'] = meta

    target_conn = DBConnection.query.filter_by(project_id=doc.project_id, conn_role='target', target_env='dev').first()
    target_config = {
        'db_type': target_conn.db_type,
        'host': target_conn.host,
        'port': target_conn.port,
        'database_name': target_conn.database_name,
        'username': target_conn.username,
        'password': target_conn.password,
        'schema_name': 'ra_ctrl.ctrl_23',
        'target_env': 'dev'
    }
    pkg = build_target_logic_package(analysis, introspected_schemas, target_config)
    print("Generated DDL lines:", len(pkg['ddl'].splitlines()))
    for kw in ['id INTEGER NOT NULL', 'batch_id', 'execution_cycle_date', 'kri_flag']:
        print(f'Contains "{kw}" in ddl?: {kw in pkg["ddl"]}')
    
    pos = pkg['ddl'].find('dl_itsm_cmdb_daily_dump')
    if pos != -1:
        print('dl_itsm_cmdb_daily_dump DDL snippet:\n', pkg['ddl'][pos:pos+400])

    pos2 = pkg['ddl'].find('ctrl_23_source_dataset_ddos')
    if pos2 != -1:
        print('ctrl_23_source_dataset_ddos snippet:\n', pkg['ddl'][pos2:pos2+400])
