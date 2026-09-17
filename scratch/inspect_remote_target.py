from sqlalchemy import create_engine, inspect, text

url = 'postgresql://hla_user:ganesh@13.127.198.137:5432/hla'
eng = create_engine(url, connect_args={'connect_timeout': 10})
insp = inspect(eng)
schemas = insp.get_schema_names()
print('Schemas on 13.127.198.137:', schemas)
for s in schemas:
    if not s.startswith('pg_') and s != 'information_schema':
        tables = insp.get_table_names(schema=s)
        print(f'\n--- Schema {s}: {len(tables)} tables ---')
        for t in tables:
            quoted = f'"{s}"."{t}"' if ('.' in s or '-' in s) else f'{s}."{t}"'
            try:
                with eng.connect() as c:
                    cnt = c.execute(text(f'SELECT count(*) FROM {quoted}')).scalar()
            except Exception as e:
                cnt = f"ERR: {e}"
            cols = [col['name'] for col in insp.get_columns(t, schema=s)]
            print(f'  {s}.{t} ({cnt} rows):')
            print(f'     first 6: {cols[:6]}')
            print(f'     last 4: {cols[-4:]}')
