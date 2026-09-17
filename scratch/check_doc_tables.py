import sys, os
sys.path.insert(0, os.path.abspath("."))
from app import app, db, Document
with app.app_context():
    doc = db.session.get(Document, 57)
    if doc and doc.analysis_data:
        dm = doc.analysis_data.get('data_model', [])
        print('DATA MODEL TABLES:')
        for t in dm:
            print(f"  {t.get('table_name')} -> load_type: {t.get('load_type')}")
        print('\nSOURCES:')
        for s in doc.analysis_data.get('sources', []):
            print(f"  {s.get('source_table')} -> load_type: {s.get('type_of_load')}")
