import sys, os
sys.path.insert(0, os.path.abspath('.'))

from sqlalchemy import create_engine
from schema_migration_service import SchemaMigrationService

# Test 1: Target DB ra_ctrl.ctrl_23 on 13.127.198.137
target_url = 'postgresql://hla_user:ganesh@13.127.198.137:5432/hla'
eng_target = create_engine(target_url, connect_args={'connect_timeout': 10})
sms_target = SchemaMigrationService(eng_target)

print("--- DRY RUN: Target DB ra_ctrl.ctrl_23 ---")
res_target = sms_target.repair_all_tables(schema_names=['ra_ctrl.ctrl_23'], dry_run=True)
print(f"Total tables: {res_target['total_tables_inspected']}")
print(f"Tables to migrate: {res_target['tables_migrated']}")
print(f"Tables skipped: {res_target['tables_skipped']}")
for d in res_target['details']:
    if d['status'] == 'PLANNED':
        print(f"Table: {d['schema']}.{d['table']} | Rows: {d['rows_preserved']} | Removed: {d['columns_removed']}")
        print(f"   Before (first 6): {d['before_cols'][:6]}")
        print(f"   After  (first 6): {d['after_cols'][:6]}")
        print(f"   After  (last 4):  {d['after_cols'][-4:]}")

# Test 2: Source DB on localhost
local_url = 'postgresql://postgres:ganesh@localhost:5432/hla_db'
eng_local = create_engine(local_url)
sms_local = SchemaMigrationService(eng_local)

print("\n--- DRY RUN: Localhost Source DB ---")
res_local = sms_local.repair_all_tables(schema_names=['cmdb', 'pearl', 'qlik_report', 'ra', 'reports', 'sfdc'], dry_run=True)
print(f"Total tables: {res_local['total_tables_inspected']}")
print(f"Tables to migrate: {res_local['tables_migrated']}")
print(f"Tables skipped: {res_local['tables_skipped']}")
for d in res_local['details']:
    if d['status'] == 'PLANNED':
        print(f"Table: {d['schema']}.{d['table']} | Rows: {d['rows_preserved']} | Removed: {d['columns_removed']}")
        print(f"   Before (first 6): {d['before_cols'][:6]}")
        print(f"   After  (first 6): {d['after_cols'][:6]}")
        print(f"   After  (last 4):  {d['after_cols'][-4:]}")
