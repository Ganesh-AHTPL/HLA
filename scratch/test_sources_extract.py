import sys, os
sys.path.insert(0, os.path.abspath("."))
from backend.core.semantic_analyzer import SemanticAnalyzer

res = SemanticAnalyzer.analyze_workbook('./uploads/projects/11/Generic_HLA_Architecture_Template_CORRECTED.xlsx')
srcs = res.get('sources', [])
print(f"Sources count: {len(srcs)}")
for idx, s in enumerate(srcs):
    print(f"  {idx}: id={s.get('source_id')} db={s.get('database')} schema={s.get('schema')} table={s.get('table')} full={s.get('full_table_name')}")
