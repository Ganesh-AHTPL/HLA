import sys, os
sys.path.insert(0, os.path.abspath('.'))
import logging
from sqlalchemy import create_engine, inspect, text
from schema_migration_service import SchemaMigrationService

logging.basicConfig(level=logging.INFO)
local_url = 'postgresql://postgres:ganesh@localhost:5432/hla_db'
eng_local = create_engine(local_url)
insp = inspect(eng_local)
print('All schemas in hla_db:', insp.get_schema_names())

sms = SchemaMigrationService(eng_local)
discovered = sms.discover_hla_tables()
print(f'\nDiscovered {len(discovered)} HLA tables:')
for schema, table in discovered:
    plan = sms.plan_table_migration(schema, table)
    print(f"\n=== TABLE: {schema}.{table} ===")
    print(f"  Rows: {plan['row_count']}")
    print(f"  Needs migration: {plan['needs_migration']}")
    print(f"  Columns to remove: {plan['columns_to_remove']}")
    print(f"  Current columns ({len(plan['current_columns'])}): {plan['current_columns']}")
    print(f"  Expected columns ({len(plan['expected_columns'])}): {plan['expected_columns']}")
