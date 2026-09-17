import sys, os
sys.path.insert(0, os.path.abspath('.'))

import logging
from sqlalchemy import create_engine, text, inspect
from schema_migration_service import SchemaMigrationService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

print("================================================================================")
print("HLA STUDIO BACKEND SCHEMA MIGRATION EXECUTION (LOCALHOST SOURCE TABLES)")
print("================================================================================")

# ── 2. Source Database Schemas on Localhost 5432/hla_db ────────────────────────
local_url = 'postgresql://postgres:ganesh@localhost:5432/hla_db'
eng_local = create_engine(local_url)
sms_local = SchemaMigrationService(eng_local)

print("\n>>> MIGRATING SOURCE SCHEMAS: cmdb, pearl, qlik_report, ra, reports, sfdc on localhost ...")
source_schemas = ['cmdb', 'pearl', 'qlik_report', 'ra', 'reports', 'sfdc']
res_local = sms_local.repair_all_tables(schema_names=source_schemas, dry_run=False)

print(f"\n--- SOURCE MIGRATION SUMMARY (localhost) ---")
print(f"Total tables inspected: {res_local['total_tables_inspected']}")
print(f"Tables migrated:        {res_local['tables_migrated']}")
print(f"Tables skipped:         {res_local['tables_skipped']}")
print(f"Tables failed:          {res_local['tables_failed']}")
print(f"Total rows preserved:   {res_local['total_rows_preserved']}")

for d in res_local['details']:
    st = d.get('status')
    tbl = f"{d.get('schema')}.{d.get('table')}"
    rows = d.get('rows_preserved', 0)
    rem = d.get('columns_removed', [])
    err = d.get('error', '')
    if st == 'MIGRATED':
        print(f"  [PASS] {tbl}: {rows} rows preserved | Removed: {rem}")
    elif st == 'SKIPPED':
        print(f"  [-] {tbl}: {rows} rows | {d.get('message')}")
    elif st == 'FAILED':
        print(f"  [FAIL] {tbl}: FAILED | Error: {err}")

print("\n================================================================================")
print("SOURCE MIGRATION EXECUTION COMPLETED")
print("================================================================================")
