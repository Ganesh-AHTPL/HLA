import psycopg2

dbs = ['postgres', 'sales', 'wondersoft', 'postgress', 'school_db', 'hla_db']
for db_name in dbs:
    try:
        conn = psycopg2.connect(dbname=db_name, user='postgres', password='ganesh', host='localhost', port=5432)
        cur = conn.cursor()
        cur.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog', 'information_schema')")
        rows = cur.fetchall()
        print(f"=== DB: {db_name} (found {len(rows)} tables) ===")
        for r in rows:
            if any(k in r[1].lower() for k in ['dl_', 'cmdb', 'copf', 'pearl', 'order', 'firewall', 'vdom', 'ckt']):
                print(f"   {r[0]}.{r[1]}")
        conn.close()
    except Exception as e:
        print(f"DB {db_name} err: {e}")
