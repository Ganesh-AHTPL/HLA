import sys, os
from sqlalchemy import create_engine, text

eng = create_engine('postgresql://postgres:ganesh@localhost:5432/hla_db')
with eng.connect() as conn:
    schemas = conn.execute(text("SELECT schema_name FROM information_schema.schemata")).fetchall()
    print("Schemata in DB:", [s[0] for s in schemas])
    for s in [s[0] for s in schemas if 'unique' in s[0].lower()]:
        tbls = conn.execute(text(f"SELECT table_name FROM information_schema.tables WHERE table_schema = '{s}'")).fetchall()
        print(f"Tables in schema '{s}':", [t[0] for t in tbls])
