import sys, os
sys.path.insert(0, os.path.abspath("."))
from backend.core.semantic_analyzer import SemanticAnalyzer
from target_logic_builder import build_target_logic_package

analysis = SemanticAnalyzer.analyze_workbook('./uploads/projects/11/Generic_HLA_Architecture_Template_CORRECTED.xlsx')
print(f"Sources: {len(analysis.get('sources', []))}")
for s in analysis.get('sources', []):
    print(f"  Source: {s.get('canonical_name')}")

package = build_target_logic_package(analysis, {}, {"environment": "dev", "schema_name": "public", "db_type": "postgresql"})
print("\n--- GENERATED DDL ---")
print(package.get("ddl"))

print("\n--- GENERATED SQL ---")
print(package.get("transformation_sql"))

print("\n--- GENERATED PYSPARK ---")
print(package.get("pyspark_code"))
