import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import excel_analyzer

res = excel_analyzer.analyze_excel_specification(r'C:\Users\Hp\Downloads\Control_Source_Logic.xlsx')

print("=== PARSED RESULT SUMMARY ===")
print("Control Overview:", res.get("control_overview"))
print("Template Compliance:", res.get("template_compliance"))
print("Sources Count:", len(res.get("sources", [])))
for i, s in enumerate(res.get("sources", [])):
    print(f"  Source {i+1}: DB='{s.get('source_db')}' | Schema='{s.get('source_schema')}' | Table='{s.get('source_table')}' | Load='{s.get('type_of_load')}'")

print("\nRules Summary:")
rules = res.get("rules", {})
print("  Input Streams:", len(rules.get("input_streams", [])))
print("  Filter Rules:", len(rules.get("filter_rules", [])))
print("  Balance Rules:", len(rules.get("balance_rules", [])))

print("\nData Model Count:", len(res.get("data_model", [])))
print("Buckets Count:", len(res.get("buckets", [])))
print("Config Tables Count:", len(res.get("config_tables", [])))
print("Mappings Count:", len(res.get("mappings", [])))
print("Derived Fields Count:", len(res.get("derived_fields", [])))
