import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()
from sqlalchemy import create_engine, text

url = os.getenv("DATABASE_URL", "postgresql://postgres:ganesh@localhost:5432/hla_db")
engine = create_engine(url)

with engine.connect() as conn:
    schemas = conn.execute(text("""
        SELECT schema_name FROM information_schema.schemata 
        WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
        ORDER BY schema_name;
    """)).fetchall()
    print("All Schemas:", [s[0] for s in schemas])
    
    for s in schemas:
        s_name = s[0]
        cnt = conn.execute(text("""
            SELECT count(*) 
            FROM information_schema.tables 
            WHERE table_schema = :s AND table_type = 'BASE TABLE';
        """), {"s": s_name}).scalar()
        print(f"Schema: {s_name} -> {cnt} tables")
        if cnt > 0 and s_name != 'public':
            tables = conn.execute(text("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = :s AND table_type = 'BASE TABLE'
                ORDER BY table_name;
            """), {"s": s_name}).fetchall()
            for t in tables:
                t_name = t[0]
                cols = conn.execute(text("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema = :s AND table_name = :t
                    ORDER BY ordinal_position;
                """), {"s": s_name, "t": t_name}).fetchall()
                row_cnt = conn.execute(text(f'SELECT COUNT(*) FROM "{s_name}"."{t_name}"')).scalar()
                print(f"  {t_name} [rows={row_cnt}]: {', '.join(c[0] for c in cols)}")

