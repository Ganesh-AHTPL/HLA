import openpyxl

wb = openpyxl.load_workbook('uploads/projects/67/Control23_Source_Logic_2.xlsx', data_only=True)

# 1. Source Systems
ws_sources = wb['Source Systems']
source_tables = []
for r in range(4, ws_sources.max_row + 1):
    tbl = ws_sources.cell(r, 1).value
    db = ws_sources.cell(r, 2).value
    freq = ws_sources.cell(r, 3).value
    sched = ws_sources.cell(r, 4).value
    dur = ws_sources.cell(r, 5).value
    l_type = ws_sources.cell(r, 6).value
    if tbl:
        source_tables.append({
            'row': r, 'table': tbl, 'db': db, 'frequency': freq, 'schedule': sched, 'type': l_type
        })

# 2. Attribute Mapping
ws_attr = wb['Attribute Mapping']
target_cols = []
for r in range(4, ws_attr.max_row + 1):
    sno = ws_attr.cell(r, 1).value
    cname = ws_attr.cell(r, 2).value
    sfield = ws_attr.cell(r, 3).value
    tname = ws_attr.cell(r, 4).value
    rem = ws_attr.cell(r, 5).value
    if cname:
        target_cols.append({
            'row': r, 'sno': sno, 'col': cname, 'source_field': sfield, 'table': tname, 'remark': rem
        })

# 3. Business Rules
ws_rules = wb['Business Rules']
rules = []
for r in range(4, ws_rules.max_row + 1):
    rid = ws_rules.cell(r, 1).value
    stream = ws_rules.cell(r, 2).value
    desc = ws_rules.cell(r, 3).value
    rule = ws_rules.cell(r, 4).value
    if rid or desc:
        rules.append({
            'row': r, 'id': rid, 'stream': stream, 'desc': desc, 'rule': rule
        })

# 4. Buckets & KRI Logic
ws_kri = wb['Buckets & KRI Logic']
kri_items = []
for r in range(4, ws_kri.max_row + 1):
    out = ws_kri.cell(r, 1).value
    kri_id = ws_kri.cell(r, 2).value
    desc = ws_kri.cell(r, 3).value
    logic = ws_kri.cell(r, 4).value
    imp_type = ws_kri.cell(r, 5).value
    imp_calc = ws_kri.cell(r, 6).value
    capex = ws_kri.cell(r, 7).value
    rem = ws_kri.cell(r, 8).value
    if out or kri_id or desc:
        kri_items.append({
            'row': r, 'bucket': out, 'kri_id': kri_id, 'desc': desc, 'logic': logic,
            'impact_type': imp_type, 'impact_calc': imp_calc, 'capex': capex, 'remarks': rem
        })

# 5. Data Model
ws_dm = wb['Data Model']
dm_entities = []
for r in range(4, ws_dm.max_row + 1):
    stage = ws_dm.cell(r, 1).value
    tname = ws_dm.cell(r, 2).value
    std = ws_dm.cell(r, 3).value
    reuse = ws_dm.cell(r, 4).value
    l_type = ws_dm.cell(r, 5).value
    desc = ws_dm.cell(r, 6).value
    if tname:
        dm_entities.append({
            'row': r, 'stage': stage, 'table': tname, 'standard': std, 'reuse': reuse, 'type': l_type, 'desc': desc
        })

# 6. Report Derivation Logic
ws_rep = wb['Report Derivation Logic']
rep_attrs = []
curr_report = "Reconciliation Summary Report"
for r in range(1, ws_rep.max_row + 1):
    c1 = str(ws_rep.cell(r, 1).value or '').strip()
    if 'Report - Attribute Derivation' in c1:
        curr_report = c1.replace(' - Attribute Derivation', '').strip()
        continue
    c2 = ws_rep.cell(r, 2).value
    c3 = ws_rep.cell(r, 3).value
    c4 = ws_rep.cell(r, 4).value
    c5 = ws_rep.cell(r, 5).value
    if c1 and c1.isdigit():
        rep_attrs.append({
            'row': r, 'report': curr_report, 'sno': c1, 'attr': c2, 'source_field': c3, 'table': c4, 'remark': c5
        })

# 7. Config Tables
ws_cfg = wb['Config Tables']
configs = {'internal_profiles': [], 'managed_services': [], 'dummy_ips': [], 'internal_customers': []}
curr_cfg = None
for r in range(1, ws_cfg.max_row + 1):
    val = str(ws_cfg.cell(r, 1).value or '').strip()
    if not val:
        continue
    if 'Internal Profiles' in val:
        curr_cfg = 'internal_profiles'
        continue
    elif 'Managed Service' in val:
        curr_cfg = 'managed_services'
        continue
    elif 'Test/Dummy IP' in val:
        curr_cfg = 'dummy_ips'
        continue
    elif 'Customer Name Exclusion' in val or 'Internal / Test Customer' in val:
        curr_cfg = 'internal_customers'
        continue
    
    if val in ['Hostname', 'Managed Services', 'IP', 'Customer Name']:
        continue
    if curr_cfg:
        configs[curr_cfg].append({'row': r, 'value': val})

print("=== DETAILED EXTRACTION METRICS ===")
print(f"1. Source tables discovered: {len(source_tables)}")
for st in source_tables:
    print(f"   - Row {st['row']}: {st['table']} | DB: {st['db']} | Load: {st['type']}")

print(f"\n2. Target columns discovered: {len(target_cols)}")
unresolved_target_cols = []
for tc in target_cols:
    src_f = str(tc['source_field'] or '').strip()
    tbl = str(tc['table'] or '').strip()
    is_derived = 'derived' in src_f.lower() or 'derived' in str(tc['col']).lower()
    if not tbl and not is_derived:
        unresolved_target_cols.append(tc)
print(f"   - Directly mapped: 0 (No physical table/column specified in Attribute Mapping sheet)")
print(f"   - Logical stream mapped: {len(target_cols) - len([t for t in target_cols if 'derived' in str(t['source_field']).lower()])}")
print(f"   - Derived: {len([t for t in target_cols if 'derived' in str(t['source_field']).lower()])}")
print(f"   - Target columns with missing physical table binding: {len(unresolved_target_cols)}")

print(f"\n3. Business rules discovered: {len(rules)}")
for ru in rules:
    print(f"   - Row {ru['row']}: [{ru['id']}] Stream: {ru['stream']} | Desc: {ru['desc']}")

print(f"\n4. KRI/buckets discovered: {len(kri_items)}")
for ki in kri_items:
    print(f"   - Row {ki['row']}: [{ki['bucket']}] KRI: {ki['kri_id']} | Desc: {ki['desc'][:40]}")

print(f"\n5. Data model entities discovered: {len(dm_entities)}")
unique_dm = set(e['table'] for e in dm_entities)
print(f"   - Unique table names: {len(unique_dm)}")

print(f"\n6. Report attributes discovered: {len(rep_attrs)}")
reps = set(ra['report'] for ra in rep_attrs)
for rep in reps:
    attrs = [ra for ra in rep_attrs if ra['report'] == rep]
    print(f"   - {rep}: {len(attrs)} attributes")

print(f"\n7. Configuration values discovered: {sum(len(v) for v in configs.values())}")
print(f"   - Internal Profiles (hostnames): {len(configs['internal_profiles'])}")
print(f"   - Managed Services: {len(configs['managed_services'])}")
print(f"   - Test/Dummy IPs: {len(configs['dummy_ips'])}")
print(f"   - Internal / Test Customers: {len(configs['internal_customers'])}")
