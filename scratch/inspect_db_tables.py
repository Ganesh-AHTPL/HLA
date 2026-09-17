import os
from sqlalchemy import create_engine, inspect, text
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv("DATABASE_URL", "postgresql://postgres:ganesh@localhost:5432/hla_db")
engine = create_engine(db_url)
insp = inspect(engine)

all_schemas = insp.get_schema_names()
print("All Schemas in DB:", all_schemas)

for s in all_schemas:
    if s.startswith("pg_") or s == "information_schema":
        continue
    tables = insp.get_table_names(schema=s)
    print(f"\n================ SCHEMA: {s} ({len(tables)} tables) ================")
    for t in tables:
        try:
            with engine.connect() as conn:
                quoted = f'"{s}"."{t}"' if ("." in s or "-" in s) else f'{s}."{t}"'
                cnt = conn.execute(text(f'SELECT count(*) FROM {quoted}')).scalar()
        except Exception as e:
            cnt = f"ERR: {e}"
        cols = insp.get_columns(t, schema=s)
        col_names = [c["name"] for c in cols]
        print(f"Table: {s}.{t} | Rows: {cnt}")
        print(f"  First 8 cols: {col_names[:8]}")
        print(f"  Last 6 cols: {col_names[-6:]}")
