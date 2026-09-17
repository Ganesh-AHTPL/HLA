from sqlalchemy import create_engine, inspect, text

url = 'postgresql://hla_user:ganesh@13.127.198.137:5432/hla'
eng = create_engine(url, connect_args={'connect_timeout': 10})
insp = inspect(eng)
schema = 'ra_ctrl.ctrl_23'

tables = insp.get_table_names(schema=schema)
print(f"Total tables in {schema}: {len(tables)}")
for t in sorted(tables):
    quoted = f'"{schema}"."{t}"'
    with eng.connect() as c:
        cnt = c.execute(text(f'SELECT count(*) FROM {quoted}')).scalar()
    cols = [col['name'] for col in insp.get_columns(t, schema=schema)]
    pk = insp.get_pk_constraint(t, schema=schema)
    print(f"\nTABLE: {t} (Rows: {cnt}, PK: {pk.get('constrained_columns', [])})")
    print(f"  COLUMNS ({len(cols)}): {cols}")
