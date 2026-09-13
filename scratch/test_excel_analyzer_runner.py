import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from excel_analyzer import analyze_excel_specification
import json

def test_run():
    res = analyze_excel_specification(r"C:\Users\Hp\Downloads\Control23_Source_Logic.xlsx")
    print("Control identification:", res["control_overview"]["identification"])
    print("Target schema:", res["control_overview"]["target_schema"])
    print("Total sources parsed:", len(res["sources"]))
    for s in res["sources"]:
        print(f"  Source: {s['source_name']} -> {s['full_table_name']} (DB: {s['database_name']}@{s['server']}:{s['port']})")
    
    print("\nTotal source DBs parsed:", len(res["source_databases"]))
    for db in res["source_databases"]:
        print(f"  DB: {db['source_db_name']} | Host: {db['host']} | Schema: {db['schema_name']} | Tables: {db['tables']}")

    print("\nData Model tables:", len(res["data_model"]))
    for dm in res["data_model"][:5]:
        print(f"  Stage: {dm['stage']} | Table: {dm['table_name']} | Load: {dm['load_type']}")

    print("\nRules summary:")
    print("  Input streams:", len(res["rules"]["input_streams"]))
    print("  Filter rules:", len(res["rules"]["filter_rules"]))
    print("  Balance rules:", len(res["rules"]["balance_rules"]))
    print("  Recon flows:", len(res["rules"]["reconciliation_flows"]))

    print("\nResultant Buckets count:", len(res["buckets"]))
    for b in res["buckets"][:6]:
        print(f"  Bucket: {b['bucket_id']} | KRI: {b['kri_id']} | Desc: {b['description']}")

    print("\nDerived Fields count:", len(res["derived_fields"]))
    for df in res["derived_fields"]:
        print(f"  Derived Field: {df['field_name']} | Referenced cols: {df['referenced_columns']}")

    print("\nConfig tables count:", len(res["config_tables"]))
    for ct in res["config_tables"]:
        print(f"  Config: {ct['table_name']} | Col: {ct['target_column']} | Count: {ct['record_count']}")

    print("\nMappings count:", len(res["mappings"]))
    for m in res["mappings"][:6]:
        print(f"  Mapping: {m['attribute_id']} | Source: {m['source_table']}.{m['source_field']} -> Target: {m['target_column']}")

    print("\nSummary counts:")
    print(json.dumps(res["summary_counts"], indent=2))

if __name__ == "__main__":
    test_run()
