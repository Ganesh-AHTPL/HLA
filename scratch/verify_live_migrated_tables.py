from sqlalchemy import create_engine, inspect, text

print("================================================================================")
print("VERIFYING LIVE POSTGRESQL TABLE STRUCTURES AFTER MIGRATION")
print("================================================================================")

# 1. Target Database ra_ctrl.ctrl_23
target_url = 'postgresql://hla_user:ganesh@13.127.198.137:5432/hla'
eng_target = create_engine(target_url, connect_args={'connect_timeout': 15})
insp_target = inspect(eng_target)

print("\n--- TARGET TABLES IN ra_ctrl.ctrl_23 (sample) ---")
sample_target_tables = [
    "dl_itsm_cmdb_daily_dump",
    "stg_dl_itsm_cmdb_daily_dump_clean",
    "ctrl_23_balanced_dataset",
    "ctrl_23_recon_matches",
    "ctrl_23_recon_exceptions",
    "target_report_dataset",
    "ctrl_23_source_dataset_ddos",
    "ctrl_23_filtered_dataset_ddos",
    "ctrl_config"
]

for t in sample_target_tables:
    cols = [c['name'] for c in insp_target.get_columns(t, schema='ra_ctrl.ctrl_23')]
    with eng_target.connect() as conn:
        cnt = conn.execute(text(f'SELECT count(*) FROM "ra_ctrl.ctrl_23"."{t}";')).scalar()
    print(f"\nTable: ra_ctrl.ctrl_23.{t} (Rows: {cnt})")
    print(f"  First 4: {cols[:4]}")
    if len(cols) > 8:
        print(f"  Middle:  {cols[4:7]} ... ({len(cols)-8} business cols)")
    print(f"  Last 4:  {cols[-4:]}")
    # Verify no unwanted generic columns in generated tables
    if t != "ctrl_config":
        for unwanted in ['batch_id', 'execution_cycle_date', 'record_status', 'source_reference', 'kri_flag']:
            assert unwanted not in cols, f"Unwanted column {unwanted} found in {t}!"

# 2. Localhost Source Tables
local_url = 'postgresql://postgres:ganesh@localhost:5432/hla_db'
eng_local = create_engine(local_url)
insp_local = inspect(eng_local)

print("\n--- SOURCE TABLES ON LOCALHOST ---")
for s, t in [
    ("cmdb", "dl_itsm_cmdb_daily_dump"),
    ("pearl", "dl_pearl_active_profiles"),
    ("qlik_report", "dl_ra_order_report_daily"),
    ("ra", "stg_rk_ckt_recon_final"),
    ("reports", "dl_vdom_firewall_audit_report"),
    ("sfdc", "copf_id"),
]:
    cols = [c['name'] for c in insp_local.get_columns(t, schema=s)]
    with eng_local.connect() as conn:
        cnt = conn.execute(text(f'SELECT count(*) FROM "{s}"."{t}";')).scalar()
    print(f"\nTable: {s}.{t} (Rows: {cnt})")
    print(f"  First 4: {cols[:4]}")
    print(f"  Last 4:  {cols[-4:]}")
    assert cols[:4] == ["ctrl_id", "exec_seq", "execution_date", "execution_schedule"]
    assert cols[-4:] == ["create_dtm", "update_dtm", "updated_by", "processing_date"]
    assert "id" not in cols[:4]
    assert cnt == 100

print("\n================================================================================")
print("ALL LIVE TABLE STRUCTURES VERIFIED CLEAN AND CONFORMANT!")
print("================================================================================")
