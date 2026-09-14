import openpyxl
import re
from excel_analyzer import (
    _clean_str, _norm_token, find_table_header,
    extract_control_identification, extract_control_schedule,
    parse_source_systems, parse_source_input_tables,
    parse_pre_execution_filters, parse_data_model,
    parse_business_rules, parse_buckets_and_kri_rules
)

wb = openpyxl.load_workbook('uploads/projects/67/Control23_Source_Logic_2.xlsx', data_only=True)
print("Workbook loaded successfully. Sheets:", wb.sheetnames)
