import sys
import json
sys.path.insert(0, '.')
from models import Document
from app import app

with app.app_context():
    doc = Document.query.get(79)
    ad = doc.analysis_data or {}
    print("=== CONTROL OVERVIEW ===")
    print(json.dumps(ad.get("control_overview", {}), indent=2))
    
    print("\n=== SOURCES ===")
    print(json.dumps(ad.get("sources", []), indent=2))
    
    print("\n=== CONFIG TABLES ===")
    print(json.dumps(ad.get("config_tables", []), indent=2))
    
    print("\n=== FILTER RULES (first 5) ===")
    print(json.dumps(ad.get("filter_rules", [])[:5], indent=2))
    
    print("\n=== DATA MODEL (first 5) ===")
    print(json.dumps(ad.get("data_model", [])[:5], indent=2))
    
    print("\n=== MAPPINGS / ATTRIBUTE MAPPINGS count ===")
    mappings = ad.get("attribute_mappings") or ad.get("mappings") or []
    print(f"Total mappings: {len(mappings)}")
    for m in mappings:
        print(f"  Target Col: {m.get('target_column')} | Src Table: {m.get('source_table')} | Src Field: {m.get('source_field')} | Type: {m.get('mapping_type')} | Logic: {m.get('derivation_logic')}")
