import re, os, sys
sys.path.insert(0, ".")
from app import app, db, Document
from target_logic_builder import generate_target_ddl, build_connection_url, create_engine, inspect
from db_fetcher import get_env_db_password

with app.app_context():
    doc = db.session.get(Document, 57)
    ddl = generate_target_ddl("ra_ctrl", "postgresql", doc.analysis_data.get("sources"), doc.analysis_data.get("rules"), doc.analysis_data.get("mappings"), {}, doc.analysis_data)
    cfg = {"db_type": "postgresql", "host": "localhost", "port": 5432, "database_name": "hla_db", "username": "postgres", "password": get_env_db_password(), "schema_name": "ra_ctrl"}
    engine = create_engine(build_connection_url(cfg))
    inspector = inspect(engine)
    existing = inspector.get_table_names(schema="ra_ctrl")
    
    # Regex test
    matches = re.findall(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([^\s\(]+)', ddl, flags=re.IGNORECASE)
    print("Matches from raw regex:", matches)
    cleaned_req = []
    for m in matches:
        t = m.split(".")[-1].strip('"\';` ')
        if t:
            cleaned_req.append(t)
    print("Existing in DB:", existing)
    print("Cleaned Required:", cleaned_req)
    missing = [t for t in cleaned_req if t.lower() not in [e.lower() for e in existing]]
    print("Missing:", missing)
