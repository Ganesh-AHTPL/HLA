import sys
sys.path.insert(0, '.')
from models import db
from app import app
from sqlalchemy import text

with app.app_context():
    schemas = db.session.execute(text("SELECT schema_name FROM information_schema.schemata ORDER BY schema_name;")).fetchall()
    print("ALL SCHEMAS IN hla_db:")
    for s in schemas:
        print(" -", s[0])

    tables = db.session.execute(text("""
        SELECT table_schema, table_name 
        FROM information_schema.tables 
        WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
        ORDER BY table_schema, table_name;
    """)).fetchall()
    print("\nALL TABLES IN NON-SYSTEM SCHEMAS:")
    for t in tables:
        print(f" {t[0]}.{t[1]}")
