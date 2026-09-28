import os
import re

FORBIDDEN_IDENTIFIERS = [
    'order_header', 'order_item', 'customer_master', 'product_master',
    'order_ingest', 'order_flagged', 'work_item_current_run',
    'exception_summary', 'non_exception_summary', 'non_exception_details'
]

code_files = [
    'target_logic_builder.py',
    'app.py',
    'analyzer.py',
    'excel_analyzer.py',
    'backend/core/semantic_analyzer.py',
    'backend/core/generic_parser.py',
    'schema_migration_service.py'
]

violations = []

for file_path in code_files:
    if not os.path.exists(file_path):
        continue
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        in_multiline_comment = False
        for line_no, line in enumerate(f, 1):
            line_str = line.strip()
            if '"""' in line_str or "'''" in line_str:
                in_multiline_comment = not in_multiline_comment
                continue
            if in_multiline_comment:
                continue
            if line_str.startswith('#') or line_str.startswith('*') or line_str.startswith('//'):
                continue
            for identifier in FORBIDDEN_IDENTIFIERS:
                if re.search(r'[\"\'\`]' + re.escape(identifier) + r'[\"\'\`]', line_str):
                    violations.append((file_path, line_no, identifier, line_str))

print(f"Total violations found: {len(violations)}")
for v in violations:
    print(f"STATIC OBJECT REFERENCE DETECTED: {v[0]}:{v[1]} -> [{v[2]}] : {v[3]}")
