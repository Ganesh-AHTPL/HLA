import sys
sys.path.insert(0, '.')
from excel_analyzer import analyze_excel_specification
from target_logic_builder import generate_transformation_sql

analysis = analyze_excel_specification('uploads/projects/67/Control23_Source_Logic_2.xlsx')
target_schema = "ra_ctrl.ctrl_test"
target_dialect = "postgresql"
sources = analysis.get("sources") or []
rules = analysis.get("rules") or {}
mappings = analysis.get("mappings") or []
config_tables = analysis.get("config_tables") or []
control_overview = analysis.get("control_overview") or {}

sql = generate_transformation_sql(target_schema, target_dialect, sources, rules, mappings, config_tables, control_overview, analysis_data=analysis)
print("Transformation SQL length:", len(sql))
print("First 1000 characters:")
print(sql[:1000])
