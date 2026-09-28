import sys, os
sys.path.insert(0, os.path.abspath('.'))

from app import app, db, _load_source_data_into_target, extract_document_source_entities, resolve_source_database_configs
from models import Document, TargetArtifact
from target_logic_builder import (
    idempotent_deploy,
    inspect_target_schema,
    generate_target_ddl,
    generate_transformation_sql,
    validate_transformation_pipeline_against_schema,
    _split_sql_statements,
    _has_executable_sql
)
from db_fetcher import build_connection_url
from sqlalchemy import create_engine, text, inspect
import uuid

with app.app_context():
    doc = Document.query.get(198)
    artifact = TargetArtifact.query.filter_by(document_id=doc.id).first()
    target_config = {
        'db_type': 'postgresql',
        'host': 'localhost',
        'port': 5432,
        'database_name': 'hla_db',
        'username': 'postgres',
        'password': 'ganesh',
        'schema_name': 'Unique'
    }
    
    execution_id = str(uuid.uuid4())
    doc_sources = extract_document_source_entities(doc.analysis_data)
    
    ddl = generate_target_ddl(
        'Unique',
        'postgresql',
        doc_sources,
        doc.analysis_data.get('rules', {}),
        doc.analysis_data.get('mappings', []),
        doc.analysis_data.get('config_tables'),
        analysis_data=doc.analysis_data
    )
    artifact.generated_ddl = ddl
    
    success, message, recon, stages = idempotent_deploy(target_config, ddl, analysis_data=doc.analysis_data)
    print('Deploy DDL:', success, message)
    
    source_configs = resolve_source_database_configs(doc.project_id)
    data_load = _load_source_data_into_target(
        source_configs, doc_sources, target_config, 'Unique', execution_id,
        analysis_data=doc.analysis_data,
        log_fn=lambda msg: print('[LOAD LOG]', msg)
    )
    print('Data Load:', data_load)
    
    target_url = build_connection_url(target_config)
    t_eng = create_engine(target_url)
    live_target_meta = inspect_target_schema(t_eng, 'Unique')
    
    transform_sql = generate_transformation_sql(
        'Unique',
        'postgresql',
        doc_sources,
        doc.analysis_data.get('rules', {}),
        doc.analysis_data.get('mappings', []),
        doc.analysis_data.get('config_tables'),
        doc.analysis_data.get('control_overview'),
        analysis_data=doc.analysis_data,
        execution_id=execution_id,
        target_meta=live_target_meta,
        ddl_script=ddl
    )
    transform_sql = transform_sql.replace(':execution_id', f"'{execution_id}'")
    print('Transform SQL length:', len(transform_sql))
    
    valid_sql, valid_msg, sql_diags = validate_transformation_pipeline_against_schema(
        target_config,
        transform_sql,
        ddl_script=ddl,
        strict_not_null=False
    )
    print('Validation SQL valid:', valid_sql)
    
    statements = _split_sql_statements(transform_sql)
    print('Executing statements count:', len(statements))
    with t_eng.connect() as conn:
        for idx, stmt in enumerate(statements):
            clean = stmt.strip()
            if clean and _has_executable_sql(clean):
                conn.execute(text(clean))
                conn.commit()
                print(f'Executed stmt {idx+1}')
    
    # Query physical counts in target DB
    insp = inspect(t_eng)
    for tbl in insp.get_table_names(schema='Unique'):
        with t_eng.connect() as conn:
            cnt = conn.execute(text(f'SELECT COUNT(*) FROM "Unique".{tbl}')).scalar()
            print(f'Target table Unique.{tbl}: {cnt} rows')
