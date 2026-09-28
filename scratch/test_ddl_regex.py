import sys, os
sys.path.insert(0, os.path.abspath('.'))
import re
from target_logic_builder import _split_sql_statements

ddl_script = """CREATE SCHEMA IF NOT EXISTS "Unique";

-- ============================================================================
-- TARGET ARCHITECTURE ENTITIES (FROM HLA SPECIFICATION)
-- ============================================================================
-- Target Entity: order_ingest (Stage: Target Ingest Model | Strategy: Truncate & load)
CREATE TABLE IF NOT EXISTS "Unique".order_ingest (
    order_id2 VARCHAR(255),
    customer_id VARCHAR(255),
    order_date VARCHAR(255),
    net_amount VARCHAR(255)
);"""

raw_stmts = _split_sql_statements(ddl_script)
for stmt in raw_stmts:
    s = stmt.strip()
    # Strip SQL comments
    s_clean = re.sub(r'--.*$', '', s, flags=re.MULTILINE).strip()
    print('ORIGINAL STMT:', s[:60])
    print('  s.upper().startswith("CREATE TABLE"):', s.upper().startswith("CREATE TABLE"))
    print('  s_clean.upper().startswith("CREATE TABLE"):', s_clean.upper().startswith("CREATE TABLE"))
    tm = re.search(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
        r"((?:\"[^\"]+\"|\w+)(?:\.(?:\"[^\"]+\"|\w+))?)",
        s, re.IGNORECASE,
    )
    print('  Regex match:', tm.group(1) if tm else None)
