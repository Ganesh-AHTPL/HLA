import sys
sys.path.insert(0, '.')
import openpyxl
import re
from excel_analyzer import (
    _clean_str, _norm_token, find_table_header,
    extract_control_identification, extract_control_schedule,
    parse_source_systems, parse_source_input_tables,
    parse_pre_execution_filters, parse_data_model,
    parse_business_rules, parse_buckets_and_kri_rules,
    parse_config_tables, parse_report_derivation_logic,
    build_attribute_mappings
)

wb = openpyxl.load_workbook('uploads/projects/67/Control23_Source_Logic_2.xlsx', data_only=True)

ws_sources = wb['Source Systems']
ws_mapping = wb['Attribute Mapping']
ws_rules = wb['Business Rules']
ws_kri = wb['Buckets & KRI Logic']
ws_model = wb['Data Model']
ws_reports = wb['Report Derivation Logic']
ws_config = wb['Config Tables']

sources, source_databases = parse_source_systems(ws_sources)
rules_data, column_catalog = parse_business_rules(ws_rules)
buckets, derived_fields = parse_buckets_and_kri_rules(ws_kri)
config_tables = parse_config_tables(ws_config)
reports = parse_report_derivation_logic(ws_reports)
data_model_tables = parse_data_model(ws_model)

print(f"Sources: {len(sources)}")
print(f"Rules: {len(rules_data.get('filter_rules', []))} filter, {len(rules_data.get('balance_rules', []))} balance, {len(rules_data.get('reconciliation_flows', []))} recon")
print(f"Buckets: {len(buckets)}")
print(f"Config tables: {len(config_tables)} with {sum(len(c.get('all_values', [])) for c in config_tables)} values")
print(f"Reports: {len(reports)} with {sum(len(r.get('attributes', [])) for r in reports)} attributes")
print(f"Data model: {len(data_model_tables)} tables")
