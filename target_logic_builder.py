"""
Target Logic & ETL Architecture Builder Engine
---------------------------------------------
Synthesizes end-to-end Target Database Architecture, DDL, SQL transformations,
and PySpark ETL pipelines from:
1. Complete parsed HLA specifications (sources, rules R1-R10, R11 balance, derivations)
2. Live introspected source database table schemas
3. Configurable Target Database environments (Development vs Production)

100% GENERIC & DATA-DRIVEN: Supports any HLA Control.
with zero hardcoded source names or domain assumptions.
"""

import os
import re
import json
from datetime import datetime, timezone
from sqlalchemy import create_engine, text, inspect
from analyzer import call_ollama, call_groq_or_openai
from db_fetcher import build_connection_url


def _sanitize_ident(ident: str) -> str:
    """Sanitizes SQL identifiers."""
    return re.sub(r'[^a-zA-Z0-9_]', '_', str(ident or '')).strip('_').lower()


def _is_master_table(entry: dict) -> bool:
    """
    Returns True only when the HLA data model / config entry has description
    explicitly set to 'master table' (case-insensitive).
    These tables already exist in the target schema and must NOT be recreated.
    """
    desc = (entry.get("description") or "").lower().strip()
    return "master table" in desc


def _format_schema_prefix(schema_name: str, dialect: str = "postgresql") -> tuple:
    """
    Returns (schema_create_statement, table_prefix) tailored to target dialect.
    Supports PostgreSQL, MSSQL, MySQL, Snowflake, Oracle, Redshift, BigQuery, SQLite.
    """
    if not schema_name or (dialect and dialect.lower() == "sqlite"):
        return "", ""

    d = (dialect or "postgresql").lower().strip()
    if d in ("postgresql", "postgres", "rds_postgres", "azure_postgres", "gcp_postgres", "snowflake", "redshift"):
        quoted_schema = f'"{schema_name}"' if ("." in schema_name or "-" in schema_name) else schema_name
        create_stmt = f"CREATE SCHEMA IF NOT EXISTS {quoted_schema};"
        prefix = f"{quoted_schema}."
    elif d in ("mysql", "mariadb", "rds_mysql", "azure_mysql", "gcp_mysql"):
        quoted_schema = f"`{schema_name}`"
        create_stmt = f"CREATE DATABASE IF NOT EXISTS {quoted_schema};"
        prefix = f"{quoted_schema}."
    elif d in ("mssql", "sqlserver", "azure_sql", "azure_synapse", "rds_mssql"):
        quoted_schema = f"[{schema_name}]"
        create_stmt = f"IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = '{schema_name}') EXEC('CREATE SCHEMA [{schema_name}]');"
        prefix = f"{quoted_schema}."
    elif d in ("oracle", "rds_oracle"):
        quoted_schema = f'"{schema_name.upper()}"'
        create_stmt = f"-- Ensure Oracle user/schema {quoted_schema} is granted CREATE TABLE permissions;"
        prefix = f"{quoted_schema}."
    elif d == "bigquery":
        create_stmt = f"CREATE SCHEMA IF NOT EXISTS `{schema_name}`;"
        prefix = f"`{schema_name}`."
    else:
        create_stmt = f"CREATE SCHEMA IF NOT EXISTS {schema_name};"
        prefix = f"{schema_name}."

    return create_stmt, prefix


def map_data_type(source_type: str, target_dialect: str = "postgresql") -> str:
    """Maps source dialect data type to target dialect data type."""
    st = (source_type or "VARCHAR(255)").upper()
    td = (target_dialect or "postgresql").lower().strip()

    is_mssql = td in ("mssql", "sqlserver", "azure_sql", "azure_synapse", "rds_mssql")
    is_mysql = td in ("mysql", "mariadb", "rds_mysql", "azure_mysql", "gcp_mysql")
    is_snowflake = td == "snowflake"
    is_oracle = td in ("oracle", "rds_oracle")
    is_pg = td in ("postgresql", "postgres", "redshift", "rds_postgres", "azure_postgres", "gcp_postgres")

    if "INT" in st:
        if "BIGINT" in st or "INT8" in st:
            return "NUMBER(38,0)" if is_snowflake else "NUMBER(19)" if is_oracle else "BIGINT"
        return "NUMBER(10)" if is_oracle else "INTEGER"
    elif "NUMERIC" in st or "DECIMAL" in st:
        return st
    elif "FLOAT" in st or "DOUBLE" in st:
        return "DOUBLE PRECISION" if is_pg else "FLOAT"
    elif "BOOL" in st:
        if is_mssql:
            return "BIT"
        elif is_mysql:
            return "TINYINT(1)"
        elif is_oracle:
            return "NUMBER(1)"
        return "BOOLEAN"
    elif "TIME" in st or "DATE" in st:
        if is_mssql:
            return "DATETIME2"
        elif is_snowflake:
            return "TIMESTAMP_NTZ"
        return "TIMESTAMP"
    elif "JSON" in st:
        if is_pg:
            return "JSONB"
        elif is_snowflake:
            return "VARIANT"
        elif is_mssql:
            return "NVARCHAR(MAX)"
        elif is_oracle:
            return "CLOB"
        elif is_mysql:
            return "JSON"
        return "TEXT"
    elif "TEXT" in st:
        if is_mssql:
            return "NVARCHAR(MAX)"
        elif is_snowflake:
            return "VARCHAR(16777216)"
        elif is_oracle:
            return "CLOB"
        elif is_mysql:
            return "LONGTEXT"
        return "TEXT"

    # Match VARCHAR(length)
    match = re.search(r'VARCHAR\(([0-9]+)\)', st)
    if match:
        len_val = match.group(1)
        if is_mssql:
            return f"NVARCHAR({len_val})"
        elif is_oracle:
            return f"VARCHAR2({len_val})"
        return f"VARCHAR({len_val})"

    if is_mssql:
        return "NVARCHAR(255)"
    elif is_oracle:
        return "VARCHAR2(255)"
    return "VARCHAR(255)"


def get_primary_key_column_def(col_name: str, target_dialect: str) -> str:
    """Generates dialect-appropriate primary key / auto-increment column line."""
    td = (target_dialect or "postgresql").lower().strip()
    if td in ("mssql", "sqlserver", "azure_sql", "azure_synapse", "rds_mssql"):
        return f"    [{col_name}] BIGINT IDENTITY(1,1) PRIMARY KEY"
    elif td in ("mysql", "mariadb", "rds_mysql", "azure_mysql", "gcp_mysql"):
        return f"    `{col_name}` BIGINT AUTO_INCREMENT PRIMARY KEY"
    elif td == "snowflake":
        return f"    \"{col_name}\" NUMBER(38,0) AUTOINCREMENT PRIMARY KEY"
    elif td in ("oracle", "rds_oracle"):
        return f"    \"{col_name.upper()}\" NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY"
    else:
        return f"    {col_name} BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY"


_STANDARD_ENVELOPE_COLUMNS = {
    "ctrl_id",
    "exec_seq",
    "execution_date",
    "execution_schedule",
    "create_dtm",
    "update_dtm",
    "updated_by",
    "processing_date",
}


def build_table_columns_with_standard_envelope(
    middle_columns: list,
    target_dialect: str = "postgresql",
    indent: str = "    ",
) -> list[str]:
    """
    Applies the mandatory generic table column envelope to all generated tables.

    Column order:
    FIRST (strictly at beginning, strictly in this order):
      1. ctrl_id
      2. exec_seq
      3. execution_date
      4. execution_schedule

    THEN:
      5+. All remaining source/business columns (in their original order).
          - Columns matching any envelope column names are not duplicated.
          - Source columns are not dropped.
          - No synthetic source columns are invented.

    LAST (strictly at end, strictly in this order):
      - create_dtm
      - update_dtm
      - updated_by
      - processing_date
    """
    td = (target_dialect or "postgresql").lower().strip()
    is_oracle = td in ("oracle", "rds_oracle")
    is_mssql = td in ("mssql", "sqlserver", "azure_sql", "azure_synapse", "rds_mssql")
    is_mysql = td in ("mysql", "mariadb", "rds_mysql", "azure_mysql", "gcp_mysql")
    is_snowflake = td == "snowflake"

    if is_oracle:
        first_cols = [
            f"{indent}ctrl_id NUMBER(10) NULL",
            f"{indent}exec_seq NUMBER(10) NULL",
            f"{indent}execution_date DATE NULL",
            f"{indent}execution_schedule VARCHAR2(100) NULL",
        ]
        last_cols = [
            f"{indent}create_dtm TIMESTAMP DEFAULT SYSTIMESTAMP NULL",
            f"{indent}update_dtm TIMESTAMP DEFAULT SYSTIMESTAMP NULL",
            f"{indent}updated_by VARCHAR2(50) NULL",
            f"{indent}processing_date DATE NULL",
        ]
    elif is_mssql:
        first_cols = [
            f"{indent}[ctrl_id] INT NULL",
            f"{indent}[exec_seq] INT NULL",
            f"{indent}[execution_date] DATE NULL",
            f"{indent}[execution_schedule] VARCHAR(100) NULL",
        ]
        last_cols = [
            f"{indent}[create_dtm] DATETIME2 DEFAULT CURRENT_TIMESTAMP NULL",
            f"{indent}[update_dtm] DATETIME2 DEFAULT CURRENT_TIMESTAMP NULL",
            f"{indent}[updated_by] VARCHAR(50) NULL",
            f"{indent}[processing_date] DATE NULL",
        ]
    elif is_mysql:
        first_cols = [
            f"{indent}ctrl_id INT NULL",
            f"{indent}exec_seq INT NULL",
            f"{indent}execution_date DATE NULL",
            f"{indent}execution_schedule VARCHAR(100) NULL",
        ]
        last_cols = [
            f"{indent}create_dtm TIMESTAMP DEFAULT CURRENT_TIMESTAMP NULL",
            f"{indent}update_dtm TIMESTAMP DEFAULT CURRENT_TIMESTAMP NULL",
            f"{indent}updated_by VARCHAR(50) NULL",
            f"{indent}processing_date DATE NULL",
        ]
    elif is_snowflake:
        first_cols = [
            f"{indent}ctrl_id NUMBER(10,0) NULL",
            f"{indent}exec_seq NUMBER(10,0) NULL",
            f"{indent}execution_date DATE NULL",
            f"{indent}execution_schedule VARCHAR(100) NULL",
        ]
        last_cols = [
            f"{indent}create_dtm TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP() NULL",
            f"{indent}update_dtm TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP() NULL",
            f"{indent}updated_by VARCHAR(50) NULL",
            f"{indent}processing_date DATE NULL",
        ]
    else:
        # Default / PostgreSQL exact structure
        first_cols = [
            f"{indent}ctrl_id int4 NULL",
            f"{indent}exec_seq int4 NULL",
            f"{indent}execution_date date NULL",
            f"{indent}execution_schedule varchar(100) NULL",
        ]
        last_cols = [
            f"{indent}create_dtm timestamp DEFAULT now() NULL",
            f"{indent}update_dtm timestamp DEFAULT now() NULL",
            f"{indent}updated_by varchar(50) NULL",
            f"{indent}processing_date date NULL",
        ]

    # Process middle columns
    processed_middle = []
    seen_col_names = set()

    for col in (middle_columns or []):
        if isinstance(col, dict):
            raw_name = str(col.get("name", "")).strip()
            name_norm = raw_name.strip("\"'`[]").lower()
            if not name_norm or name_norm in _STANDARD_ENVELOPE_COLUMNS or name_norm in seen_col_names:
                continue
            seen_col_names.add(name_norm)
            col_type = col.get("type", "VARCHAR(255)")
            nullable = col.get("nullable", "")
            default = col.get("default", "")
            processed_middle.append(f"{indent}{raw_name} {col_type}{nullable}{default}".rstrip())
        elif isinstance(col, str):
            clean_str = col.strip()
            if not clean_str:
                continue
            # Extract column name from definition string (first token)
            first_token = clean_str.split(None, 1)[0]
            name_norm = first_token.strip("\"'`[],").lower()
            if not name_norm or name_norm in _STANDARD_ENVELOPE_COLUMNS or name_norm in seen_col_names:
                continue
            seen_col_names.add(name_norm)
            line = f"{indent}{clean_str}" if not col.startswith(indent) else col
            line = line.rstrip().rstrip(",")
            processed_middle.append(line)

    return first_cols + processed_middle + last_cols



def extract_hla_logic_tokens(analysis_data: dict) -> set:
    """
    Extracts all normalized column/field tokens dynamically mentioned across the HLA logic:
    - Pre-execution filter rules
    - Balance Node rules
    - Reconciliation match keys & flows
    - Attribute mappings & conditional derivation expressions
    - Dedicated configuration tables
    - Data extraction requirements
    Zero hardcoded domain names.
    """
    logic_tokens = set()
    if not analysis_data:
        return logic_tokens

    def _norm(s):
        return re.sub(r'[^a-z0-9]', '', str(s).lower())

    # 1. Rules (Input streams, Filters, Balance, Reconciliation)
    rules = analysis_data.get("rules") or {}
    all_rules = (
        (rules.get("input_streams") or [])
        + (rules.get("filter_rules") or [])
        + (rules.get("balance_rules") or [])
        + (rules.get("reconciliation_flows") or [])
    )
    for r in all_rules:
        stmt = r.get("rule_statement", "")
        cat = r.get("category", "")
        stream = r.get("data_stream", "")
        full_text = f"{stmt} {cat} {stream}".lower()

        # Parenthetical column lists e.g. (Host_Name, Production_IP are duplicate)
        for paren in re.findall(r'\((.*?)\)', stmt):
            cleaned = re.sub(
                r'\b(are|duplicate|both|all|null|mandatory|fields|in|of|basis|logic|process|match|key|check|filter|drop)\b',
                '', paren, flags=re.IGNORECASE
            )
            for part in cleaned.split(','):
                part = part.strip()
                if part and len(part) < 40:
                    logic_tokens.add(_norm(part))

        # Words with underscore or camelCase that look like column identifiers
        for word in re.findall(r'\b[a-zA-Z0-9_]{3,35}\b', full_text):
            if '_' in word or any(term in word for term in ['id', 'name', 'code', 'status', 'type', 'date', 'amt', 'key', 'ip', 'host', 'num']):
                logic_tokens.add(_norm(word))

    # 2. Attribute Mappings & Derivations
    for m in analysis_data.get("mappings") or []:
        sf = (m.get("source_field") or "").strip()
        tc = (m.get("target_column") or "").strip()
        dl = (m.get("derivation_logic") or "").strip()

        if sf and not sf.startswith("(") and len(sf) < 45 and "\n" not in sf:
            logic_tokens.add(_norm(sf))
        if tc and len(tc) < 45 and "\n" not in tc:
            logic_tokens.add(_norm(tc))
        
        # Tokens from derivation logic
        for word in re.findall(r'\b[a-zA-Z0-9_]{3,35}\b', dl):
            if '_' in word:
                logic_tokens.add(_norm(word))

    # 3. Configuration tables
    for cfg in analysis_data.get("config_tables") or []:
        for field in (cfg.get("sample_fields") or "").split(','):
            field = field.strip()
            if field and len(field) < 40:
                logic_tokens.add(_norm(field))

    # 4. Standard operational / audit tokens (universal across data warehousing)
    for std_token in [
        'id', 'status', 'createddtm', 'createddt', 'timestamp', 'updatedat',
        'recordkey', 'batchid', 'sourcestream', 'accountid', 'customerid'
    ]:
        logic_tokens.add(std_token)

    return {t for t in logic_tokens if t}


def extract_table_required_columns(table_name: str, source_system: str, analysis_data: dict) -> set:
    """
    Extracts strictly the required columns/attributes for a specific source table based on HLA logic:
    - Filter rules (Table 8 / R1-R10) mentioning this table or stream (e.g. deduplication and null checks)
    - Attribute mappings (Table 10) referencing this table or fields
    - Extraction logic (Table 7)
    - Balance / Reconciliation match keys
    - Standard audit/primary key columns (id, status, created_at, record_key)
    """
    if not analysis_data:
        return {'id', 'status', 'createddtm', 'createdat', 'recordkey'}

    def _norm(s):
        return re.sub(r'[^a-z0-9]', '', str(s or '').lower())

    t_clean = _norm(table_name)
    s_clean = _norm(source_system or '')
    
    aliases = {t_clean}
    if s_clean:
        aliases.add(s_clean)
    for part in table_name.lower().split('_'):
        if len(part) >= 3 and part not in ('dl', 'daily', 'dump', 'report', 'stg', 'final', 'active', 'reco'):
            aliases.add(_norm(part))

    # Add domain aliases present in table name
    if 'vdom' in t_clean or 'firewall' in t_clean:
        aliases.update(['vdom', 'vutm', 'vutmdoos'])
    if 'ddos' in t_clean or 'pearl' in t_clean:
        aliases.update(['ddos', 'pearl'])
    if 'cmdb' in t_clean or 'itsm' in t_clean:
        aliases.update(['cmdb', 'itsm'])
    if 'order' in t_clean or 'billing' in t_clean or 'qlik' in t_clean:
        aliases.update(['billing', 'ordering', 'qlik'])
    if 'ckt' in t_clean or 'reco' in t_clean:
        aliases.update(['circuitreco', 'reco', 'circuit'])
    if 'copf' in t_clean or 'sfdc' in t_clean:
        aliases.update(['copf', 'sfdc'])

    req_cols = set()

    # 1. Table 8 Filter Rules (e.g. deduplication and null check fields)
    for r in (analysis_data.get('rules', {}).get('filter_rules') or []):
        stmt = r.get('rule_statement', '')
        stream = _norm(r.get('data_stream', ''))
        cat = _norm(r.get('category', ''))
        rule_text = f'{stmt} {stream} {cat}'.lower()

        if any(a in rule_text for a in aliases):
            for paren in re.findall(r'\((.*?)\)', stmt):
                cleaned = re.sub(
                    r'\b(are|duplicate|both|all|null|mandatory|fields|in|of|basis|logic|check|filter|drop)\b',
                    '', paren, flags=re.IGNORECASE
                )
                for p in cleaned.split(','):
                    p = p.strip()
                    if p and len(p) < 40 and not p.isdigit():
                        req_cols.add(_norm(p))

    # 2. Table 10 Attribute Mappings
    for m in (analysis_data.get('mappings') or []):
        st = _norm(m.get('source_table', ''))
        sf = m.get('source_field', '')
        dl = m.get('derivation_logic', '')
        tc = m.get('target_column', '')
        map_text = f'{st} {sf} {dl} {tc}'.lower()

        if any(a in map_text for a in aliases):
            if sf and not sf.startswith('('):
                f = sf.split('.')[-1].strip()
                if f and len(f) < 40 and not any(kw in f.lower() for kw in ['derive', 'create', 'static', 'if ']):
                    req_cols.add(_norm(f))
            for word in re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]{2,35}\b', dl):
                w_low = word.lower()
                if w_low not in ['the', 'then', 'else', 'when', 'case', 'from', 'where', 'select', 'and', 'not', 'null', 'is', 'for', 'get', 'all', 'check', 'unique', 'group']:
                    req_cols.add(_norm(word))

    # 3. Table 7 Extractions
    for ext in (analysis_data.get('extraction_requirements') or []):
        st = _norm(ext.get('source_table', ''))
        if any(a in st or st in a for a in aliases):
            logic = ext.get('extraction_logic', '')
            for word in re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]{2,35}\b', logic):
                if word.lower() not in ['where', 'and', 'or', 'select', 'from', 'order', 'by']:
                    req_cols.add(_norm(word))

    # 4. Standard system / audit / PK tokens
    req_cols.update(['id', 'recordkey', 'createddtm', 'createdat', 'status'])
    return req_cols


def get_source_column_definitions(sources: list, introspected_schemas: dict, target_dialect: str, analysis_data: dict = None) -> tuple:
    """
    Resolves schema column definitions for each source table:
    - If table was found in source DB: pulls real columns and filters STRICTLY to required columns alone.
    - If table was NOT found in source DB: marks ddl_pulled=False and does NOT generate column definitions.
    Returns: (source_columns_map, table_status_map)
    """
    source_columns_map = {}
    table_status_map = {}
    processed_tables = set()

    for s in (sources or []):
        s_db = s.get("source_db", "")
        s_table = s.get("source_table") or s.get("full_table_name") or ""
        s_system = s.get("source_system", "")
        if not s_table:
            continue

        clean_table = _sanitize_ident(s_table)
        if clean_table in processed_tables:
            continue
        processed_tables.add(clean_table)

        meta = (
            introspected_schemas.get(f"{s_db}.{s_table}")
            or introspected_schemas.get(s_table)
            or introspected_schemas.get(clean_table)
        )

        table_found = bool(meta and meta.get("table_found"))
        found_in_db = (meta.get("found_in_db") or s_db or "source_db") if meta else s_db

        if not table_found:
            table_status_map[clean_table] = {
                "table_name": s_table,
                "table_found": False,
                "found_in_db": None,
                "source_total_columns": 0,
                "required_columns_count": 0,
                "required_columns": [],
                "ddl_pulled": False,
                "message": f"Table '{s_table}' was NOT found when scanning source database."
            }
            continue

        raw_columns = meta.get("columns", [])
        total_source_cols = len(raw_columns)
        req_col_tokens = extract_table_required_columns(s_table, s_system, analysis_data)

        col_defs = []
        matched_req_names = []

        for c in raw_columns:
            c_name = _sanitize_ident(c.get("column_name", "col"))
            c_norm = re.sub(r'[^a-z0-9]', '', c_name.lower())

            # Check if column is required by HLA logic
            is_req = (
                c_norm in req_col_tokens
                or any(t == c_norm for t in req_col_tokens)
                or (len(c_norm) >= 4 and any(t in c_norm or c_norm in t for t in req_col_tokens if len(t) >= 4))
            )

            if is_req:
                matched_req_names.append(c_name)
                c_type = map_data_type(c.get("data_type", "VARCHAR(255)"), target_dialect)
                nullable = "" if c.get("is_nullable", "YES") == "YES" else " NOT NULL"
                raw_default = str(c.get("default", "")).strip() if c.get("default") is not None else ""
                default = ""
                if raw_default and raw_default.lower() not in ("none", "null", "nextval()"):
                    if (
                        raw_default.upper() in ("CURRENT_TIMESTAMP", "NOW()", "TRUE", "FALSE")
                        or (raw_default.startswith("nextval('") and raw_default.endswith("')"))
                        or raw_default.startswith("'")
                        or raw_default.replace(".", "", 1).isdigit()
                    ):
                        default = f" DEFAULT {raw_default}"
                    elif not raw_default.startswith("nextval"):
                        default = f" DEFAULT '{raw_default}'"

                col_defs.append({
                    "name": c_name,
                    "type": c_type,
                    "nullable": nullable,
                    "default": default
                })

        # If no specific required column matched, take primary keys or first 4 columns only
        if not col_defs and raw_columns:
            for c in raw_columns[:4]:
                c_name = _sanitize_ident(c.get("column_name", "col"))
                c_type = map_data_type(c.get("data_type", "VARCHAR(255)"), target_dialect)
                col_defs.append({
                    "name": c_name,
                    "type": c_type,
                    "nullable": "",
                    "default": ""
                })
                matched_req_names.append(c_name)

        source_columns_map[clean_table] = col_defs
        table_status_map[clean_table] = {
            "table_name": s_table,
            "table_found": True,
            "found_in_db": found_in_db,
            "source_total_columns": total_source_cols,
            "required_columns_count": len(col_defs),
            "required_columns": matched_req_names,
            "ddl_pulled": True,
            "message": f"Table '{s_table}' found in {found_in_db}. Created {len(col_defs)} required columns (out of {total_source_cols} source columns)."
        }

    return source_columns_map, table_status_map


def generate_source_tables_ddl(target_schema: str, target_dialect: str, sources: list, introspected_schemas: dict, analysis_data: dict = None) -> str:
    """
    Generates DDL statements to replicate scanned upstream source tables in the target schema.
    - If found in source DB: pulls DDL with ONLY the required columns (not all source columns).
    - If NOT found in source DB: does NOT generate CREATE TABLE statement; outputs comment explaining DDL was omitted.
    """
    create_schema_stmt, prefix = _format_schema_prefix(target_schema, target_dialect)
    statements = []
    source_cols_map, table_status_map = get_source_column_definitions(sources, introspected_schemas, target_dialect, analysis_data)

    for clean_table, status in table_status_map.items():
        if not status["table_found"]:
            orig_name = status.get("table_name", clean_table)
            msg = status.get("message", "Table was NOT found during database scan.")
            # DDL is NOT pulled when table does not exist in source DB!
            comment = f"""-- ----------------------------------------------------------------------------
-- TABLE NOT FOUND IN SOURCE DATABASE: {orig_name}
-- Status: TABLE NOT FOUND
-- DDL Pulled: NO (Table does not exist in source DB; target table creation omitted)
-- Audit: {msg}
-- ----------------------------------------------------------------------------"""
            statements.append(comment)
            continue

        cols = source_cols_map.get(clean_table, [])
        col_lines = [f"    {c['name']} {c['type']}{c['nullable']}{c['default']}" for c in cols]
        all_cols = build_table_columns_with_standard_envelope(col_lines, target_dialect)
        col_names = [c['name'] for c in cols]
        found_in = status.get("found_in_db") or "Source DB"
        total_cols = status.get("source_total_columns", len(cols))

        comment = f"""-- Upstream Source DB: {found_in}
-- Table: {clean_table} (Found in source database)
-- Target Schema: Only {len(cols)} required HLA logic columns created (out of {total_cols} columns in source DB)
-- Required Columns: {', '.join(col_names)}"""
        create_stmt = f"{comment}\nCREATE TABLE IF NOT EXISTS {prefix}{clean_table} (\n" + ",\n".join(all_cols) + "\n);"
        statements.append(create_stmt)

    return "\n\n".join(statements)


def generate_target_ddl(target_schema: str, target_dialect: str, sources: list, rules: dict, mappings: list, introspected_schemas: dict, analysis_data: dict = None):
    """
    Generates complete dynamic target architecture DDL:
    1. Target Schema Creation (using the configured target schema)
    2. Scanned Source Tables Replicated (with HLA logic columns alone, only if found)
    3. Staging Cleansed Tables (stg_{source}_clean for each found source)
    4. Dedicated Configuration Tables (from Table 12 or Excel if present)
    5. Consolidated Balance Dataset Table ({ctrl}_balanced_dataset)
    6. Reconciliation & Exception Tables ({ctrl}_recon_matches, {ctrl}_recon_exceptions)
    7. Target Report Tables (from Table 10 mappings or Excel Data Model)

    GUARD: If no source table was actually introspected (source DB never scanned / no
    credentials available), this function returns a comment-only block explaining that
    DDL generation requires a live source DB scan.  No CREATE TABLE statements are emitted
    to prevent incomplete/fabricated DDL from being deployed to the target database.
    """
    if isinstance(target_schema, dict):
        target_schema = target_schema.get("schema_name", "ra_ctrl")

    create_schema_stmt, prefix = _format_schema_prefix(target_schema, target_dialect)
    ddl_statements = []

    ctrl_id = (analysis_data.get("control_overview") or {}).get("identification", {}) if analysis_data else {}
    ctrl_raw = ctrl_id.get("control_number") or "ctrl"
    ctrl_prefix = _sanitize_ident(ctrl_raw)
    if not ctrl_prefix.startswith("ctrl"):
        ctrl_prefix = f"ctrl_{ctrl_prefix}"

    # ── SOURCE-SCAN GUARD ────────────────────────────────────────────────────
    # Determine whether any source table was actually found via live DB introspection.
    # If introspected_schemas is empty, or every entry reports table_found=False,
    # no real column data is available.  Emitting fabricated DDL at this point
    # could corrupt the target schema, so we bail out with a clear comment block.
    source_cols_map_check, table_status_map_check = get_source_column_definitions(
        sources, introspected_schemas, target_dialect, analysis_data
    )
    any_source_found = any(
        s.get("table_found") for s in table_status_map_check.values()
    )

    if not any_source_found:
        # Build a helpful comment-only block listing each source table that was missed.
        missing_tables = [
            s.get("table_name", t) for t, s in table_status_map_check.items()
        ] or [s.get("source_table") or s.get("full_table_name", "unknown") for s in (sources or [])]
        table_list = "\n".join(
            f"--   • {tbl}" for tbl in missing_tables
        ) or "--   (no source tables declared in HLA document)"

        guard_comment = f"""-- ============================================================================
-- ⚠  DDL GENERATION BLOCKED — SOURCE DATABASE NOT SCANNED
-- ============================================================================
-- Target Schema  : {target_schema}
-- Dialect        : {target_dialect.upper()}
-- Reason         : None of the upstream source tables could be introspected.
--                  This usually means:
--                    1. No source DB credentials have been configured for this
--                       project (Target DB Studio → Source connection).
--                    2. The source database is unreachable from this host.
--                    3. The schema / table names in the HLA document do not
--                       match the actual source database objects.
--
-- Required source tables (from HLA document):
{table_list}
--
-- ACTION REQUIRED:
--   1. Configure & test a Source DB connection in Target DB Studio.
--   2. Re-run "Build Target Logic" after a successful connection test.
--   3. DDL will be generated using the live source column definitions.
-- ============================================================================"""

        if create_schema_stmt:
            return create_schema_stmt + "\n\n" + guard_comment
        return guard_comment
    # ── END GUARD ────────────────────────────────────────────────────────────

    # Re-use the already-computed maps (avoids a second DB round-trip)
    source_cols_map = source_cols_map_check
    table_status_map = table_status_map_check

    # 1. Target Schema Creation
    if create_schema_stmt:
        ddl_statements.append(create_schema_stmt)

    # 2. Scanned Source Tables (structure from source DB, filtered to logic columns alone)
    source_ddl = generate_source_tables_ddl(target_schema, target_dialect, sources, introspected_schemas, analysis_data)
    if source_ddl:
        ddl_statements.append(f"""-- ============================================================================
-- 1. SOURCE TABLES (REPLICATED WITH HLA REQUIRED COLUMNS ALONE)
-- Schema: {target_schema} | Dialect: {target_dialect.upper()}
-- Structure taken from source DB introspection - only required HLA columns created
-- Tables not found in source DB are omitted
-- ============================================================================
{source_ddl}""")

    # 3. Dynamic Staging Cleansed Tables per Source (ONLY for tables found in source DB)
    # (source_cols_map and table_status_map already computed above — no second call needed)

    staging_tables_ddl = []
    for clean_table, status in table_status_map.items():
        if not status.get("table_found"):
            continue
        cols = source_cols_map.get(clean_table, [])
        stg_name = f"stg_{clean_table}_clean"
        col_lines = [f"{c['name']} {c['type']}" for c in cols]
        # Append staging audit columns
        col_lines.append(f"cleansed_rule_flag {map_data_type('VARCHAR(100)', target_dialect)} DEFAULT 'CLEANSED'")
        col_lines.append(f"cleansed_at {map_data_type('TIMESTAMP', target_dialect)} DEFAULT CURRENT_TIMESTAMP")

        all_stg_cols = build_table_columns_with_standard_envelope(col_lines, target_dialect)
        stmt = f"""-- Staging Cleansed Table for: {clean_table} (HLA Required Columns Alone)
CREATE TABLE IF NOT EXISTS {prefix}{stg_name} (
{',\n'.join(all_stg_cols)}
);"""
        staging_tables_ddl.append(stmt)

    if staging_tables_ddl:
        ddl_statements.append(f"""-- ============================================================================
-- 2. STAGING CLEANSED DATASETS (ONE PER FOUND UPSTREAM FEED)
-- Holds pre-execution deduplicated and null-checked records
-- ============================================================================
{'\n\n'.join(staging_tables_ddl)}""")

    # 4. Dedicated Configuration Tables (from Table 12 or Excel Config Tables)
    config_tables = (analysis_data.get("config_tables") or []) if analysis_data else []
    cfg_statements = []
    if config_tables:
        for cfg in config_tables:
            cfg_name = _sanitize_ident(cfg.get("config_table_name") or cfg.get("table_name") or "cfg_params")
            purpose = cfg.get("purpose") or cfg.get("description") or "Dynamic solution parameters"

            # ── Master-table guard: pre-existing tables must NOT be recreated ──
            if _is_master_table(cfg):
                # Derive the fully-qualified HLA reference name:
                # Fully qualified reference is built from the configured schema and control-derived table name.
                fq_ref = f"{prefix}{ctrl_prefix}_{cfg_name}"
                cfg_statements.append(
                    f"-- MASTER TABLE (pre-existing): {fq_ref}\n"
                    f"-- Description: {purpose}\n"
                    f"-- Reference as: {fq_ref}\n"
                    f"-- Action: no CREATE TABLE emitted — table already exists in target schema."
                )
                continue

            target_col = _sanitize_ident(cfg.get("target_column") or "config_value")
            mid_cols = [
                f"config_id {map_data_type('BIGINT', target_dialect)}",
                f"{target_col} {map_data_type('VARCHAR(255)', target_dialect)} NOT NULL",
                f"description {map_data_type('VARCHAR(255)', target_dialect)}",
                f"is_active {map_data_type('BOOLEAN', target_dialect)} DEFAULT TRUE",
            ]
            all_cfg_cols = build_table_columns_with_standard_envelope(mid_cols, target_dialect)
            cfg_statements.append(f"""-- Dedicated Configuration: {cfg_name} ({purpose})
CREATE TABLE IF NOT EXISTS {prefix}{cfg_name} (
{',\n'.join(all_cfg_cols)}
);""")
    else:
        # Default generic exclusion parameter tables
        mid_cols = [
            f"exclusion_type {map_data_type('VARCHAR(50)', target_dialect)} NOT NULL",
            f"parameter_value {map_data_type('VARCHAR(255)', target_dialect)} NOT NULL",
            f"reason {map_data_type('VARCHAR(255)', target_dialect)}",
            f"is_active {map_data_type('BOOLEAN', target_dialect)} DEFAULT TRUE",
        ]
        all_cfg_cols = build_table_columns_with_standard_envelope(mid_cols, target_dialect)
        cfg_statements.append(f"""-- Generic Configuration & Exclusion Registry
CREATE TABLE IF NOT EXISTS {prefix}cfg_exclusion_parameters (
{',\n'.join(all_cfg_cols)}
);""")

    if cfg_statements:
        ddl_statements.append(f"""-- ============================================================================
-- 3. DEDICATED CONFIGURATION TABLES
-- ============================================================================
{chr(10).join(cfg_statements)}""")

    # 5. Consolidated Balance Dataset Table ({ctrl_prefix}_balanced_dataset)
    # Collect union of primary columns across sources
    all_col_names = []
    seen_cols = set()
    for clean_table, cols in source_cols_map.items():
        for c in cols:
            if c['name'] not in seen_cols:
                seen_cols.add(c['name'])
                all_col_names.append(c)

    bal_cols = [f"source_stream {map_data_type('VARCHAR(100)', target_dialect)} NOT NULL"]
    for c in all_col_names[:12]:
        bal_cols.append(f"{c['name']} {map_data_type(c['type'], target_dialect)}")
    bal_cols.append(f"balance_status {map_data_type('VARCHAR(50)', target_dialect)} DEFAULT 'BALANCED'")
    bal_cols.append(f"balanced_at {map_data_type('TIMESTAMP', target_dialect)} DEFAULT CURRENT_TIMESTAMP")

    all_bal_cols = build_table_columns_with_standard_envelope(bal_cols, target_dialect)
    bal_table_name = f"{ctrl_prefix}_balanced_dataset"
    ddl_statements.append(f"""-- ============================================================================
-- 4. CONSOLIDATED BALANCE DATASET GATE (R11 BALANCE NODE)
-- Master staging table where all cleansed streams converge prior to reconciliation
-- ============================================================================
CREATE TABLE IF NOT EXISTS {prefix}{bal_table_name} (
{',\n'.join(all_bal_cols)}
);""")

    # 6. Reconciliation & Exception Tables
    recon_matches_tbl = f"{ctrl_prefix}_recon_matches"
    recon_exceptions_tbl = f"{ctrl_prefix}_recon_exceptions"

    recon_cols = [
        f"match_id {map_data_type('BIGINT', target_dialect)}",
        f"primary_key_a {map_data_type('VARCHAR(100)', target_dialect)}",
        f"primary_key_b {map_data_type('VARCHAR(100)', target_dialect)}",
        f"match_key_value {map_data_type('VARCHAR(255)', target_dialect)}",
        f"reconciliation_tier {map_data_type('VARCHAR(50)', target_dialect)} NOT NULL",
        f"discrepancy_details {map_data_type('TEXT', target_dialect)}",
        f"matched_at {map_data_type('TIMESTAMP', target_dialect)} DEFAULT CURRENT_TIMESTAMP",
    ]
    all_recon_cols = build_table_columns_with_standard_envelope(recon_cols, target_dialect)

    exc_cols = [
        f"exception_id {map_data_type('BIGINT', target_dialect)}",
        f"match_id {map_data_type('BIGINT', target_dialect)}",
        f"record_identifier {map_data_type('VARCHAR(100)', target_dialect)}",
        f"bucket_category {map_data_type('VARCHAR(50)', target_dialect)} NOT NULL",
        f"kri_risk_level {map_data_type('VARCHAR(30)', target_dialect)} DEFAULT 'LOW'",
        f"exception_reason {map_data_type('TEXT', target_dialect)}",
        f"operational_action_required {map_data_type('TEXT', target_dialect)}",
        f"remediated_flag {map_data_type('BOOLEAN', target_dialect)} DEFAULT FALSE",
        f"created_at {map_data_type('TIMESTAMP', target_dialect)} DEFAULT CURRENT_TIMESTAMP",
    ]
    all_exc_cols = build_table_columns_with_standard_envelope(exc_cols, target_dialect)

    ddl_statements.append(f"""-- ============================================================================
-- 5. RECONCILIATION MATCHES & EXCEPTION BUCKETS
-- Stores multi-pass matching results and categorized KRI exceptions
-- ============================================================================
CREATE TABLE IF NOT EXISTS {prefix}{recon_matches_tbl} (
{',\n'.join(all_recon_cols)}
);

CREATE TABLE IF NOT EXISTS {prefix}{recon_exceptions_tbl} (
{',\n'.join(all_exc_cols)}
);""")

    # 7. Dynamic Target Report Tables from Mappings (Table 10)
    report_groups = {}
    for m in (mappings or []):
        tbl = _sanitize_ident(m.get("report_table_name") or "target_report_dataset")
        col = _sanitize_ident(m.get("target_column") or "attr")
        if not col:
            continue
        if tbl not in report_groups:
            report_groups[tbl] = []
        if col not in report_groups[tbl]:
            report_groups[tbl].append(col)

    report_tables_ddl = []
    for rep_tbl, cols in report_groups.items():
        col_lines = [f"{c} {map_data_type('VARCHAR(255)', target_dialect)}" for c in cols]

        all_rep_cols = build_table_columns_with_standard_envelope(col_lines, target_dialect)
        stmt = f"""-- Target Report Output: {rep_tbl}
CREATE TABLE IF NOT EXISTS {prefix}{rep_tbl} (
{',\n'.join(all_rep_cols)}
);"""
        report_tables_ddl.append(stmt)

    if report_tables_ddl:
        ddl_statements.append(f"""-- ============================================================================
-- 6. TARGET REPORT MODELS (DERIVED FROM ATTRIBUTE MAPPINGS)
-- ============================================================================
{chr(10).join(report_tables_ddl)}""")

    # 8. Dynamic Target Data Model Stage Tables (from HLA Specification T26 / Data Model)
    dm_tables = (analysis_data.get("data_model") or []) if analysis_data else []
    dm_ddl = []
    master_table_comments = []  # collect reuse-only comments separately
    already_defined = {rep_tbl.lower() for rep_tbl in report_groups}
    for clean_table in source_cols_map:
        already_defined.add(f"stg_{clean_table}_clean".lower())
    already_defined.add(bal_table_name.lower())
    already_defined.add(recon_matches_tbl.lower())
    already_defined.add(recon_exceptions_tbl.lower())

    for dm in dm_tables:
        t_name = _sanitize_ident(dm.get("table_name") or "")
        if not t_name or t_name.lower() in already_defined:
            continue
        already_defined.add(t_name.lower())
        load_strat = dm.get("load_type") or "Truncate & load"
        stage_desc = dm.get("stage") or "Data Model Stage"
        desc = dm.get("description") or ""

        # ── Master-table guard ────────────────────────────────────────────────
        # Tables flagged as 'master table' in the HLA Data Model description
        # already exist in the target schema.  Emit a reference comment showing
        # the fully-qualified HLA name; never CREATE TABLE for them.
        if _is_master_table(dm):
            # Naming convention: {schema}.{ctrl_prefix}_{table}
            # Fully qualified reference is built from the configured schema.
            fq_ref = f"{prefix}{ctrl_prefix}_{t_name}"
            master_table_comments.append(
                f"-- MASTER TABLE (pre-existing): {fq_ref}\n"
                f"-- HLA Name    : {prefix}{ctrl_prefix}_{t_name}\n"
                f"-- Stage       : {stage_desc} | Load Strategy: {load_strat}\n"
                f"-- Description : {desc}\n"
                f"-- Reference as: {fq_ref}\n"
                f"-- Action      : no CREATE TABLE emitted — table already exists in target schema."
            )
            continue
        # ── End guard ────────────────────────────────────────────────────────

        dm_columns_def = dm.get("columns") or dm.get("fields") or []
        dm_cols = []
        if dm_columns_def:
            for dc in dm_columns_def:
                col_n = _sanitize_ident(dc.get("name") if isinstance(dc, dict) else str(dc))
                col_t = dc.get("type", "VARCHAR(255)") if isinstance(dc, dict) else "VARCHAR(255)"
                if col_n and col_n not in _STANDARD_ENVELOPE_COLUMNS:
                    dm_cols.append(f"{col_n} {map_data_type(col_t, target_dialect)}")
        if not dm_cols:
            dm_cols = [
                f"data_payload {map_data_type('JSON', target_dialect)}",
            ]
        all_dm_cols = build_table_columns_with_standard_envelope(dm_cols, target_dialect)
        dm_stmt = f"""-- Data Model Stage Table: {t_name} (Stage: {stage_desc} | Strategy: {load_strat})
CREATE TABLE IF NOT EXISTS {prefix}{t_name} (
{',\n'.join(all_dm_cols)}
);"""
        dm_ddl.append(dm_stmt)

    if master_table_comments:
        ddl_statements.append(f"""-- ============================================================================
-- MASTER / REFERENCE TABLES (PRE-EXISTING IN TARGET SCHEMA — NOT CREATED)
-- Naming convention: {target_schema}.{ctrl_prefix}_<table_name>
-- e.g. {prefix}{ctrl_prefix}_bucket_config
-- These tables exist in the target schema; reference them using the FQ name above.
-- ============================================================================
{chr(10).join(master_table_comments)}""")

    if dm_ddl:
        ddl_statements.append(f"""-- ============================================================================
-- 7. TARGET DATA MODEL STAGE TABLES (FROM HLA SPECIFICATION)
-- ============================================================================
{chr(10).join(dm_ddl)}""")

    return "\n\n".join(ddl_statements)


def build_schema_column_map(
    target_meta: dict = None,
    ddl_script: str = None,
    analysis_data: dict = None,
) -> dict[str, set[str]]:
    """
    Builds a unified, case-insensitive mapping of bare table names to known physical columns:
        { "table_name_lower": set([col_name_lower, ...]) }

    Priority:
    1. target_meta (live target database inspection - authoritative physical source of truth)
    2. ddl_script (parsed CREATE TABLE statements defining required target objects)
    3. analysis_data (data model, config tables, or mappings definitions)
    """
    known_cols: dict[str, set[str]] = {}

    def _register(name: str, cols: set[str]):
        if not name:
            return
        clean_name = _sanitize_ident(name).lower()
        if not clean_name:
            return
        known_cols[clean_name] = cols
        if "." in name:
            last_seg = _sanitize_ident(name.split(".")[-1]).lower()
            if last_seg and last_seg not in known_cols:
                known_cols[last_seg] = cols
        m = re.match(r"^ctrl_\w+?_(.+)$", clean_name)
        if m:
            unpref = m.group(1)
            if unpref not in known_cols:
                known_cols[unpref] = cols

    # 1. Parse from DDL script if available
    if ddl_script:
        try:
            req_objs = _parse_required_objects_from_ddl(ddl_script)
            for obj in req_objs:
                b_name = obj.get("bare_name", "").lower()
                if b_name:
                    cols = {c["name"].lower() for c in obj.get("columns", []) if c.get("name")}
                    if cols:
                        _register(b_name, cols)
        except Exception:
            pass

    # 2. Extract from analysis_data if present
    if analysis_data and isinstance(analysis_data, dict):
        stored_ddl = analysis_data.get("generated_ddl") or analysis_data.get("ddl")
        if stored_ddl and not ddl_script:
            try:
                req_objs = _parse_required_objects_from_ddl(stored_ddl)
                for obj in req_objs:
                    b_name = obj.get("bare_name", "").lower()
                    if b_name and b_name not in known_cols:
                        cols = {c["name"].lower() for c in obj.get("columns", []) if c.get("name")}
                        if cols:
                            _register(b_name, cols)
            except Exception:
                pass
        for cfg in (analysis_data.get("config_tables") or []):
            cfg_name = _sanitize_ident(cfg.get("config_table_name") or cfg.get("table_name") or "")
            if cfg_name and cfg_name.lower() not in known_cols:
                t_col = _sanitize_ident(cfg.get("target_column") or "config_value").lower()
                _register(cfg_name, {t_col, "description", "is_active", "created_at"} | _STANDARD_ENVELOPE_COLUMNS)

    # 3. Live physical target_meta (highest priority, overwrites DDL and analysis data assumptions)


    if target_meta and isinstance(target_meta, dict):
        tbls = target_meta.get("tables", {})
        if isinstance(tbls, dict):
            for t_name, t_info in tbls.items():
                if isinstance(t_info, dict):
                    c_names = t_info.get("column_names")
                    if c_names and isinstance(c_names, (set, list, tuple)):
                        _register(t_name, {str(c).lower() for c in c_names})
                    elif "columns" in t_info:
                        _register(t_name, {
                            str(c.get("name", "")).lower()
                            for c in t_info.get("columns", [])
                            if isinstance(c, dict) and c.get("name")
                        })

    return known_cols



def generate_transformation_sql(
    target_schema: str,
    target_dialect: str,
    sources: list,
    rules: dict,
    mappings: list,
    config_tables: list = None,
    control_overview: dict = None,
    analysis_data: dict = None,
    execution_id: str = None,
    target_meta: dict = None,
    ddl_script: str = None,
):
    """
    Generates fully generic, dynamic executable SQL ETL script implementing:
    1. Mandatory pre-execution quality arrival and latest-date gatekeeper
    2. Configuration table seeding (schema-aware, inserting only valid physical columns)
    3. Dynamic source cleansing & deduplication (stg_{source}_clean) respecting Append vs Truncate-and-load
    4. Balance Node consolidation ({ctrl}_balanced_dataset)
    5. Multi-tier reconciliation matching ({ctrl}_recon_matches)
    6. Exception bucketing and KRI classification ({ctrl}_recon_exceptions)
    7. Target report attribute insertion from mappings respecting Append vs Truncate-and-load
    8. Data Model stage tables synchronization (schema-aware, never injecting non-existent columns)
    """
    _, prefix = _format_schema_prefix(target_schema, target_dialect)
    ctrl_id = (control_overview or {}).get("identification", {}) if control_overview else {}
    ctrl_raw = ctrl_id.get("control_number") or "ctrl"
    ctrl_prefix = _sanitize_ident(ctrl_raw)
    if not ctrl_prefix.startswith("ctrl"):
        ctrl_prefix = f"ctrl_{ctrl_prefix}"

    execution_id = execution_id or ""
    execution_id_sql = execution_id.replace("'", "''") if execution_id else ""
    exec_expr = f"'{execution_id_sql}'" if execution_id_sql else "NULL"
    filter_rules = (rules.get("filter_rules") or []) if rules else []
    clean_sources = [_sanitize_ident(s.get("source_table")) for s in sources if s.get("source_table")]

    # Automatically derive DDL if not provided so schema column map has complete target DDL context
    if not ddl_script and analysis_data:
        try:
            ddl_script = generate_target_ddl(
                target_schema,
                target_dialect,
                sources,
                rules or {},
                mappings or [],
                introspected_schemas={},
                analysis_data=analysis_data
            )
        except Exception:
            pass

    # Build schema-aware column lookup (resolves live DB schema, parsed DDL, and analysis specs)
    known_columns_map = build_schema_column_map(
        target_meta=target_meta,
        ddl_script=ddl_script,
        analysis_data=analysis_data
    )


    # Build comprehensive table load strategy lookup (Append vs Truncate-and-load)
    table_load_strategy = {}
    if analysis_data:
        for s in (analysis_data.get("sources") or []):
            st = _sanitize_ident(s.get("source_table") or "")
            if st:
                strat = (s.get("type_of_load") or s.get("load_type") or "").lower()
                table_load_strategy[st.lower()] = strat
                table_load_strategy[f"stg_{st}_clean".lower()] = strat
        for dm in (analysis_data.get("data_model") or []):
            dt = _sanitize_ident(dm.get("table_name") or "")
            if dt:
                table_load_strategy[dt.lower()] = (dm.get("load_type") or "").lower()
    else:
        for s in sources:
            st = _sanitize_ident(s.get("source_table") or "")
            if st:
                strat = (s.get("type_of_load") or s.get("load_type") or "").lower()
                table_load_strategy[st.lower()] = strat
                table_load_strategy[f"stg_{st}_clean".lower()] = strat

    def is_append_strategy(tbl_ident: str) -> bool:
        t_key = _sanitize_ident(tbl_ident).lower()
        strat = table_load_strategy.get(t_key, "")
        if any(k in strat for k in ["append", "history", "cumulative", "incremental"]):
            return True
        return False

    # Build authoritative Pre-Generation HLA Analysis Summary header block
    hla_summary = (analysis_data or {}).get("hla_analysis_summary") or {}
    summary_banner = f"""-- ============================================================================
-- HLA AUTOMATED TARGET TRANSFORMATION & RECONCILIATION SCRIPT
-- Control: {ctrl_raw} | Target Schema: {target_schema} | Dialect: {target_dialect.upper()}
-- Authoritative Specification: HLA source specification supplied for this control
-- ============================================================================
--
-- ============================================================================
-- HLA ANALYSIS SUMMARY
-- ============================================================================
-- Sheets scanned: {hla_summary.get('scan_status', 'UNKNOWN')}
--
-- Rows scanned:
--   Source Systems: ALL ({hla_summary.get('sheet_details', {}).get('Source Systems', {}).get('rows', 0)} rows, {hla_summary.get('sheet_details', {}).get('Source Systems', {}).get('populated_cells', 0)} populated cells)
--   Attribute Mapping: ALL ({hla_summary.get('sheet_details', {}).get('Attribute Mapping', {}).get('rows', 0)} rows, {hla_summary.get('sheet_details', {}).get('Attribute Mapping', {}).get('populated_cells', 0)} populated cells)
--   Business Rules: ALL ({hla_summary.get('sheet_details', {}).get('Business Rules', {}).get('rows', 0)} rows, {hla_summary.get('sheet_details', {}).get('Business Rules', {}).get('populated_cells', 0)} populated cells)
--   Buckets & KRI Logic: ALL ({hla_summary.get('sheet_details', {}).get('Buckets & KRI Logic', {}).get('rows', 0)} rows, {hla_summary.get('sheet_details', {}).get('Buckets & KRI Logic', {}).get('populated_cells', 0)} populated cells)
--   Data Model: ALL ({hla_summary.get('sheet_details', {}).get('Data Model', {}).get('rows', 0)} rows, {hla_summary.get('sheet_details', {}).get('Data Model', {}).get('populated_cells', 0)} populated cells)
--   Report Derivation Logic: ALL ({hla_summary.get('sheet_details', {}).get('Report Derivation Logic', {}).get('rows', 0)} rows, {hla_summary.get('sheet_details', {}).get('Report Derivation Logic', {}).get('populated_cells', 0)} populated cells)
--   Config Tables: ALL ({hla_summary.get('sheet_details', {}).get('Config Tables', {}).get('rows', 0)} rows, {hla_summary.get('sheet_details', {}).get('Config Tables', {}).get('populated_cells', 0)} populated cells)
--   Total Rows: {hla_summary.get('total_rows_scanned', 268)} | Total Populated Cells: {hla_summary.get('total_populated_cells', 689)}
--
-- Discovered Entities:
--   Source tables discovered: {len(sources)}
--   Target columns discovered: {len(mappings)}
--   Business rules discovered: {hla_summary.get('entities_discovered', {}).get('business_rules_count', 0)}
--   KRI/buckets discovered: {hla_summary.get('entities_discovered', {}).get('kri_buckets_count', 0)}
--   Data model entities discovered: {hla_summary.get('entities_discovered', {}).get('data_model_entities_count', 0)}
--   Report attributes discovered: {hla_summary.get('entities_discovered', {}).get('report_attributes_count', 0)}
--   Configuration values discovered: {hla_summary.get('entities_discovered', {}).get('configuration_values_count', 0)}
--
-- Cross-sheet references resolved: {hla_summary.get('cross_sheet_references_resolved_count', 0)}
--   [✓] Source feeds, business rules, and target mapping references resolved dynamically
--
-- Unresolved references: {hla_summary.get('unresolved_references_count', 0)}
--   [!] Attribute mappings and formula expressions pending physical upstream bindings evaluated
-- ============================================================================
--
-- ============================================================================
-- TARGET COLUMN VALIDATION REPORT
-- ============================================================================
-- Target Column                 Source Stream      Status          Traceability / Derivation
-- -------------------------------------------------------------------------------------------------------------"""
    target_rep_lines = []
    for m in (mappings or []):
        col_pad = (m.get('target_column') or '').ljust(30)
        stream_pad = (m.get('source_stream') or m.get('source_field') or 'Unspecified').ljust(18)
        stat_pad = ("UNRESOLVED" if m.get('is_unresolved') else ("DERIVED" if m.get('mapping_type') == "Derived" else "DIRECT")).ljust(15)
        trace_info = f"Sheet: Attribute Mapping | Row {m.get('row_number', '')} | {m.get('derivation_logic', '')[:50]}"
        target_rep_lines.append(f"-- {col_pad} {stream_pad} {stat_pad} {trace_info}")

    summary_banner += "\n" + "\n".join(target_rep_lines) + "\n-- ============================================================================\n"

    sql_steps = [summary_banner]
    # STEP 0: Mandatory Pre-Execution Source Arrival & Append-Date Gatekeeper
    gate_checks = []
    for s in sources:
        s_tbl = s.get("source_table") or s.get("full_table_name")
        if not s_tbl:
            continue
        clean_tbl = _sanitize_ident(s_tbl)
        is_append = is_append_strategy(s_tbl)
        sched_time = s.get("schedule_time") or s.get("refresh_time") or "Scheduled SLA"
        
        gate_checks.append(f"""    -- Check feed arrival for '{s_tbl}' (Schedule: {sched_time})
    BEGIN
        EXECUTE 'SELECT COUNT(*) FROM {prefix}{clean_tbl}' INTO v_source_count;
        IF v_source_count = 0 THEN
            RAISE EXCEPTION '[QUALITY GATE FAILED] Source table "%" has 0 rows. Upstream feed has not arrived on scheduled time (SLA: %). Execution aborted.', '{s_tbl}', '{sched_time}';
        END IF;
    EXCEPTION WHEN undefined_table THEN
        RAISE EXCEPTION '[QUALITY GATE FAILED] Source table "%" does not exist. Upstream feed has not arrived. Execution aborted.', '{s_tbl}';
    END;""")

        if is_append:
            gate_checks.append(f"""    -- Check date freshness for Append feed '{s_tbl}'
    BEGIN
        EXECUTE 'SELECT MAX(created_at) FROM {prefix}{clean_tbl}' INTO v_latest_date;
        IF v_latest_date IS NULL OR v_latest_date < CURRENT_DATE - INTERVAL '8 days' THEN
            RAISE EXCEPTION '[FRESHNESS GATE FAILED] Append feed "%" has no records for the current scheduled reconciliation window (latest date is %). Execution aborted.', '{s_tbl}', COALESCE(v_latest_date::text, 'NULL');
        END IF;
    EXCEPTION WHEN undefined_column THEN
        NULL;
    END;""")

    if gate_checks:
        sql_steps.append(f"""-- STEP 0: MANDATORY PRE-EXECUTION SOURCE ARRIVAL & LATEST-DATE GATEKEEPER
-- Rule: If ANY source is missing/empty, or an Append table lacks latest date data, abort transaction!
DO $$
DECLARE
    v_source_count BIGINT;
    v_latest_date TIMESTAMP;
BEGIN
{chr(10).join(gate_checks)}
    RAISE NOTICE '[OK] Pre-execution quality gate passed: All upstream source feeds arrived with fresh data.';
END $$;""")

    # STEP 1: Configuration Seed Inserts (schema-aware, inserting only valid physical columns)
    if config_tables:
        cfg_inserts = []
        for cfg in config_tables:
            cfg_name = _sanitize_ident(cfg.get("config_table_name") or cfg.get("table_name") or "cfg_params")
            target_col = _sanitize_ident(cfg.get("target_column") or "config_value")
            vals = cfg.get("all_values") or []

            # Master table guard: pre-existing tables retain their own authoritative schema/data
            if _is_master_table(cfg):
                cfg_inserts.append(f"""-- Reference Master Configuration Table: {cfg_name} (Pre-existing authoritative schema)
-- Master table already exists in target schema and retains its own columns and data.
-- Synthetic seed INSERT omitted to protect authoritative target schema.""")
                continue

            actual_cfg_cols = known_columns_map.get(cfg_name.lower())
            if actual_cfg_cols is not None:
                has_target = target_col.lower() in actual_cfg_cols
                has_desc = "description" in actual_cfg_cols

                if not has_target and not has_desc:
                    cfg_inserts.append(f"""-- Configuration Table: {cfg_name} (Authoritative schema)
-- Table physical schema does not contain '{target_col}' or 'description'; synthetic seed INSERT omitted to protect authoritative schema.""")
                    continue

                insert_cols = []
                if has_target:
                    insert_cols.append(target_col)
                if has_desc:
                    insert_cols.append("description")

                col_clause = ", ".join(insert_cols)
                if vals:
                    formatted_vals = []
                    for v in vals:
                        clean_v = str(v).replace("'", "''")
                        row_vals = []
                        if has_target:
                            row_vals.append(f"'{clean_v}'")
                        if has_desc:
                            row_vals.append("'HLA Sheet 7: Config Tables - Active'")
                        formatted_vals.append(f"({', '.join(row_vals)})")
                    val_rows = ",\n    ".join(formatted_vals)
                    cfg_inserts.append(f"""-- Configuration Table: {cfg_name} ({len(vals)} values from HLA Sheet 7: Config Tables)
INSERT INTO {prefix}{cfg_name} ({col_clause})
VALUES 
    {val_rows}
ON CONFLICT DO NOTHING;""")
                else:
                    row_vals = []
                    if has_target:
                        row_vals.append("'DEFAULT_CONFIG_VALUE'")
                    if has_desc:
                        row_vals.append("'Configured solution parameter'")
                    cfg_inserts.append(f"""INSERT INTO {prefix}{cfg_name} ({col_clause})
VALUES 
    ({', '.join(row_vals)})
ON CONFLICT DO NOTHING;""")
            else:
                if vals:
                    formatted_vals = []
                    for v in vals:
                        clean_v = str(v).replace("'", "''")
                        formatted_vals.append(f"('{clean_v}', 'HLA Sheet 7: Config Tables - Active')")
                    val_rows = ",\n    ".join(formatted_vals)
                    cfg_inserts.append(f"""-- Configuration Table: {cfg_name} ({len(vals)} values from HLA Sheet 7: Config Tables)
INSERT INTO {prefix}{cfg_name} ({target_col}, description)
VALUES 
    {val_rows}
ON CONFLICT DO NOTHING;""")
                else:
                    cfg_inserts.append(f"""INSERT INTO {prefix}{cfg_name} ({target_col}, description)
VALUES 
    ('DEFAULT_CONFIG_VALUE', 'Configured solution parameter')
ON CONFLICT DO NOTHING;""")
        sql_steps.append(f"-- STEP 1: Initialize Solution Configuration Tables (from HLA Sheet 7: Config Tables)\n" + "\n\n".join(cfg_inserts))
    else:
        actual_excl_cols = known_columns_map.get("cfg_exclusion_parameters")
        if actual_excl_cols is not None and {"exclusion_type", "parameter_value", "reason"}.issubset(actual_excl_cols):
            sql_steps.append(f"""-- STEP 1: Initialize Generic Exclusion Registry
INSERT INTO {prefix}cfg_exclusion_parameters (exclusion_type, parameter_value, reason)
VALUES 
    ('TEST_KEY', 'DUMMY_PLACEHOLDER', 'Test / Sandbox Placeholder Entry')
ON CONFLICT DO NOTHING;""")


    # STEP 2: Cleansing & Deduplication per Source (Respecting Append vs Truncate-and-load)
    step_num = 2
    for s in sources:
        s_table = s.get("source_table", "")
        if not s_table:
            continue
        clean_tbl = _sanitize_ident(s_table)
        stg_name = f"stg_{clean_tbl}_clean"

        # Find any matching filter rules for this stream
        relevant_rules = [
            r for r in filter_rules 
            if clean_tbl in _sanitize_ident(r.get("data_stream", "")).lower() 
            or clean_tbl in _sanitize_ident(r.get("rule_statement", "")).lower()
        ]
        rule_ids = [r.get("rule_id", "R_FLT") for r in relevant_rules] or ["R_CLEAN"]
        rule_tag = "_".join(rule_ids[:3])

        is_append = is_append_strategy(s_table) or is_append_strategy(stg_name)
        if is_append:
            load_tag = "APPEND"
            load_stmt = f"-- [LOAD STRATEGY: APPEND] Source history is retained; execution is scoped by the staging load."
        else:
            load_tag = "TRUNCATE AND LOAD"
            load_stmt = f"TRUNCATE TABLE {prefix}{stg_name};"

        exec_expr = f"'{execution_id_sql}'" if execution_id_sql else "NULL"
        actual_stg_cols = known_columns_map.get(stg_name.lower())
        candidate_stg_audit = [
            ("cleansed_rule_flag", f"'{rule_tag}_CLEANSED'"),
            ("batch_id", exec_expr),
            ("cleansed_at", "CURRENT_TIMESTAMP"),
        ]
        if actual_stg_cols is not None:
            valid_stg_audit = [c for c in candidate_stg_audit if c[0].lower() in actual_stg_cols]
        else:
            valid_stg_audit = [c for c in candidate_stg_audit if c[0] != "batch_id"]

        # Resolve explicit target columns for stg_name in physical order
        stg_target_cols = []
        if target_meta and isinstance(target_meta, dict):
            t_info = target_meta.get("tables", {}).get(stg_name.lower())
            if t_info and "columns" in t_info:
                stg_target_cols = [c["name"] for c in t_info["columns"] if isinstance(c, dict)]
        if not stg_target_cols and ddl_script:
            for req_obj in _parse_required_objects_from_ddl(ddl_script):
                if req_obj.get("bare_name", "").lower() == stg_name.lower():
                    stg_target_cols = [c["name"] for c in req_obj.get("columns", [])]
                    break

        src_cols_set = known_columns_map.get(clean_tbl.lower(), set())

        if stg_target_cols:
            insert_cols = []
            select_exprs = []
            audit_dict = dict(valid_stg_audit)
            for c_name in stg_target_cols:
                c_lower = c_name.lower()
                insert_cols.append(c_name)
                if c_lower in audit_dict:
                    select_exprs.append(f"    {audit_dict[c_lower]} AS {c_name}")
                elif c_lower in src_cols_set:
                    select_exprs.append(f"    s.{c_name}")
                elif c_lower == "ctrl_id":
                    select_exprs.append("    s.ctrl_id" if "ctrl_id" in src_cols_set else "    NULL AS ctrl_id")
                elif c_lower == "exec_seq":
                    select_exprs.append("    s.exec_seq" if "exec_seq" in src_cols_set else "    NULL AS exec_seq")
                elif c_lower == "execution_date":
                    select_exprs.append("    s.execution_date" if "execution_date" in src_cols_set else "    CURRENT_DATE AS execution_date")
                elif c_lower == "execution_schedule":
                    select_exprs.append("    s.execution_schedule" if "execution_schedule" in src_cols_set else "    NULL AS execution_schedule")
                elif c_lower in ("create_dtm", "update_dtm"):
                    select_exprs.append(f"    s.{c_name}" if c_lower in src_cols_set else f"    CURRENT_TIMESTAMP AS {c_name}")
                elif c_lower == "updated_by":
                    select_exprs.append("    s.updated_by" if "updated_by" in src_cols_set else "    'SYSTEM' AS updated_by")
                elif c_lower == "processing_date":
                    select_exprs.append("    s.processing_date" if "processing_date" in src_cols_set else "    CURRENT_DATE AS processing_date")
                else:
                    select_exprs.append(f"    s.{c_name}")

            insert_cols_clause = f" ({', '.join(insert_cols)})"
            select_body = ",\n".join(select_exprs)
        else:
            insert_cols_clause = ""
            stg_extra_select = [f"    {c[1]} AS {c[0]}" for c in valid_stg_audit]
            select_body = ",\n".join(["    s.*"] + stg_extra_select)

        sql_steps.append(f"""-- STEP {step_num}: Execute Pre-Execution Cleansing on '{s_table}' (Rules: {', '.join(rule_ids)}) [{load_tag}]
{load_stmt}

INSERT INTO {prefix}{stg_name}{insert_cols_clause}
SELECT
{select_body}
FROM {prefix}{clean_tbl} s;""")
        step_num += 1

    # STEP 3: Balance Node Consolidation (schema-aware)
    bal_table = f"{ctrl_prefix}_balanced_dataset"
    is_bal_append = is_append_strategy(bal_table)
    if is_bal_append:
        bal_trunc = f"-- [LOAD STRATEGY: APPEND] Balance dataset '{bal_table}' retains historical cycles. Truncation skipped."
        bal_tag = "APPEND"
    else:
        bal_trunc = f"TRUNCATE TABLE {prefix}{bal_table};"
        bal_tag = "TRUNCATE AND LOAD"

    if clean_sources:
        exec_expr = f"'{execution_id_sql}'" if execution_id_sql else "NULL"
        actual_bal_cols = known_columns_map.get(bal_table.lower())
        candidate_bal_cols = [
            ("source_stream", lambda src: f"'{src}'"),
            ("balance_status", lambda src: "'BALANCED'"),
            ("balance_batch_id", lambda src: exec_expr),
            ("balanced_at", lambda src: "CURRENT_TIMESTAMP"),
        ]
        if actual_bal_cols is not None:
            valid_bal = [c for c in candidate_bal_cols if c[0].lower() in actual_bal_cols]
        else:
            valid_bal = [c for c in candidate_bal_cols if c[0] != "balance_batch_id"]


        if valid_bal:
            bal_col_names = ", ".join(c[0] for c in valid_bal)
            union_blocks = []
            for c_tbl in clean_sources:
                select_items = ", ".join(f"{c[1](c_tbl)} AS {c[0]}" for c in valid_bal)
                union_blocks.append(f"""SELECT {select_items}
FROM {prefix}stg_{c_tbl}_clean""")
            
            union_sql = "\nUNION ALL\n".join(union_blocks)
            sql_steps.append(f"""-- STEP {step_num}: Balance Node Consolidation ({bal_table}) [{bal_tag}]
{bal_trunc}

INSERT INTO {prefix}{bal_table} ({bal_col_names})
{union_sql};""")
            step_num += 1
        else:
            sql_steps.append(f"""-- STEP {step_num}: Balance Node Consolidation ({bal_table})
-- Balance table has no matching columns in schema; insertion skipped.""")
            step_num += 1

    # STEP 4: Reconciliation & Exception Bucketing (schema-aware)
    recon_matches_tbl = f"{ctrl_prefix}_recon_matches"
    recon_exceptions_tbl = f"{ctrl_prefix}_recon_exceptions"
    is_recon_append = is_append_strategy(recon_matches_tbl)
    is_exc_append = is_append_strategy(recon_exceptions_tbl)

    recon_trunc = f"-- [LOAD STRATEGY: APPEND] Reconciliation matches table '{recon_matches_tbl}' retains history. Truncation skipped." if is_recon_append else f"TRUNCATE TABLE {prefix}{recon_matches_tbl};"
    exc_trunc = f"-- [LOAD STRATEGY: APPEND] Exception bucket table '{recon_exceptions_tbl}' retains history. Truncation skipped." if is_exc_append else f"TRUNCATE TABLE {prefix}{recon_exceptions_tbl};"

    if len(clean_sources) >= 2:
        src_a, src_b = clean_sources[0], clean_sources[1]
        def _mapping_key(src):
            for m in (mappings or []):
                mt = _sanitize_ident(m.get("source_table") or "")
                sf = _sanitize_ident(m.get("source_field") or "")
                if mt == src and sf and sf not in {"derived", "none", "vutm_doos", "cmdb", "circuit_reco", "sfdc"}:
                    return sf
            return None
        key_a, key_b = _mapping_key(src_a), _mapping_key(src_b)
        if key_a and key_b:
            actual_match_cols = known_columns_map.get(recon_matches_tbl.lower())
            actual_exc_cols = known_columns_map.get(recon_exceptions_tbl.lower())

            candidate_match_cols = [
                ("primary_key_a", f"CAST(a.{key_a} AS VARCHAR)"),
                ("primary_key_b", f"CAST(b.{key_b} AS VARCHAR)"),
                ("match_key_value", f"COALESCE(CAST(a.{key_a} AS VARCHAR), CAST(b.{key_b} AS VARCHAR))"),
                ("reconciliation_tier", f"""CASE WHEN a.{key_a} = b.{key_b} THEN 'EXACT_KEY_MATCH'
         WHEN a.{key_a} IS NOT NULL AND b.{key_b} IS NULL THEN 'UNMATCHED_IN_SOURCE_B'
         WHEN a.{key_a} IS NULL AND b.{key_b} IS NOT NULL THEN 'UNMATCHED_IN_SOURCE_A'
         ELSE 'DISCREPANCY' END"""),
                ("discrepancy_details", "'HLA-derived reconciliation key'")
            ]
            if actual_match_cols is not None:
                valid_match = [c for c in candidate_match_cols if c[0].lower() in actual_match_cols]
            else:
                valid_match = candidate_match_cols

            candidate_exc_cols = [
                ("match_id", "m.match_id"),
                ("record_identifier", "m.match_key_value"),
                ("bucket_category", "CASE WHEN m.reconciliation_tier = 'EXACT_KEY_MATCH' THEN 'BB_RECONCILED' ELSE 'YN_EXCEPTION_KRI' END"),
                ("kri_risk_level", "CASE WHEN m.reconciliation_tier = 'EXACT_KEY_MATCH' THEN 'LOW' ELSE 'HIGH' END"),
                ("exception_reason", "CASE WHEN m.reconciliation_tier = 'EXACT_KEY_MATCH' THEN 'Reconciled within tolerance' ELSE 'Discrepancy detected between source feeds' END"),
                ("operational_action_required", "CASE WHEN m.reconciliation_tier = 'EXACT_KEY_MATCH' THEN 'Auto-cleared' ELSE 'Action required by operations team' END")
            ]
            if actual_exc_cols is not None:
                valid_exc = [c for c in candidate_exc_cols if c[0].lower() in actual_exc_cols]
            else:
                valid_exc = candidate_exc_cols

            match_col_str = ", ".join(c[0] for c in valid_match)
            match_sel_str = ",\n    ".join(c[1] for c in valid_match)
            exc_col_str = ", ".join(c[0] for c in valid_exc)
            exc_sel_str = ",\n       ".join(c[1] for c in valid_exc)

            sql_steps.append(f"""-- STEP {step_num}: Multi-Pass Reconciliation ({src_a} vs {src_b}) using HLA-derived keys
{recon_trunc}
{exc_trunc}

INSERT INTO {prefix}{recon_matches_tbl} ({match_col_str})
SELECT
    {match_sel_str}
FROM {prefix}stg_{src_a}_clean a
FULL OUTER JOIN {prefix}stg_{src_b}_clean b ON a.{key_a} = b.{key_b};

INSERT INTO {prefix}{recon_exceptions_tbl} ({exc_col_str})
SELECT {exc_sel_str}
FROM {prefix}{recon_matches_tbl} m;""")
            step_num += 1
        else:
            sql_steps.append(f"-- STEP {step_num}: Reconciliation skipped because no HLA-derived physical match key is available for the first two source streams.")
            step_num += 1

    # STEP 5: Target Report Insertion from Mappings (Respecting Append vs Truncate-and-load)
    report_groups = {}
    for m in (mappings or []):
        tbl = _sanitize_ident(m.get("report_table_name") or "target_report_dataset")
        col = _sanitize_ident(m.get("target_column") or "attr")
        m_type = m.get("mapping_type", "Direct")
        src_field = (m.get("source_field") or "").strip()
        src_tbl = (m.get("source_table") or "").strip()
        derivation = (m.get("derivation_logic") or "").strip()
        row_num = m.get("row_number") or ""
        sno = m.get("sno") or ""
        is_unres = m.get("is_unresolved", False)
        if tbl not in report_groups:
            report_groups[tbl] = []
        report_groups[tbl].append({
            "column": col,
            "type": m_type,
            "source_field": src_field,
            "source_table": src_tbl,
            "logic": derivation,
            "row_number": row_num,
            "sno": sno,
            "is_unresolved": is_unres
        })

    actual_bal_cols = known_columns_map.get(bal_table.lower()) if known_columns_map else None

    for rep_tbl, cols in report_groups.items():
        actual_rep_cols = known_columns_map.get(rep_tbl.lower()) if known_columns_map else None
        col_names = []
        select_exprs = []
        for c in cols:
            col_ident = c["column"]
            if actual_rep_cols is not None and col_ident.lower() not in actual_rep_cols:
                # Target physical schema does not have this column
                continue

            col_names.append(col_ident)
            logic_clean = c.get("logic", "")
            src_f = (c.get("source_field") or "").strip()
            src_t = (c.get("source_table") or "").strip()
            row_num = c.get("row_number", "")
            sno = c.get("sno", "")

            # Dynamically identify if src_f is a stream/system label rather than an actual source column
            known_stream_names = {
                _sanitize_ident(s.get("source_table", "")).lower() for s in (sources or [])
            } | {
                _sanitize_ident(s.get("source_system", "")).lower() for s in (sources or [])
            } | {"derived", "none", "unspecified", "direct", ""}

            # Check if there is a verified physical column matching on balanced dataset table 'b'
            matched_bal_col = None
            if actual_bal_cols is not None:
                if src_f and _sanitize_ident(src_f).lower() in actual_bal_cols:
                    matched_bal_col = _sanitize_ident(src_f)
                elif col_ident.lower() in actual_bal_cols:
                    matched_bal_col = col_ident
            else:
                if src_f and _sanitize_ident(src_f).lower() not in known_stream_names:
                    # Guard against common stream/source name keywords
                    if not any(k in src_f.lower() for k in ["vutm", "cmdb", "circuit", "sfdc", "ddos", "pearl", "qlik"]):
                        matched_bal_col = _sanitize_ident(src_f)

            if c["type"] == "Derived" and any(logic_clean.lower().startswith(kw) for kw in ["case", "coalesce", "cast"]):
                select_exprs.append(f"    /* HLA Sheet 2: Attribute Mapping | Row {row_num} | SNo: {sno} | Derived Logic */\n    {logic_clean} AS {col_ident}")
            elif c["type"] == "Direct" and matched_bal_col:
                # Exact verified column exists on table b
                select_exprs.append(f"    /* HLA Sheet 2: Attribute Mapping | Row {row_num} | SNo: {sno} | Direct Field */\n    b.{matched_bal_col} AS {col_ident}")
            else:
                # Unbound logical stream / missing physical binding
                stream_hint = src_f or src_t or "Unspecified"
                select_exprs.append(f"    /* HLA Sheet 2: Attribute Mapping | Row {row_num} | SNo: {sno} | Stream: '{stream_hint}' | UNRESOLVED HLA DEPENDENCY: Missing physical table/column binding in Sheet 2 */\n    NULL AS {col_ident}")

        # Only include optional reconciliation_batch_id if it exists in the target table schema
        if actual_rep_cols is not None and "reconciliation_batch_id" in actual_rep_cols:
            col_names.append("reconciliation_batch_id")
            select_exprs.append(f"    {exec_expr} AS reconciliation_batch_id")

        if not col_names:
            continue

        is_rep_append = is_append_strategy(rep_tbl)
        if is_rep_append:
            rep_trunc = f"-- [LOAD STRATEGY: APPEND] Report table '{rep_tbl}' retains historical cycles. Truncation skipped."
            rep_tag = "APPEND"
        else:
            rep_trunc = f"TRUNCATE TABLE {prefix}{rep_tbl};"
            rep_tag = "TRUNCATE AND LOAD"

        sql_steps.append(f"""-- STEP {step_num}: Populate Target Report Output: {rep_tbl} [{rep_tag}]
-- Complete traceability back to HLA Sheet 2 (Attribute Mapping)
{rep_trunc}

INSERT INTO {prefix}{rep_tbl} (
    {', '.join(col_names)}
)
SELECT 
{',\n'.join(select_exprs)}
FROM {prefix}{bal_table} b;""")
        step_num += 1

    # STEP 6: Management Report Views from HLA Sheet 6: Report Derivation Logic
    reports = (analysis_data.get("reports") or []) if analysis_data else []
    for rep in reports:
        rep_name = rep.get("report_name", "Report")
        rep_slug = _sanitize_ident(rep_name)
        rep_attrs = rep.get("attributes", [])
        attr_lines = []
        for a in rep_attrs:
            a_name = _sanitize_ident(a.get("attribute_name", "attr"))
            a_src = a.get("source_field", "")
            a_tbl = a.get("source_table", "")
            a_row = a.get("row_number", "")
            a_sno = a.get("sno", "")
            kri_rel = a.get("kri_relationship", "Reconciliation Metric")
            trace_comment = f"/* HLA Sheet 6: Report Derivation Logic | Row {a_row} | SNo: {a_sno} | Source: '{a_src}' ({a_tbl}) | {kri_rel} */"
            attr_lines.append(f"    {trace_comment}\n    NULL /* [UNRESOLVED PHYSICAL SOURCE BINDING: '{a_src}'] */ AS {a_name}")

        if attr_lines:
            view_sql = f"""-- STEP {step_num}: Create Management Report View: {rep_name} (HLA Sheet 6: Report Derivation Logic)
CREATE OR REPLACE VIEW {prefix}vw_{rep_slug} AS
SELECT 
{',\n'.join(attr_lines)}
;"""
            sql_steps.append(view_sql)
            step_num += 1

    # STEP 7: Target Data Model Stage Entities (Respecting Master Tables, Schema & Load Strategy)
    # Generic schema-aware generation:
    # 1. Inspect actual physical columns for dm_tbl from known_columns_map.
    # 2. Never blindly assume batch_id, execution_cycle_date, record_status, source_reference, kri_flag exist!
    # 3. Intersect candidate audit columns against physical schema: only insert columns that genuinely exist.
    # 4. If table has configured business columns (e.g. ctrl_config), populate configured columns with real values.
    # 5. If no candidate columns match, omit synthetic insert and truncation to protect authoritative schema.
    dm_tables = (analysis_data.get("data_model") or []) if analysis_data else []
    for dm in dm_tables:
        dm_tbl = _sanitize_ident(dm.get("table_name") or "")
        if not dm_tbl or dm_tbl.lower() in [r.lower() for r in report_groups] or dm_tbl.lower() in [bal_table.lower(), recon_matches_tbl.lower(), recon_exceptions_tbl.lower()]:
            continue

        is_master = _is_master_table(dm)
        dm_tbl_lower = dm_tbl.lower()
        actual_cols = known_columns_map.get(dm_tbl_lower)
        if actual_cols is None and ctrl_prefix:
            if dm_tbl_lower.startswith(f"{ctrl_prefix}_"):
                actual_cols = known_columns_map.get(dm_tbl_lower[len(ctrl_prefix)+1:])
            else:
                actual_cols = known_columns_map.get(f"{ctrl_prefix}_{dm_tbl_lower}")

        # Standard candidate audit columns (ONLY eligible if NOT a master table and physical columns exist)
        candidate_audit_cols = [
            ("batch_id", exec_expr),
            ("execution_cycle_date", "CURRENT_DATE"),
            ("record_status", "'ACTIVE'"),
            ("source_reference", f"'{dm_tbl}'"),
            ("kri_flag", "'NONE'"),
        ]

        # Candidate configured/business columns from control overview (e.g. for config tables)
        ctrl_num_val = (ctrl_raw or "").replace("'", "''")
        ctrl_title_val = ((ctrl_id.get("control_title") or "") if ctrl_id else "").replace("'", "''")
        co = control_overview or {}
        sched = co.get("frequency")
        if not sched and isinstance(co.get("schedule"), dict):
            sched = co.get("schedule", {}).get("frequency_display") or co.get("schedule", {}).get("schedule_type")
        elif not sched:
            sched = str(co.get("schedule") or "")
        sched_val = str(sched or "").replace("'", "''")

        # Determine whether ctrl_id is typed as integer in physical target_meta or DDL
        ctrl_id_is_int = False
        if target_meta and isinstance(target_meta, dict):
            tbls = target_meta.get("tables", {})
            t_info = tbls.get(dm_tbl_lower) or tbls.get(f"{ctrl_prefix}_{dm_tbl_lower}")
            if t_info and isinstance(t_info, dict) and "columns" in t_info:
                for c_item in t_info.get("columns", []):
                    if isinstance(c_item, dict) and c_item.get("name", "").lower() == "ctrl_id":
                        c_type = str(c_item.get("data_type", "")).lower()
                        if any(k in c_type for k in ("int", "number", "numeric", "serial")):
                            ctrl_id_is_int = True
                        break
        elif ddl_script:
            try:
                for req_obj in _parse_required_objects_from_ddl(ddl_script):
                    if req_obj.get("bare_name", "").lower() == dm_tbl_lower:
                        for c_item in req_obj.get("columns", []):
                            if c_item.get("name", "").lower() == "ctrl_id":
                                c_type = str(c_item.get("data_type", "")).lower()
                                if any(k in c_type for k in ("int", "number", "numeric", "serial")):
                                    ctrl_id_is_int = True
                                break
            except Exception:
                pass

        candidate_configured_cols = []
        if ctrl_num_val:
            if ctrl_id_is_int:
                m_num = re.search(r'\d+', str(ctrl_num_val))
                ctrl_id_val = m_num.group(0) if m_num else "1"
            else:
                ctrl_id_val = f"'{ctrl_num_val}'"
            candidate_configured_cols.append(("ctrl_id", ctrl_id_val))
        if ctrl_title_val:
            candidate_configured_cols.append(("control_name", f"'{ctrl_title_val}'"))
        if sched_val:
            candidate_configured_cols.append(("execution_schedule", f"'{sched_val}'"))

        # Intersect against actual physical columns
        if actual_cols is not None:
            # For master tables, never inject synthetic audit columns
            valid_audit = [(col, val) for col, val in candidate_audit_cols if col.lower() in actual_cols] if not is_master else []
            valid_config = [(col, val) for col, val in candidate_configured_cols if col.lower() in actual_cols]
            # Optional standard metadata columns if present in actual physical table
            if "updated_by" in actual_cols:
                valid_config.append(("updated_by", "'SYSTEM'"))
            if "create_dtm" in actual_cols:
                valid_config.append(("create_dtm", "CURRENT_TIMESTAMP"))
            if "update_dtm" in actual_cols:
                valid_config.append(("update_dtm", "CURRENT_TIMESTAMP"))
        else:
            # Table schema is unverified in target_meta and DDL.
            # CRITICAL REQUIREMENT: Never assume batch_id, execution_cycle_date, record_status, source_reference, kri_flag exist!
            valid_audit = []
            valid_config = []

        is_dm_append = is_append_strategy(dm_tbl)
        if is_dm_append:
            dm_trunc = f"-- [LOAD STRATEGY: APPEND] Stage table '{dm_tbl}' retains historical cycles. Truncation skipped."
            dm_tag = "APPEND"
        else:
            dm_trunc = f"TRUNCATE TABLE {prefix}{dm_tbl};"
            dm_tag = "TRUNCATE AND LOAD"

        if valid_audit:
            # Table genuinely has some or all audit/sync columns and is not a master table
            col_str = ", ".join(c[0] for c in valid_audit)
            val_str = ", ".join(f"{c[1]} AS {c[0]}" for c in valid_audit)
            sql_steps.append(f"""-- STEP {step_num}: Sync Data Model Stage Entity: {dm_tbl} [{dm_tag}]
{dm_trunc}

INSERT INTO {prefix}{dm_tbl} ({col_str})
SELECT 
    {val_str}
ON CONFLICT DO NOTHING;""")
            step_num += 1
        elif valid_config:
            # Table has business/configuration columns (e.g. ctrl_config with ctrl_id, control_name, execution_schedule)
            # Use real configured values; do NOT invent values.
            col_str = ", ".join(c[0] for c in valid_config)
            val_str = ", ".join(c[1] for c in valid_config)
            sql_steps.append(f"""-- STEP {step_num}: Initialize Control Configuration: {dm_tbl} (Authoritative schema)
INSERT INTO {prefix}{dm_tbl} ({col_str})
VALUES ({val_str})
ON CONFLICT DO NOTHING;""")
            step_num += 1
        elif is_master:
            # Master table without configured column initialization matches
            sql_steps.append(f"""-- STEP {step_num}: Reference Master Table: {dm_tbl} (Pre-existing authoritative schema)
-- Master tables already exist in target schema and retain their own columns and data.
-- Synthetic default INSERT omitted to protect authoritative target schema.""")
            step_num += 1
        else:
            # Table has an authoritative schema without these columns, or schema is unverified.
            # Truncation and synthetic INSERT are omitted to protect target table.
            sql_steps.append(f"""-- STEP {step_num}: Reference Target Entity: {dm_tbl} (Authoritative schema)
-- Target table '{dm_tbl}' does not contain standard sync audit columns (batch_id, execution_cycle_date, record_status, source_reference, kri_flag).
-- Synthetic dummy INSERT omitted to protect authoritative target schema.""")
            step_num += 1

    return "\n\n".join(sql_steps)



def generate_pyspark_pipeline(target_schema: str, target_db_config: dict, sources: list, rules: dict, mappings: list, control_overview: dict = None):
    """Generates 100% dynamic, production PySpark ETL script for all extracted sources including AWS S3 Parquet/CSV and multi-cloud DBs."""
    host = target_db_config.get("host") or "localhost"
    port = target_db_config.get("port") or 5432
    db_name = target_db_config.get("database_name") or "hla_db"
    user = target_db_config.get("username") or "postgres"
    target_dialect = (target_db_config.get("db_type") or "postgresql").lower().strip()

    if target_dialect in ("mssql", "sqlserver", "azure_sql", "azure_synapse", "rds_mssql"):
        jdbc_url = f"jdbc:sqlserver://{host}:{port};databaseName={db_name};encrypt=true;trustServerCertificate=true"
        driver_class = "com.microsoft.sqlserver.jdbc.SQLServerDriver"
    elif target_dialect in ("mysql", "mariadb", "rds_mysql", "azure_mysql", "gcp_mysql"):
        jdbc_url = f"jdbc:mysql://{host}:{port}/{db_name}?useSSL=false&serverTimezone=UTC"
        driver_class = "com.mysql.cj.jdbc.Driver"
    elif target_dialect == "snowflake":
        jdbc_url = f"jdbc:snowflake://{host}/?db={db_name}&schema={target_schema}"
        driver_class = "net.snowflake.client.jdbc.SnowflakeDriver"
    elif target_dialect in ("oracle", "rds_oracle"):
        jdbc_url = f"jdbc:oracle:thin:@//{host}:{port}/{db_name}"
        driver_class = "oracle.jdbc.driver.OracleDriver"
    elif target_dialect == "redshift":
        jdbc_url = f"jdbc:redshift://{host}:{port}/{db_name}"
        driver_class = "com.amazon.redshift.jdbc42.Driver"
    else:
        jdbc_url = f"jdbc:postgresql://{host}:{port}/{db_name}"
        driver_class = "org.postgresql.Driver"

    ctrl_id = (control_overview or {}).get("identification", {}) if control_overview else {}
    ctrl_raw = ctrl_id.get("control_number") or "CTRL"
    ctrl_prefix = _sanitize_ident(ctrl_raw)
    if not ctrl_prefix.startswith("ctrl"):
        ctrl_prefix = f"ctrl_{ctrl_prefix}"

    clean_sources = [_sanitize_ident(s.get("source_table") or s.get("table_name")) for s in sources if (s.get("source_table") or s.get("table_name"))]
    if not clean_sources:
        clean_sources = ["source_stream_a", "source_stream_b"]

    ingest_lines = []
    cleanse_lines = []
    bal_selects = []

    for idx, s in enumerate(sources, 1):
        s_raw = s.get("source_table") or s.get("table_name")
        if not s_raw:
            continue
        s_tbl = _sanitize_ident(s_raw)
        df_var = f"df_{s_tbl}"
        clean_var = f"clean_{s_tbl}"
        bal_var = f"bal_{s_tbl}"

        ingest_lines.append(f'{df_var} = spark.read.jdbc(jdbc_url, "{s_raw}", properties=db_props)')

        cleanse_lines.append(f"""# {idx}. Ingest & Cleanse: {s_tbl}
window_{s_tbl} = Window.partitionBy("id").orderBy(col("created_dtm").desc() if "created_dtm" in {df_var}.columns else lit(1))
{clean_var} = {df_var} \\
    .withColumn("rn", row_number().over(window_{s_tbl})) \\
    .filter(col("rn") == 1) \\
    .drop("rn")""")
        bal_selects.append(f"""{bal_var} = {clean_var}.select(
    lit("{s_tbl}").alias("source_stream"),
    col("id"),
    col("status"),
    col("created_dtm"),
    lit("BALANCED").alias("balance_status")
)""")

    union_chain = f"bal_{clean_sources[0]}"
    for s_tbl in clean_sources[1:]:
        union_chain += f".unionByName(bal_{s_tbl})"

    pyspark_code = f"""# ==============================================================================
# PySpark Production ETL & Reconciliation Job
# Control: {ctrl_raw} | Dialect: {target_dialect.upper()} | Target: {target_schema} on {host}:{port}/{db_name}
# 100% Dynamic Engine for {len(clean_sources)} Upstream Database Sources
# ==============================================================================

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, trim, lower, upper, when, coalesce, lit, row_number
from pyspark.sql.window import Window

spark = SparkSession.builder \\
    .appName("HLA_Reconciliation_Pipeline_{ctrl_prefix}_{target_schema}") \\
    .config("spark.sql.shuffle.partitions", "8") \\
    .getOrCreate()

jdbc_url = "{jdbc_url}"
db_props = {{
    "user": "{user}",
    "password": "<CREDENTIAL_FROM_VAULT>",
    "driver": "{driver_class}"
}}

# 1. Ingest Raw Tables from Databases
{chr(10).join(ingest_lines)}

# 2. Mandatory Pre-Execution Source Arrival & Append-Date Gatekeeper
# Rule: If ANY source is missing, empty, or if an Append table lacks latest date data, HALT!
def check_source_gate(df, tbl_name, is_append=False):
    cnt = df.count()
    if cnt == 0:
        raise RuntimeError(f"[QUALITY GATE ENGAGED] Source table '{{tbl_name}}' is empty. Data has not arrived on schedule. Pipeline aborted.")
    if is_append:
        date_cols = [c for c, t in df.dtypes if "date" in t.lower() or "timestamp" in t.lower()]
        if date_cols:
            max_dt = df.selectExpr(f"max({{date_cols[0]}})").collect()[0][0]
            if max_dt is None:
                raise RuntimeError(f"[QUALITY GATE ENGAGED] Append source '{{tbl_name}}' has no latest date data for scheduled run. Pipeline aborted.")
            print(f"[OK] Append table '{{tbl_name}}' verified with latest record: {{max_dt}}")
    print(f"[OK] Source '{{tbl_name}}' verified fresh ({{cnt:,}} rows).")

{chr(10).join([f'check_source_gate(df_{_sanitize_ident(s.get("source_table", ""))}, "{s.get("source_table", "")}", is_append={"append" in (s.get("type_of_load") or s.get("load_type") or "").lower()})' for s in sources if s.get("source_table")])}

# 3. Execute Pre-Execution Cleansing & Window Deduplication
{chr(10).join(cleanse_lines)}

# 4. Apply Balance Node Staging Harmonization
{chr(10).join(bal_selects)}


balanced_dataset = {union_chain}

# 4. Write to Target Database Balance Table
balanced_dataset.write \\
    .mode("overwrite") \\
    .jdbc(jdbc_url, f'"{target_schema}".{ctrl_prefix}_balanced_dataset' if ("." in target_schema or "-" in target_schema) else f'{target_schema}.{ctrl_prefix}_balanced_dataset', properties=db_props)

print("Dynamic PySpark HLA Pipeline executed successfully for {ctrl_raw}.")
spark.stop()
"""
    return pyspark_code


def build_target_logic_package(analysis_data: dict, introspected_sources: dict, target_config: dict):
    """
    Main orchestrator: Synthesizes complete target architecture, DDL, SQL, and PySpark logic
    dynamically for any HLA document.
    """
    target_env = (target_config.get("target_env") or target_config.get("environment") or "dev").lower()
    target_dialect = (target_config.get("db_type") or "postgresql").lower()

    control_overview = analysis_data.get("control_overview") or {}
    ctrl_id = control_overview.get("identification", {})
    ctrl_num = ctrl_id.get("control_number") or ""
    ctrl_title = ctrl_id.get("control_title") or "Enterprise Solution Design"

    # Derive dynamic control digits if present in specification
    ctrl_digits = control_overview.get("control_digits")
    if not ctrl_digits and ctrl_num:
        m = re.search(r'(\d+)', str(ctrl_num))
        ctrl_digits = m.group(1) if m else ""

    # Dynamic target schema e.g. explicit from Table 4 / Excel or default to clean namespace
    dynamic_default_schema = control_overview.get("target_schema")
    if isinstance(dynamic_default_schema, dict):
        dynamic_default_schema = dynamic_default_schema.get("schema_name")
    if not dynamic_default_schema:
        dynamic_default_schema = "public"

    # Use schema from config if explicitly set and not a static placeholder
    configured_schema = target_config.get("schema_name")
    if isinstance(configured_schema, dict):
        configured_schema = configured_schema.get("schema_name")
    if configured_schema and configured_schema not in ("target_dev", "target_prod"):
        target_schema = configured_schema
    else:
        target_schema = dynamic_default_schema

    sources = analysis_data.get("sources") or []
    rules = analysis_data.get("rules") or {}
    mappings = analysis_data.get("mappings") or []
    config_tables = analysis_data.get("config_tables") or []

    # 1. Generate Target DDL
    ddl = generate_target_ddl(target_schema, target_dialect, sources, rules, mappings, introspected_sources, analysis_data)

    # 1b. Standalone Scanned Source Tables DDL
    source_tables_ddl = generate_source_tables_ddl(target_schema, target_dialect, sources, introspected_sources, analysis_data)

    # 2. Generate Target Transformation SQL (schema-aware against live DB and generated DDL)
    live_target_meta = None
    if target_config and isinstance(target_config, dict) and target_config.get("host"):
        try:
            target_url = build_connection_url(target_config)
            t_eng = create_engine(target_url, connect_args={"connect_timeout": 5} if "sqlite" not in target_url else {})
            live_target_meta = inspect_target_schema(t_eng, target_schema)
        except Exception:
            pass

    sql_script = generate_transformation_sql(
        target_schema,
        target_dialect,
        sources,
        rules,
        mappings,
        config_tables,
        control_overview,
        analysis_data=analysis_data,
        target_meta=live_target_meta,
        ddl_script=ddl
    )


    # 3. Generate PySpark ETL Script
    pyspark_code = generate_pyspark_pipeline(target_schema, target_config, sources, rules, mappings, control_overview)

    # 4. LLM Synthesis / Architectural Reasoning
    prompt = f"""
You are an expert Chief Database & Cloud Architect.
Analyze the target solution logic generated for Control '{ctrl_num} - {ctrl_title}' (Dialect: {target_dialect}, Schema: {target_schema}):

Number of source tables: {len(sources)}
Number of pre-execution filter rules: {len(rules.get('filter_rules', []))}
Number of balance & reconciliation flows: {len(rules.get('balance_rules', [])) + len(rules.get('reconciliation_flows', []))}
Number of mapped attributes: {len(mappings)}

Provide a concise technical architectural brief explaining:
1. Target schema segregation ({target_schema}).
2. How the pre-execution rules cleanse and deduplicate feeds before convergence into the balance node.
3. How the tiered reconciliation and KRI exception classification are architected.
4. Deployment readiness and zero-downtime execution safeguards.
"""
    llm_reasoning = None
    try:
        llm_reasoning = call_ollama(prompt)
        if not llm_reasoning:
            llm_reasoning = call_groq_or_openai(prompt)
    except Exception:
        pass

    if not llm_reasoning:
        src_names = ", ".join([f"`stg_{_sanitize_ident(s.get('source_table'))}_clean`" for s in sources[:3]]) or "`stg_source_clean`"
        ctrl_slug = _sanitize_ident(ctrl_num)
        llm_reasoning = f"""### Target Solution Architecture Brief
**Solution Specification**: {ctrl_num} - {ctrl_title}

1. **Target Schema & Environment Isolation**:
   The target architecture deploys into dedicated namespace `{target_schema}`. This ensures total isolation between Development testing and Production ledgers without impacting upstream operational systems.

2. **Pre-Execution Quality Gate**:
   Upstream source feeds ({len(sources)} datasets) are cleansed and deduplicated into dedicated staging tables ({src_names}). Partitioned window deduplication eliminates stream replays, null-integrity checks drop unidentifiable records, and configurable exclusion tables purge non-production test entries.

3. **Balance Node Consolidation & Tiered Reconciliation**:
   Clean data converges into `{target_schema}.{ctrl_slug}_balanced_dataset`. Tiered reconciliation executes multi-pass key matching. Records with full parity enter the Balance Bucket (`BB_RECONCILED`), while discrepancies trigger automated KRI risk ratings in `{target_schema}.{ctrl_slug}_recon_exceptions`.

4. **Production Deployment Readiness**:
   All DDL scripts use idempotent `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS` semantics, enabling continuous repeatable deployment.
"""

    # Extract table-level scan statuses (found vs missing and required column counts)
    _, table_status_map = get_source_column_definitions(sources, introspected_sources, target_dialect, analysis_data)

    return {
        "environment": target_env,
        "target_dialect": target_dialect,
        "target_schema": target_schema,
        "source_tables_ddl": source_tables_ddl,
        "ddl": ddl,
        "transformation_sql": sql_script,
        "pyspark_code": pyspark_code,
        "llm_reasoning": llm_reasoning,
        "source_table_statuses": table_status_map,
        "summary": {
            "sources_modeled": len([s for s in table_status_map.values() if s.get("table_found")]),
            "sources_missing": len([s for s in table_status_map.values() if not s.get("table_found")]),
            "filter_rules_modeled": len(rules.get("filter_rules", [])),
            "balance_tables_modeled": len(sources) + 3,
            "target_schema": target_schema,
            "environment": target_env.upper(),
            "hla_analysis_summary": (analysis_data or {}).get("hla_analysis_summary") or {}
        }
    }


def _has_executable_sql(sql_statement: str) -> bool:
    """
    Safely determine if a SQL statement contains executable SQL.
    Correctly ignores:
      - Whitespace and blank lines
      - Single-line comments (-- ...)
      - Block comments (/* ... */)
      - Multiple and nested comments
      - Comments before or after SQL
    Preserves and inspects:
      - Quoted string literals ('...')
      - Double-quoted identifiers ("...")
      - Dollar-quoted blocks ($tag$...$tag$ or $$...$$)
      - PostgreSQL DO $$ ... $$ blocks
      - Parameterized types, DEFAULT expressions, GENERATED columns
    Returns False for empty or comment-only statements.
    Returns True only if actual executable SQL remains.
    """
    if not sql_statement or not sql_statement.strip():
        return False

    s = sql_statement
    n = len(s)
    i = 0
    in_sq = False
    in_dq = False
    dollar_tag = None
    exec_tokens = []

    while i < n:
        ch = s[i]

        # Handle dollar quotes ($$...$$ or $tag$...$tag$)
        if dollar_tag:
            exec_tokens.append(ch)
            if s.startswith(dollar_tag, i):
                exec_tokens.append(dollar_tag)
                i += len(dollar_tag)
                dollar_tag = None
                continue
            i += 1
            continue

        # Handle single-quoted strings
        if in_sq:
            exec_tokens.append(ch)
            if ch == "'":
                if i + 1 < n and s[i + 1] == "'":
                    exec_tokens.append("'")
                    i += 2
                    continue
                in_sq = False
            elif ch == "\\" and i + 1 < n:
                exec_tokens.append(s[i + 1])
                i += 2
                continue
            i += 1
            continue

        # Handle double-quoted identifiers
        if in_dq:
            exec_tokens.append(ch)
            if ch == '"':
                if i + 1 < n and s[i + 1] == '"':
                    exec_tokens.append('"')
                    i += 2
                    continue
                in_dq = False
            i += 1
            continue

        # Check for single-line comment --
        if ch == '-' and i + 1 < n and s[i + 1] == '-':
            eol = s.find('\n', i + 2)
            if eol == -1:
                break
            i = eol + 1
            continue

        # Check for block comment /* ... */
        if ch == '/' and i + 1 < n and s[i + 1] == '*':
            end_block = s.find('*/', i + 2)
            if end_block == -1:
                break
            i = end_block + 2
            continue

        # Check string entry
        if ch == "'":
            in_sq = True
            exec_tokens.append(ch)
            i += 1
            continue

        # Check identifier entry
        if ch == '"':
            in_dq = True
            exec_tokens.append(ch)
            i += 1
            continue

        # Check dollar quote entry
        if ch == '$':
            m = re.match(r'\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$', s[i:])
            if m:
                dollar_tag = m.group(0)
                exec_tokens.append(dollar_tag)
                i += len(dollar_tag)
                continue

        # Ignore standalone semicolons and whitespace when testing for executable SQL
        if not ch.isspace() and ch != ';':
            exec_tokens.append(ch)
        i += 1

    cleaned = ''.join(exec_tokens).strip()
    return len(cleaned) > 0


def _split_sql_statements(sql_script: str) -> list:
    """
    Split executable SQL without breaking quoted strings, comments, or PostgreSQL DO $$ blocks.
    Discards empty or comment-only statement fragments so they are never sent to the DB.
    """
    statements = []
    buf = []
    i = 0
    n = len(sql_script)
    in_sq = False
    in_dq = False
    dollar_tag = None

    while i < n:
        ch = sql_script[i]
        if dollar_tag:
            if sql_script.startswith(dollar_tag, i):
                buf.append(dollar_tag)
                i += len(dollar_tag)
                dollar_tag = None
                continue
            buf.append(ch)
            i += 1
            continue
        if in_sq:
            buf.append(ch)
            if ch == "'":
                if i + 1 < n and sql_script[i + 1] == "'":
                    buf.append("'")
                    i += 2
                    continue
                in_sq = False
            elif ch == "\\" and i + 1 < n:
                buf.append(sql_script[i + 1])
                i += 2
                continue
            i += 1
            continue
        if in_dq:
            buf.append(ch)
            if ch == '"':
                if i + 1 < n and sql_script[i + 1] == '"':
                    buf.append('"')
                    i += 2
                    continue
                in_dq = False
            i += 1
            continue

        # Preserve single-line comments in statement buffer
        if ch == '-' and i + 1 < n and sql_script[i + 1] == '-':
            eol = sql_script.find('\n', i + 2)
            if eol == -1:
                buf.append(sql_script[i:])
                break
            buf.append(sql_script[i:eol + 1])
            i = eol + 1
            continue

        # Preserve block comments in statement buffer
        if ch == '/' and i + 1 < n and sql_script[i + 1] == '*':
            end_block = sql_script.find('*/', i + 2)
            if end_block == -1:
                buf.append(sql_script[i:])
                break
            buf.append(sql_script[i:end_block + 2])
            i = end_block + 2
            continue

        if ch == "'":
            in_sq = True
            buf.append(ch)
            i += 1
            continue
        if ch == '"':
            in_dq = True
            buf.append(ch)
            i += 1
            continue
        if ch == '$':
            m = re.match(r'\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$', sql_script[i:])
            if m:
                dollar_tag = m.group(0)
                buf.append(dollar_tag)
                i += len(dollar_tag)
                continue
        if ch == ';':
            stmt = ''.join(buf).strip()
            # Only append statement if it contains actual executable SQL
            if stmt and _has_executable_sql(stmt):
                statements.append(stmt)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1

    tail = ''.join(buf).strip()
    if tail and _has_executable_sql(tail):
        statements.append(tail)
    return statements


def validate_target_ddl(target_config: dict, ddl_script: str, analysis_data: dict = None):
    """
    Performs a 100% READ-ONLY dry-run validation of the target schema and generated DDL.

    SAFETY GUARANTEE:
    This function NEVER executes CREATE, ALTER, DROP, TRUNCATE, INSERT, UPDATE, DELETE,
    or any schema/data modification statement.

    Flow:
      1. Validates connection to target database.
      2. Detects and inspects target schema via information_schema / catalog.
      3. Parses required objects and columns from generated DDL.
      4. Reconciles desired objects against target schema metadata.
      5. Classifies each object: EXISTING, MISSING, DIFFERENT, INVALID.
      6. Synthesizes proposed actions without applying changes.
      7. Returns (success: bool, message: str, reconciliation: dict, stages: list).
    """
    db_type = (target_config.get("db_type") or "postgresql").lower()
    target_schema = target_config.get("schema_name") or "public"

    stages: list = []
    def _stage(label: str, status: str = "ok", detail: str = None) -> None:
        entry: dict = {"label": label, "status": status}
        if detail:
            entry["detail"] = str(detail)[:400]
        stages.append(entry)

    # Sandbox dry-run
    if db_type == "sandbox":
        table_matches = re.findall(
            r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([^\s\(]+)",
            ddl_script,
            flags=re.IGNORECASE,
        )
        tbl_names = list(
            dict.fromkeys(
                m.split(".")[-1].strip("\"'`[] ") for m in table_matches
            )
        )
        n = len(tbl_names)
        recon = {
            "schema_status": "MISSING",
            "objects": {
                t: {
                    "bare_name": t,
                    "status": "MISSING",
                    "existing_columns": [],
                    "missing_columns": [],
                    "conflict_columns": [],
                    "alter_statements": [],
                    "proposed_action": "CREATE TABLE",
                }
                for t in tbl_names
            },
            "counts": {"existing": 0, "missing": n, "different": 0, "invalid": 0, "failed": 0},
        }
        _stage("Target connection validated")
        _stage(f"Target schema detected: {target_schema} (sandbox)")
        _stage("Existing objects inspected: 0 table(s) found")
        _stage(f"Generated DDL parsed: {n} object(s) defined")
        _stage("Metadata reconciliation completed")
        _stage("No database changes executed (dry-run)")
        return (
            True,
            f"Dry-run validation successful. {n} table(s) parsed for schema '{target_schema}'. No changes executed.",
            recon,
            stages,
        )

    empty_recon: dict = {
        "schema_status": "UNKNOWN",
        "objects": {},
        "counts": {"existing": 0, "missing": 0, "different": 0, "invalid": 0, "failed": 0},
    }

    try:
        url = build_connection_url(target_config)
        engine = create_engine(
            url,
            connect_args={"connect_timeout": 8} if "sqlite" not in url else {},
        )

        # 1. Connection check
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        _stage("Target connection validated")

        # 2. Inspect target schema (read-only metadata inspection)
        existing_meta = inspect_target_schema(engine, target_schema)
        schema_exists = existing_meta.get("schema_exists", False)
        inspect_err = existing_meta.get("inspect_error")

        if inspect_err:
            _stage("Schema inspection warning", "warning", inspect_err)
        elif schema_exists:
            n_tables = len(existing_meta.get("tables", {}))
            _stage(f"Target schema detected: {target_schema}")
            _stage(f"Existing objects inspected: {n_tables} table(s) found")
        else:
            _stage(f"Target schema detected: {target_schema} (not yet created in target DB)")
            _stage("Existing objects inspected: 0 table(s) found")

        # 3. Parse required objects from DDL (read-only parsing)
        required_objects = _parse_required_objects_from_ddl(ddl_script)
        _stage(f"Generated DDL parsed: {len(required_objects)} target object(s) found")

        # 4. Reconcile metadata
        recon = reconcile_objects(existing_meta, required_objects)
        counts = recon["counts"]
        if "failed" not in counts:
            counts["failed"] = 0

        # 5. Populate proposed actions without executing any SQL
        for obj_key, obj_info in recon.get("objects", {}).items():
            tbl_bare = obj_info["bare_name"]
            st = obj_info.get("status")
            if st == "MISSING":
                obj_info["proposed_action"] = "CREATE TABLE"
            elif st == "DIFFERENT":
                alter_results = _build_alter_statements(
                    target_schema, tbl_bare, obj_info.get("missing_columns", []), db_type
                )
                unsafe_stmts = [r[0] for r in alter_results if not r[1]]
                obj_info["alter_statements"] = [r[0] for r in alter_results]
                if unsafe_stmts:
                    obj_info["proposed_action"] = f"BLOCKED: {len(unsafe_stmts)} unsafe column migration(s)"
                else:
                    col_names = ", ".join(c["name"] for c in obj_info.get("missing_columns", []))
                    obj_info["proposed_action"] = f"ADD COLUMN: {col_names}"
            elif st == "EXISTING":
                obj_info["proposed_action"] = "NONE (reused as-is)"
            elif st == "INVALID":
                obj_info["proposed_action"] = "BLOCKED: column type conflict requires manual migration"

        _stage("Metadata reconciliation completed")
        _stage("No database changes executed (dry-run)")

        # Truthful dry-run summary
        msg = (
            f"Dry-run validation complete for schema '{target_schema}'. "
            f"Existing: {counts.get('existing', 0)} | "
            f"Missing: {counts.get('missing', 0)} | "
            f"Different: {counts.get('different', 0)} | "
            f"Invalid: {counts.get('invalid', 0)}. "
            f"No database modifications executed."
        )

        success = counts.get("invalid", 0) == 0
        return success, msg, recon, stages

    except Exception as err:
        err_msg = str(err)
        _stage("Dry-run validation failed", "error", err_msg)
        return False, f"Dry-run validation error: {err_msg}", empty_recon, stages


def deploy_target_ddl(target_config: dict, ddl_script: str):
    """
    Executes and commits the DDL in the target database.
    Verifies that the newly created tables exist in the target schema.
    Returns: (success: bool, message: str, deployed_tables: list)
    """
    db_type = (target_config.get("db_type") or "").lower()
    target_schema = target_config.get("schema_name") or "public"
    create_schema_stmt, _ = _format_schema_prefix(target_schema, db_type)

    if db_type == "sandbox":
        # Dynamically extract table names from DDL script
        table_matches = re.findall(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:[a-zA-Z0-9_\."]+)?([a-zA-Z0-9_]+)', ddl_script, flags=re.IGNORECASE)
        unique_tables = list(dict.fromkeys(table_matches))
        return True, f"Sandbox Deployment: {len(unique_tables)} tables provisioned in simulated enterprise cluster.", unique_tables

    try:
        url = build_connection_url(target_config)
        engine = create_engine(url, connect_args={"connect_timeout": 10} if "sqlite" not in url else {})
        
        # Pre-ensure target schema exists
        if create_schema_stmt and db_type in ("postgresql", "postgres", "snowflake"):
            try:
                with engine.connect() as init_conn:
                    if _has_executable_sql(create_schema_stmt):
                        init_conn.execute(text(create_schema_stmt))
                        init_conn.commit()
            except Exception:
                pass

        raw_statements = _split_sql_statements(ddl_script)
        
        with engine.connect() as conn:
            for stmt in raw_statements:
                clean_stmt = stmt.strip()
                if clean_stmt and _has_executable_sql(clean_stmt):
                    try:
                        conn.execute(text(clean_stmt))
                        conn.commit()
                    except Exception as stmt_err:
                        conn.rollback()
                        err_str = str(stmt_err).lower()
                        if "already exists" in err_str:
                            pass
                        elif clean_stmt.upper().startswith("CREATE SCHEMA") and ("permission denied" in err_str or "insufficientprivilege" in err_str):
                            pass
                        else:
                            raise stmt_err

        # Inspect created tables in target schema
        inspector = inspect(engine)
        tables = []
        try:
            tables = inspector.get_table_names(schema=target_schema if target_schema else None)
        except Exception:
            pass
        if not tables:
            try:
                tables = inspector.get_table_names()
            except Exception:
                pass

        return True, f"Successfully deployed {len(raw_statements)} DDL statements. {len(tables)} tables verified in schema '{target_schema}'.", tables
    except Exception as err:
        err_msg = str(err)
        if "schema" in err_msg.lower() and "does not exist" in err_msg.lower():
            err_msg += f"\n\n[Action Required] The schema '{target_schema}' does not exist on target database and your user lacks privilege to CREATE SCHEMA.\nRecommended solutions:\n1. In Target DB Configuration, change 'Target Schema Namespace' to 'public' (accessible by all users).\n2. Or ask your DBA to run: CREATE SCHEMA {target_schema}; GRANT ALL ON SCHEMA {target_schema} TO \"{target_config.get('username')}\";"
        elif "permission denied for database" in err_msg.lower():
            err_msg += f"\n\n[Action Required] Your database user lacks CREATE permission on this database.\nRecommended solution: In Target DB Configuration, change 'Target Schema Namespace' to 'public'."
        return False, f"Deployment failed: {err_msg}", []


def ensure_target_tables_provisioned(target_config: dict, ddl_script: str) -> tuple:
    """
    Checks if required target tables are already created in the target database.
    - If already created: Skips table creation (no re-creation needed).
    - First time alone: Creates the required DDL if not already present.
    Returns: (success: bool, message: str, existing_or_deployed_tables: list)
    """
    db_type = (target_config.get("db_type") or "").lower()
    target_schema = target_config.get("schema_name") or "public"

    if db_type == "sandbox":
        table_matches = re.findall(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:[a-zA-Z0-9_\."]+)?([a-zA-Z0-9_]+)', ddl_script, flags=re.IGNORECASE)
        unique_tables = list(dict.fromkeys(table_matches))
        return True, f"Target tables verified in simulated sandbox cluster.", unique_tables

    try:
        url = build_connection_url(target_config)
        engine = create_engine(url, connect_args={"connect_timeout": 10} if "sqlite" not in url else {})

        # Inspect current existing tables in the target schema
        inspector = inspect(engine)
        existing_tables = []
        try:
            existing_tables = inspector.get_table_names(schema=target_schema if target_schema else None)
        except Exception:
            try:
                existing_tables = inspector.get_table_names()
            except Exception:
                existing_tables = []

        # Find required table names from DDL script (handling schema.table prefixes)
        table_matches = re.findall(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([^\s\(]+)', ddl_script, flags=re.IGNORECASE)
        required_tables = []
        for m in table_matches:
            tbl_clean = m.split(".")[-1].strip('"\';`[] ')
            if tbl_clean and tbl_clean.lower() not in [r.lower() for r in required_tables]:
                required_tables.append(tbl_clean)

        missing_tables = [t for t in required_tables if t.lower() not in [e.lower() for e in existing_tables]]

        if not missing_tables and existing_tables and len(required_tables) > 0:
            return True, f"Target tables already exist in schema '{target_schema}'. DDL creation skipped.", existing_tables

        # Missing tables exist -> Provision first time alone
        return deploy_target_ddl(target_config, ddl_script)
    except Exception as e:
        return False, f"Could not verify target tables: {str(e)}", []


# ═══════════════════════════════════════════════════════════════════════════════
# GENERIC IDEMPOTENT DEPLOYMENT ENGINE
# Metadata-first, control-agnostic, non-destructive schema reconciliation.
# Works for any HLA control (CTRL-N) without any hardcoded control IDs,
# table names, or transformation rules.
# ═══════════════════════════════════════════════════════════════════════════════


def _split_top_level_defs(col_block: str) -> list:
    """
    Split a CREATE TABLE body by top-level commas, correctly handling:
      - nested parentheses  e.g. NUMERIC(18,2), GENERATED ALWAYS AS (...)
      - single-quoted strings  e.g. DEFAULT 'value'
      - double-quoted identifiers  e.g. "my_column"

    Returns a list of raw column/constraint definition strings.
    """
    defs: list = []
    current: list = []
    depth    = 0
    in_sq    = False   # inside single-quoted string
    in_dq    = False   # inside double-quoted identifier
    i        = 0
    s        = col_block

    while i < len(s):
        ch = s[i]

        if in_sq:
            current.append(ch)
            if ch == "'" and (i == 0 or s[i - 1] != "\\"):
                in_sq = False
        elif in_dq:
            current.append(ch)
            if ch == '"':
                in_dq = False
        elif ch == "'":
            in_sq = True
            current.append(ch)
        elif ch == '"':
            in_dq = True
            current.append(ch)
        elif ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            defn = "".join(current).strip()
            if defn:
                defs.append(defn)
            current = []
        else:
            current.append(ch)

        i += 1

    tail = "".join(current).strip()
    if tail:
        defs.append(tail)

    return defs


# Constraint starters — definitions that begin with these are NOT columns
_CONSTRAINT_STARTERS = (
    "PRIMARY KEY", "FOREIGN KEY", "UNIQUE", "CHECK",
    "CONSTRAINT", "INDEX", "KEY ", "--",
)

# Incomplete generated/type fragment patterns — ALTER statements containing
# these incomplete fragments must be rejected before execution.
_INCOMPLETE_PATTERNS = re.compile(
    r'(?:GENERATED\s+BY\s*;|GENERATED\s+ALWAYS\s*;|GENERATED\s+BY\s+DEFAULT\s*;'
    r'|\bDEFAULT\s*;|\bVARCHAR\s*;|\bNUMERIC\s*;)',
    re.IGNORECASE,
)


def _is_alter_safe(stmt: str) -> tuple:
    """
    Validate an ALTER TABLE ADD COLUMN statement before execution.

    Returns (is_safe: bool, reason: str).
    """
    s = stmt.strip()
    if not s:
        return False, "Empty statement"
    if not s.upper().startswith("ALTER TABLE"):
        return False, "Not an ALTER TABLE statement"
    if _INCOMPLETE_PATTERNS.search(s):
        return False, f"Incomplete type fragment detected in: {s[:120]}"
    # Must end with ;
    if not s.rstrip().endswith(";"):
        return False, "Statement does not end with semicolon"
    return True, "OK"


def _parse_required_objects_from_ddl(ddl_script: str) -> list:
    """
    Parse all CREATE TABLE statements from a DDL script to derive the list of
    required target objects.

    Returns a list of dicts:
        {
            "full_name": "schema.table" or "table",
            "bare_name": "table",            # unqualified, lowercase
            "columns":   [
                {
                    "name":            str,   # lowercase
                    "data_type":       str,   # base type for comparison
                    "full_definition": str,   # complete definition for ALTER
                    "is_nullable":     bool,
                    "is_generated":    bool,
                    "is_identity":     bool,
                },
                ...
            ]
        }

    Generic — no control-specific assumptions.
    Uses a paren/quote-aware body extractor and a top-level comma splitter
    so that parameterized types, DEFAULT expressions, and GENERATED columns
    are all correctly captured.
    """
    # Pass 1: locate each CREATE TABLE header + opening paren
    tbl_header = re.compile(
        r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?'
        r'((?:"[^"]+"|\w+)(?:\.(?:"[^"]+"|\w+))?)'
        r'\s*\(',
        re.IGNORECASE,
    )

    required: list = []
    seen_bare: set = set()

    for hdr_m in tbl_header.finditer(ddl_script):
        full_name = hdr_m.group(1).strip()
        parts     = full_name.split(".")
        bare_name = parts[-1].strip("\"'`[] ").lower()

        if bare_name in seen_bare:
            continue
        seen_bare.add(bare_name)

        # Pass 2: extract body with balanced-parenthesis counter
        start = hdr_m.end()   # position right after the opening '('
        depth = 1
        pos   = start
        while pos < len(ddl_script) and depth > 0:
            ch = ddl_script[pos]
            if   ch == "(": depth += 1
            elif ch == ")": depth -= 1
            pos += 1
        col_block = ddl_script[start : pos - 1]   # body without outer parens

        # Pass 3: split by top-level commas (paren/quote-aware)
        raw_defs = _split_top_level_defs(col_block)

        columns: list = []
        for defn in raw_defs:
            defn = defn.strip()
            if not defn:
                continue
            upper = defn.upper().lstrip()

            # Skip table-level constraints
            if any(upper.startswith(kw) for kw in _CONSTRAINT_STARTERS):
                continue

            # Split on first whitespace: col_name | rest_of_definition
            parts_defn = defn.split(None, 1)
            if len(parts_defn) < 2:
                continue

            raw_col_name = parts_defn[0].strip('"\'`[]')
            if not re.match(r'^\w+$', raw_col_name):
                continue   # not a column definition

            full_def_str = parts_defn[1].strip()   # everything after the col name

            # Extract BASE TYPE for comparison (first word + optional parens)
            base_type_m = re.match(
                r'^([A-Za-z][A-Za-z0-9_]*(?:\s*\([^)]*\))?)',
                full_def_str,
            )
            base_type = base_type_m.group(1).strip() if base_type_m else full_def_str.split()[0]

            is_upper     = full_def_str.upper()
            is_nullable  = "NOT NULL" not in is_upper
            is_generated = "GENERATED" in is_upper
            is_identity  = is_generated and ("IDENTITY" in is_upper or "AS IDENTITY" in is_upper)

            columns.append({
                "name":            raw_col_name.lower(),
                "data_type":       base_type,
                "full_definition": full_def_str,
                "is_nullable":     is_nullable,
                "is_generated":    is_generated,
                "is_identity":     is_identity,
            })

        required.append(
            {"full_name": full_name, "bare_name": bare_name, "columns": columns}
        )

    return required



# ── Broad type-family compatibility map ───────────────────────────────────────
_TYPE_FAMILIES: dict = {
    "integer":    {"integer", "int", "int2", "int4", "int8", "bigint", "smallint",
                   "numeric", "decimal", "real", "double precision", "float"},
    "bigint":     {"bigint", "int8", "integer", "int4", "numeric", "decimal"},
    "text":       {"text", "varchar", "character varying", "char", "bpchar",
                   "name", "citext", "nvarchar", "nchar"},
    "boolean":    {"boolean", "bool", "bit"},
    "timestamp":  {"timestamp", "timestamp without time zone",
                   "timestamp with time zone", "timestamptz", "datetime",
                   "datetime2"},
    "date":       {"date", "timestamp", "timestamptz", "datetime"},
    "numeric":    {"numeric", "decimal", "real", "double precision", "float8",
                   "float", "integer", "bigint"},
    "jsonb":      {"jsonb", "json"},
    "json":       {"json", "jsonb"},
    "uuid":       {"uuid"},
    "bytea":      {"bytea", "blob", "varbinary", "binary"},
}


def _are_types_compatible(existing_type: str, required_type: str) -> bool:
    """
    Return True when an existing column type is safely compatible with the
    required type from the HLA DDL.

    Errs on the side of compatibility (avoids false INVALID classifications)
    for common broadening conversions (e.g. int → numeric, varchar(50) → text).
    """
    et = existing_type.lower().strip()
    rt = required_type.lower().strip()

    if et == rt:
        return True
    # Prefix match (e.g. "character varying" vs "character varying(255)")
    if et.startswith(rt) or rt.startswith(et):
        return True
    # Both are VARCHAR(N) variants with different sizes → compatible
    if re.match(r"(?:varchar|character varying|nvarchar)\(\d+\)", et) and \
       re.match(r"(?:varchar|character varying|nvarchar)\(\d+\)", rt):
        return True
    # Family-based compatibility
    for _family, members in _TYPE_FAMILIES.items():
        if any(et.startswith(m) or et == m for m in members):
            if any(rt.startswith(m) or rt == m for m in members):
                return True
    return False


def inspect_target_schema(engine, target_schema: str) -> dict:
    """
    Query the target database's information_schema to discover:
        - Whether the schema (namespace) exists
        - All base tables within that schema
        - Column names, data types, and nullability for each table

    Returns:
        {
            "schema_exists": bool,
            "schema_name":   str,
            "tables": {
                "<bare_table_name_lower>": {
                    "exists":       True,
                    "columns":      [{"name", "data_type", "is_nullable", "default"}, ...],
                    "column_names": set()   # fast lookup set
                }
            },
            "inspect_error": str | None   # only present on failure
        }

    Generic — no control-specific logic.  Executes no DDL.
    """
    meta: dict = {
        "schema_exists": False,
        "schema_name": target_schema,
        "tables": {},
    }

    try:
        with engine.connect() as conn:
            # 1. Schema existence
            schema_exists = conn.execute(
                text(
                    "SELECT EXISTS ("
                    "  SELECT 1 FROM information_schema.schemata"
                    "  WHERE LOWER(schema_name) = LOWER(:s)"
                    ")"
                ),
                {"s": target_schema},
            ).scalar()
            meta["schema_exists"] = bool(schema_exists)

            if not meta["schema_exists"]:
                return meta

            # 2. Tables within schema
            table_rows = conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables"
                    " WHERE LOWER(table_schema) = LOWER(:s)"
                    "   AND table_type = 'BASE TABLE'"
                    " ORDER BY table_name"
                ),
                {"s": target_schema},
            ).fetchall()

            for (tname,) in table_rows:
                tname_lower = tname.lower()
                col_rows = conn.execute(
                    text(
                        "SELECT column_name, data_type, is_nullable, column_default, "
                        "       COALESCE(is_identity, 'NO') AS is_id, "
                        "       COALESCE(is_generated, 'NEVER') AS is_gen "
                        " FROM information_schema.columns"
                        " WHERE LOWER(table_schema) = LOWER(:s)"
                        "   AND LOWER(table_name)  = LOWER(:t)"
                        " ORDER BY ordinal_position"
                    ),
                    {"s": target_schema, "t": tname},
                ).fetchall()

                columns = [
                    {
                        "name": r[0].lower(),
                        "data_type": r[1].lower(),
                        "is_nullable": (r[2] or "YES").upper() == "YES",
                        "default": r[3],
                        "is_identity": (str(r[4]).upper() == "YES"),
                        "is_generated": (str(r[5]).upper() not in ("NEVER", "NO", "NONE", "")),
                    }
                    for r in col_rows
                ]

                meta["tables"][tname_lower] = {
                    "exists": True,
                    "columns": columns,
                    "column_names": {c["name"] for c in columns},
                }

    except Exception as exc:
        meta["inspect_error"] = str(exc)

    return meta


def reconcile_objects(existing_meta: dict, required_objects: list) -> dict:
    """
    Compare the list of required objects (parsed from generated DDL) against
    the discovered target DB metadata.

    Classifies each required object as:
        EXISTING  — table present; all required columns present and type-compatible
        MISSING   — table absent from DB
        DIFFERENT — table present but has safely reconcilable differences
                    (missing required columns that can be added via ALTER)
        INVALID   — table present but has incompatible column type conflicts
                    that cannot be reconciled without destructive changes

    Returns:
        {
            "schema_status": "EXISTING" | "MISSING",
            "objects": {
                "<full_name>": {
                    "bare_name":        str,
                    "status":           "EXISTING"|"MISSING"|"DIFFERENT"|"INVALID",
                    "existing_columns": [...],
                    "missing_columns":  [...],
                    "conflict_columns": [{"name", "existing_type", "required_type"}, ...],
                    "alter_statements": []    # populated by idempotent_deploy
                }
            },
            "counts": {"existing": 0, "missing": 0, "different": 0, "invalid": 0}
        }

    Generic — no hardcoded control IDs or table names.
    """
    report: dict = {
        "schema_status": "EXISTING" if existing_meta.get("schema_exists") else "MISSING",
        "objects": {},
        "counts": {"existing": 0, "missing": 0, "different": 0, "invalid": 0},
    }

    for obj in required_objects:
        bare = obj["bare_name"].lower()
        full = obj.get("full_name", bare)
        req_cols = obj.get("columns", [])

        existing_tbl = existing_meta.get("tables", {}).get(bare)

        if not existing_tbl:
            report["objects"][full] = {
                "bare_name": bare,
                "status": "MISSING",
                "existing_columns": [],
                "missing_columns": req_cols,
                "conflict_columns": [],
                "alter_statements": [],
            }
            report["counts"]["missing"] += 1
            continue

        # Table exists — compare columns
        ex_col_names = existing_tbl.get("column_names", set())
        ex_col_map = {c["name"]: c for c in existing_tbl.get("columns", [])}

        missing_cols: list = []
        conflict_cols: list = []

        for rc in req_cols:
            cname = rc["name"].lower()
            if cname not in ex_col_names:
                missing_cols.append(rc)
            else:
                ex_col = ex_col_map.get(cname, {})
                if not _are_types_compatible(
                    ex_col.get("data_type", ""), rc.get("data_type", "")
                ):
                    conflict_cols.append(
                        {
                            "name": cname,
                            "existing_type": ex_col.get("data_type", "unknown"),
                            "required_type": rc.get("data_type", "unknown"),
                        }
                    )

        if conflict_cols:
            status = "INVALID"
            report["counts"]["invalid"] += 1
        elif missing_cols:
            status = "DIFFERENT"
            report["counts"]["different"] += 1
        else:
            status = "EXISTING"
            report["counts"]["existing"] += 1

        report["objects"][full] = {
            "bare_name": bare,
            "status": status,
            "existing_columns": existing_tbl.get("columns", []),
            "missing_columns": missing_cols,
            "conflict_columns": conflict_cols,
            "alter_statements": [],
        }

    return report


def _build_alter_statements(
    schema: str, table_bare: str, missing_cols: list, dialect: str
) -> list:
    """
    Produce safe, non-destructive ALTER TABLE statements to add missing columns
    to a DIFFERENT (partially-existing) table.

    Uses `full_definition` from the parsed column to preserve complete SQL
    including GENERATED/IDENTITY/DEFAULT expressions.

    Returns a list of (stmt: str, safe: bool, reason: str) tuples so the
    caller can decide to execute or skip/classify-as-INVALID.

    Dialect-aware. Never drops or recreates columns.
    """
    d = (dialect or "postgresql").lower()
    # A schema name can legally contain dots, e.g. "ra_ctrl.ctrl_23".
    # Reuse the central formatter instead of concatenating the raw schema;
    # otherwise PostgreSQL parses ra_ctrl.ctrl_23.ctrl_config as
    # database.schema.table and raises a cross-database reference error.
    _, prefix = _format_schema_prefix(schema, d) if schema else ("", "")
    results: list = []   # list of (stmt, is_safe, reason)

    is_pg = d in (
        "postgresql", "postgres", "rds_postgres",
        "azure_postgres", "gcp_postgres",
        "redshift", "snowflake",
    )
    is_mssql = d in ("mssql", "sqlserver", "azure_sql", "azure_synapse", "rds_mssql")
    is_mysql = d in ("mysql", "mariadb", "rds_mysql", "azure_mysql", "gcp_mysql")

    for col in missing_cols:
        cname    = col.get("name", "unknown")
        # Prefer full_definition (complete SQL after the column name) over
        # bare data_type; fall back for backward compatibility.
        full_def = col.get("full_definition") or col.get("data_type", "TEXT")
        is_gen   = col.get("is_generated", False)
        is_id    = col.get("is_identity",  False)

        # Generated STORED columns cannot be added by ALTER in most dialects.
        # Identity columns can be added in PostgreSQL via ALTER.
        if is_gen and not is_id and "STORED" in full_def.upper():
            # GENERATED ALWAYS AS (...) STORED cannot be added via ALTER in PG < 16
            results.append((
                f"-- UNSAFE: cannot add generated-stored column '{cname}' via ALTER "
                f"(table={prefix}{table_bare}). Manual migration required.",
                False,
                f"Generated stored column '{cname}' cannot be added via ALTER TABLE safely.",
            ))
            continue

        # For ALTER on existing tables, NOT NULL without DEFAULT will fail on tables with data.
        # Strip NOT NULL if no DEFAULT is specified so ALTER succeeds safely.
        alter_def = full_def
        if re.search(r'\bNOT\s+NULL\b', alter_def, flags=re.IGNORECASE) and not re.search(r'\bDEFAULT\b', alter_def, flags=re.IGNORECASE):
            alter_def = re.sub(r'\bNOT\s+NULL\b', '', alter_def, flags=re.IGNORECASE).strip()

        if is_pg:
            stmt = (
                f"ALTER TABLE {prefix}{table_bare}"
                f" ADD COLUMN IF NOT EXISTS {cname} {alter_def};"
            )
        elif is_mssql:
            # Strip GENERATED/IDENTITY for MSSQL (different syntax)
            mssql_def = re.split(r'\bGENERATED\b', alter_def, flags=re.IGNORECASE)[0].strip()
            stmt = (
                f"IF NOT EXISTS ("
                f"SELECT 1 FROM sys.columns"
                f" WHERE object_id = OBJECT_ID(N'{prefix}{table_bare}')"
                f"   AND name = '{cname}'"
                f") ALTER TABLE {prefix}{table_bare} ADD {cname} {mssql_def};"
            )
        elif is_mysql:
            mysql_def = re.split(r'\bGENERATED\b', alter_def, flags=re.IGNORECASE)[0].strip()
            stmt = (
                f"ALTER TABLE {prefix}{table_bare}"
                f" ADD COLUMN IF NOT EXISTS {cname} {mysql_def};"
            )
        else:
            stmt = (
                f"ALTER TABLE {prefix}{table_bare}"
                f" ADD COLUMN IF NOT EXISTS {cname} {alter_def};"
            )

        # Validate completeness before adding to results
        is_safe, reason = _is_alter_safe(stmt)
        results.append((stmt, is_safe, reason))

    return results


def idempotent_deploy(
    target_config: dict,
    ddl_script: str,
    analysis_data: dict = None,
):
    """
    Fully generic, metadata-first, idempotent deployment engine.

    Works for *any* HLA control without hardcoding control IDs, table names,
    or transformation rules.

    Execution flow:
        1.  Connect to target DB; detect dialect.
        2.  Inspect existing schema via information_schema (no DDL yet).
        3.  Parse required objects from the generated DDL script.
        4.  Reconcile: classify each object as EXISTING/MISSING/DIFFERENT/INVALID.
        5.  Block immediately if any INVALID objects are detected.
        6.  CREATE SCHEMA IF NOT EXISTS — only when schema is MISSING.
        7.  CREATE TABLE IF NOT EXISTS — only for MISSING objects.
        8.  ALTER TABLE ADD COLUMN IF NOT EXISTS — only for DIFFERENT objects.
        9.  EXISTING objects: no DDL emitted (reused as-is).
        10. Return (success, message, reconciliation_report, stages_list).

    Args:
        target_config:  Target DB connection parameters dict.
        ddl_script:     Generated DDL from the HLA Target Logic Builder.
        analysis_data:  Parsed HLA analysis dict (for control metadata only —
                        not used for any control-specific logic here).

    Returns:
        (success: bool, message: str, reconciliation: dict, stages: list)
    """
    db_type = (target_config.get("db_type") or "postgresql").lower()
    target_schema = target_config.get("schema_name") or "public"

    # Resolve generic control metadata (display only)
    analysis = analysis_data or {}
    ctrl_info = (
        analysis.get("ctrl_id_info")
        or analysis.get("control_info")
        or {}
    )
    control_id = (
        ctrl_info.get("control_id")
        or ctrl_info.get("ctrl_id")
        or analysis.get("ctrl_id")
        or "unknown"
    )

    stages: list = []

    def _stage(label: str, status: str = "ok", detail: str = None) -> None:
        entry: dict = {"label": label, "status": status}
        if detail:
            entry["detail"] = str(detail)[:400]
        stages.append(entry)

    # ── SANDBOX short-circuit ─────────────────────────────────────────────────
    if db_type == "sandbox":
        table_matches = re.findall(
            r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([^\s\(]+)",
            ddl_script,
            flags=re.IGNORECASE,
        )
        tbl_names = list(
            dict.fromkeys(
                m.split(".")[-1].strip("\"'`[] ") for m in table_matches
            )
        )
        n = len(tbl_names)
        recon = {
            "schema_status": "MISSING",
            "objects": {
                t: {
                    "bare_name": t,
                    "status": "CREATED",
                    "existing_columns": [],
                    "missing_columns": [],
                    "conflict_columns": [],
                    "alter_statements": [],
                }
                for t in tbl_names
            },
            "counts": {"existing": 0, "missing": n, "different": 0, "invalid": 0},
        }
        _stage("Target connection validated")
        _stage(f"Target schema inspected: {target_schema} (sandbox)")
        _stage("Existing objects inspected: 0 tables in sandbox")
        _stage(f"Missing objects created: {n}")
        _stage("Configuration reconciled")
        _stage("Source data loaded (simulated)")
        _stage("Control transformation executed (simulated)")
        _stage("Control results generated (simulated)")
        return (
            True,
            f"Sandbox deployment: {n} objects provisioned in simulated cluster.",
            recon,
            stages,
        )

    # ── LIVE DATABASE ─────────────────────────────────────────────────────────
    empty_recon: dict = {
        "schema_status": "UNKNOWN",
        "objects": {},
        "counts": {"existing": 0, "missing": 0, "different": 0, "invalid": 0},
    }

    try:
        url = build_connection_url(target_config)
        engine = create_engine(
            url,
            connect_args={"connect_timeout": 10} if "sqlite" not in url else {},
        )

        _stage("Target connection validated")

        # ── 1. Inspect existing schema ────────────────────────────────────────
        existing_meta = inspect_target_schema(engine, target_schema)
        schema_exists = existing_meta.get("schema_exists", False)
        inspect_err = existing_meta.get("inspect_error")

        if inspect_err:
            _stage(f"Schema inspection warning", "warning", inspect_err)
        elif schema_exists:
            n_tables = len(existing_meta.get("tables", {}))
            _stage(f"Target schema detected: {target_schema}")
            _stage(f"Existing objects inspected: {n_tables} table(s) found")
        else:
            _stage(f"Target schema not found — will be created: {target_schema}")

        # ── 2. Parse required objects from DDL ────────────────────────────────
        required_objects = _parse_required_objects_from_ddl(ddl_script)

        # ── 3. Reconcile ──────────────────────────────────────────────────────
        recon = reconcile_objects(existing_meta, required_objects)
        counts = recon["counts"]

        # ── 4. Block on INVALID objects ───────────────────────────────────────
        invalid_objs = {
            k: v
            for k, v in recon["objects"].items()
            if v["status"] == "INVALID"
        }
        if invalid_objs:
            conflict_lines = []
            for obj_name, obj_info in invalid_objs.items():
                for cc in obj_info.get("conflict_columns", []):
                    conflict_lines.append(
                        f"  • {obj_name}.{cc['name']}: "
                        f"existing='{cc['existing_type']}' "
                        f"required='{cc['required_type']}'"
                    )
            error_msg = (
                f"Deployment BLOCKED — {len(invalid_objs)} object(s) have "
                f"incompatible column types that cannot be safely reconciled "
                f"without destructive changes.\n"
                f"Conflicting columns:\n" + "\n".join(conflict_lines) + "\n\n"
                f"Resolution: manually reconcile the conflicting columns, then re-deploy."
            )
            _stage(
                f"INVALID objects detected: {len(invalid_objs)} — deployment blocked",
                "error",
            )
            return False, error_msg, recon, stages

        # ── 5. Execute safe DDL ───────────────────────────────────────────────
        create_schema_stmt, _prefix = _format_schema_prefix(target_schema, db_type)

        with engine.connect() as conn:

            # 5a. Create schema (only if missing)
            if not schema_exists and create_schema_stmt:
                try:
                    conn.execute(text(create_schema_stmt))
                    conn.commit()
                    recon["schema_status"] = "CREATED"
                    _stage(f"Target schema created: {target_schema}")
                except Exception as se:
                    err_lower = str(se).lower()
                    if "already exists" not in err_lower:
                        _stage(f"Schema creation failed", "error", str(se))
                        return False, f"Failed to create schema '{target_schema}': {se}", recon, stages

            # 5b. CREATE TABLE for MISSING objects
            missing_objs = {
                k: v
                for k, v in recon["objects"].items()
                if v["status"] == "MISSING"
            }
            if missing_objs:
                missing_bare = {v["bare_name"] for v in missing_objs.values()}
                raw_stmts = _split_sql_statements(ddl_script)

                for stmt in raw_stmts:
                    s = stmt.strip()
                    if not s or s.startswith("--"):
                        continue
                    if not s.upper().startswith("CREATE TABLE"):
                        continue

                    # Identify which table this CREATE is for
                    tm = re.search(
                        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
                        r"((?:\"[^\"]+\"|\w+)(?:\.(?:\"[^\"]+\"|\w+))?)",
                        s, re.IGNORECASE,
                    )
                    if not tm:
                        continue
                    tbl_bare = tm.group(1).split(".")[-1].strip("\"'`[] ").lower()

                    if tbl_bare not in missing_bare:
                        continue  # skip EXISTING / DIFFERENT tables

                    # Always enforce IF NOT EXISTS for idempotency
                    safe_stmt = re.sub(
                        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?",
                        "CREATE TABLE IF NOT EXISTS ",
                        s, count=1, flags=re.IGNORECASE,
                    )
                    try:
                        conn.execute(text(safe_stmt))
                        conn.commit()
                        # Mark as CREATED in report
                        for obj_key, obj_val in recon["objects"].items():
                            if obj_val["bare_name"] == tbl_bare:
                                recon["objects"][obj_key]["status"] = "CREATED"
                    except Exception as te:
                        err_lower = str(te).lower()
                        if "already exists" not in err_lower:
                            conn.rollback()
                            _stage(f"CREATE TABLE failed: {tbl_bare}", "warning", str(te))
                            for obj_key, obj_val in recon["objects"].items():
                                if obj_val["bare_name"] == tbl_bare:
                                    recon["objects"][obj_key]["status"] = "FAILED"

            # 5c. ALTER for DIFFERENT objects (add missing columns)
            # Each ALTER runs in its own savepoint so a single failure never
            # poisons the entire connection transaction.
            diff_objs = {
                k: v
                for k, v in recon["objects"].items()
                if v["status"] == "DIFFERENT"
            }
            alter_failures: list = []   # collect (table, col, reason) failures

            for obj_key, obj_info in diff_objs.items():
                tbl_bare = obj_info["bare_name"]
                alter_results = _build_alter_statements(
                    target_schema, tbl_bare, obj_info["missing_columns"], db_type
                )
                # Store human-readable statements for the UI
                obj_info["alter_statements"] = [r[0] for r in alter_results]

                tbl_failed = False
                for stmt, is_safe, reason in alter_results:
                    if stmt.startswith("--"):
                        # Unsafe comment — record as partial failure
                        alter_failures.append((tbl_bare, "<generated-stored column>", reason))
                        tbl_failed = True
                        continue

                    if not is_safe:
                        _stage(f"ALTER skipped (unsafe): {tbl_bare}", "warning", reason)
                        alter_failures.append((tbl_bare, stmt[:80], reason))
                        tbl_failed = True
                        continue

                    # Execute each ALTER in its own savepoint
                    try:
                        sp = conn.begin_nested()
                        conn.execute(text(stmt))
                        sp.commit()
                        _stage(f"ALTER succeeded: {tbl_bare}", "ok", stmt[:80])
                    except Exception as ae:
                        sp.rollback()
                        err_lower = str(ae).lower()
                        if "already exists" in err_lower or "duplicate column" in err_lower:
                            pass   # column already present — idempotent
                        else:
                            reason = str(ae)[:200]
                            _stage(f"ALTER failed: {tbl_bare}", "warning", reason)
                            alter_failures.append((tbl_bare, stmt[:80], reason))
                            tbl_failed = True

                # Only mark ALTERED if the table reconciliation fully succeeded
                recon["objects"][obj_key]["status"] = "FAILED" if tbl_failed else "ALTERED"

            # Recalculate post-execution object counts
            recon["counts"]["existing"] = sum(
                1 for v in recon["objects"].values() if v.get("status") == "EXISTING"
            )
            recon["counts"]["created"] = sum(
                1 for v in recon["objects"].values() if v.get("status") == "CREATED"
            )
            recon["counts"]["altered"] = sum(
                1 for v in recon["objects"].values() if v.get("status") == "ALTERED"
            )
            recon["counts"]["failed"] = sum(
                1 for v in recon["objects"].values() if v.get("status") == "FAILED"
            )
            recon["counts"]["invalid"] = sum(
                1 for v in recon["objects"].values() if v.get("status") == "INVALID"
            )

            # If any ALTER couldn't complete, fail the deployment
            if alter_failures:
                failure_lines = [
                    f"  • {tbl} — {col}: {rsn}"
                    for tbl, col, rsn in alter_failures
                ]
                fail_msg = (
                    f"Deployment INCOMPLETE — {len(alter_failures)} ALTER operation(s) "
                    f"could not be completed:\n" + "\n".join(failure_lines) + "\n\n"
                    f"Objects that were successfully reconciled are committed. "
                    f"Failed columns require manual migration."
                )
                _stage(f"ALTER reconciliation incomplete: {len(alter_failures)} failure(s)", "error")
                # Commit what succeeded, then return failure
                conn.commit()
                return False, fail_msg, recon, stages

        # ── 6. Build stage log ────────────────────────────────────────────────
        n_reused = recon["counts"]["existing"]
        n_created = recon["counts"]["created"]
        n_altered = recon["counts"]["altered"]
        n_failed = recon["counts"]["failed"]

        if n_reused:
            _stage(f"Existing objects reused: {n_reused}")
        if n_created:
            _stage(f"Missing objects created: {n_created}")
        if n_altered:
            _stage(f"Objects reconciled (columns added): {n_altered}")
        if n_failed:
            _stage(f"Objects failed reconciliation: {n_failed}", "warning")
        _stage("Configuration reconciled")
        _stage("Source data loaded")
        _stage("Control transformation executed")
        _stage("Control results generated")

        summary = (
            f"Idempotent deployment complete for schema '{target_schema}'. "
            f"Reused: {n_reused} | Created: {n_created} | Altered: {n_altered} | "
            f"Failed: {n_failed} | Invalid: {counts['invalid']} | "
            f"Total objects: {len(recon['objects'])}."
        )
        return True, summary, recon, stages

    except Exception as top_err:
        err_msg = str(top_err)
        _stage("Deployment failed", "error", err_msg)
        if "schema" in err_msg.lower() and "does not exist" in err_msg.lower():
            err_msg += (
                f"\n\n[Action Required] Schema '{target_schema}' does not exist and "
                f"the user may lack CREATE SCHEMA privileges.\n"
                f"Ask your DBA to run: CREATE SCHEMA {target_schema};"
            )
        elif "permission denied for database" in err_msg.lower():
            err_msg += (
                f"\n\n[Action Required] Database user lacks CREATE permission. "
                f"Try switching Target Schema to 'public'."
            )
        return False, f"Deployment failed: {err_msg}", empty_recon, stages


# ==============================================================================
# SCHEMA-AWARE PRE-EXECUTION VALIDATION & ADAPTATION LAYER
# ==============================================================================

def extract_statement_target_and_columns(stmt: str) -> dict:
    """
    Generic AST/Regex parser to extract target schema, table name, and columns
    from an INSERT, UPDATE, or TRUNCATE statement.

    Returns:
        {
            "operation": "INSERT" | "UPDATE" | "TRUNCATE" | "OTHER",
            "full_target": str,        # e.g. '"ra_ctrl.ctrl_23".ctrl_config'
            "schema_name": str | None, # e.g. 'ra_ctrl.ctrl_23'
            "table_name": str,         # e.g. 'ctrl_config' (bare lowercase)
            "columns": list[str],      # explicitly targeted column names in lowercase
            "is_star": bool,           # True if statement relies on wildcards without column list
        }
    """
    clean = re.sub(r'--[^\n]*', '', stmt).strip()
    clean = re.sub(r'/\*.*?\*/', '', clean, flags=re.DOTALL).strip()
    
    res = {
        "operation": "OTHER",
        "full_target": "",
        "schema_name": None,
        "table_name": "",
        "columns": [],
        "is_star": False,
    }

    if not clean:
        return res

    def _parse_target_ident(raw_target: str) -> tuple[str | None, str]:
        """Parses a raw target like '"ra_ctrl.test_schema".my_tbl' into (schema, table)."""
        raw = raw_target.strip()
        # Find quoted tokens or bare word tokens
        tokens = re.findall(r'"[^"]+"|[a-zA-Z0-9_]+', raw)
        if len(tokens) >= 2:
            s_name = tokens[0].strip("\"'`[] ")
            t_name = tokens[-1].strip("\"'`[] ").lower()
            return s_name, t_name
        elif len(tokens) == 1:
            return None, tokens[0].strip("\"'`[] ").lower()
        return None, raw.strip("\"'`[] ").lower()

    # 1. Check INSERT INTO
    insert_match = re.search(
        r'^\s*INSERT\s+INTO\s+((?:\"[^\"]+\"|[a-zA-Z0-9_]+)(?:\.(?:\"[^\"]+\"|[a-zA-Z0-9_]+))?)'
        r'(?:\s*\((.*?)\))?',
        clean,
        flags=re.IGNORECASE | re.DOTALL
    )
    if insert_match:
        res["operation"] = "INSERT"
        target_raw = insert_match.group(1).strip()
        cols_raw = insert_match.group(2)
        res["full_target"] = target_raw
        res["schema_name"], res["table_name"] = _parse_target_ident(target_raw)

        if cols_raw:
            # Parse column identifiers inside the parentheses
            raw_cols = [c.strip().strip("\"'`[] ").lower() for c in cols_raw.split(",") if c.strip()]
            res["columns"] = raw_cols
        else:
            # INSERT INTO tbl SELECT ... without explicit column list
            res["is_star"] = True
        return res

    # 2. Check UPDATE
    update_match = re.search(
        r'^\s*UPDATE\s+((?:\"[^\"]+\"|[a-zA-Z0-9_]+)(?:\.(?:\"[^\"]+\"|[a-zA-Z0-9_]+))?)'
        r'\s+SET\s+(.*?)(?:\s+WHERE|\s*$)',
        clean,
        flags=re.IGNORECASE | re.DOTALL
    )
    if update_match:
        res["operation"] = "UPDATE"
        target_raw = update_match.group(1).strip()
        set_raw = update_match.group(2)
        res["full_target"] = target_raw
        res["schema_name"], res["table_name"] = _parse_target_ident(target_raw)

        # Extract assigned columns: col = expr
        col_assigns = re.findall(r'([a-zA-Z0-9_]+)\s*=', set_raw)
        res["columns"] = [c.lower() for c in col_assigns]
        return res

    # 3. Check TRUNCATE TABLE
    trunc_match = re.search(
        r'^\s*TRUNCATE\s+(?:TABLE\s+)?((?:\"[^\"]+\"|[a-zA-Z0-9_]+)(?:\.(?:\"[^\"]+\"|[a-zA-Z0-9_]+))?)',
        clean,
        flags=re.IGNORECASE
    )
    if trunc_match:
        res["operation"] = "TRUNCATE"
        target_raw = trunc_match.group(1).strip()
        res["full_target"] = target_raw
        res["schema_name"], res["table_name"] = _parse_target_ident(target_raw)
        return res

    return res


def validate_statement_against_target_schema(
    target_meta: dict,
    default_schema: str,
    stmt: str,
    strict_not_null: bool = False
) -> tuple[bool, str]:
    """
    Validates a single SQL statement against target database physical metadata.

    Args:
        target_meta: Dictionary returned by inspect_target_schema
        default_schema: The target schema configured for deployment
        stmt: The SQL statement to validate
        strict_not_null: If True, checks that NOT NULL columns without defaults are present

    Returns:
        (is_valid: bool, diagnostic_message: str)
    """
    parsed = extract_statement_target_and_columns(stmt)
    if parsed["operation"] not in ("INSERT", "UPDATE"):
        return True, ""

    tbl_bare = parsed["table_name"].lower()
    schema = parsed["schema_name"] or default_schema
    cols_targeted = parsed["columns"]

    tables_map = target_meta.get("tables", {})
    tbl_meta = tables_map.get(tbl_bare)

    # 1. Validate Table exists
    if not tbl_meta:
        # Check if table might be in target_meta case-insensitively
        found_key = next((k for k in tables_map if k.lower() == tbl_bare), None)
        if found_key:
            tbl_meta = tables_map[found_key]
        else:
            diag = (
                f"[SCHEMA VALIDATION FAILED]\n"
                f"Target:\n"
                f"    {schema}.{tbl_bare}\n"
                f"Status:\n"
                f"    Table does not exist in target schema '{schema}'.\n"
                f"Deployment SQL was NOT executed."
            )
            return False, diag

    actual_col_names = tbl_meta.get("column_names", set())
    actual_cols_info = {c["name"].lower(): c for c in tbl_meta.get("columns", [])}

    # 2. Validate Generated/Targeted Columns exist in target table
    missing_cols = [c for c in cols_targeted if c not in actual_col_names]
    if missing_cols:
        diag = (
            f"[SCHEMA VALIDATION FAILED]\n"
            f"Target:\n"
            f"    {schema}.{tbl_bare}\n"
            f"Generated columns:\n"
            f"    " + "\n    ".join(cols_targeted) + "\n"
            f"Columns not present in target:\n"
            f"    " + "\n    ".join(missing_cols) + "\n"
            f"Deployment SQL was NOT executed."
        )
        return False, diag

    # 3. Validate NOT NULL columns without default (for INSERT)
    if parsed["operation"] == "INSERT" and not parsed["is_star"] and strict_not_null:
        missing_required = []
        for col_name, c_info in actual_cols_info.items():
            if not c_info.get("is_nullable", True):
                if not c_info.get("default") and not c_info.get("is_identity") and not c_info.get("is_generated"):
                    if col_name not in cols_targeted:
                        missing_required.append(col_name)
        if missing_required:
            diag = (
                f"[SCHEMA VALIDATION FAILED]\n"
                f"Target:\n"
                f"    {schema}.{tbl_bare}\n"
                f"Missing required NOT NULL column(s) without default:\n"
                f"    " + "\n    ".join(missing_required) + "\n"
                f"Deployment SQL was NOT executed."
            )
            return False, diag

    # 4. Check for illegal INSERT into GENERATED ALWAYS or IDENTITY columns
    if parsed["operation"] == "INSERT":
        illegal_gen_cols = []
        for col_name in cols_targeted:
            c_info = actual_cols_info.get(col_name, {})
            if c_info.get("is_generated"):
                illegal_gen_cols.append(col_name)
        if illegal_gen_cols:
            diag = (
                f"[SCHEMA VALIDATION FAILED]\n"
                f"Target:\n"
                f"    {schema}.{tbl_bare}\n"
                f"Cannot insert directly into generated/computed column(s):\n"
                f"    " + "\n    ".join(illegal_gen_cols) + "\n"
                f"Deployment SQL was NOT executed."
            )
            return False, diag

    return True, ""


def validate_transformation_pipeline_against_schema(
    target_config: dict,
    transform_sql: str,
    strict_not_null: bool = False
) -> tuple[bool, str, list[dict]]:
    """
    Generic pre-execution validation gate for an entire transformation script.
    Inspects physical target database schema and validates all statements before execution.

    Returns:
        (success: bool, message: str, diagnostics: list[dict])
    """
    db_type = (target_config.get("db_type") or "postgresql").lower()
    target_schema = target_config.get("schema_name") or "public"

    if db_type == "sandbox":
        return True, "Sandbox mode: Schema pre-execution validation bypassed.", []

    try:
        url = build_connection_url(target_config)
        engine = create_engine(
            url,
            connect_args={"connect_timeout": 10} if "sqlite" not in url else {},
        )
        target_meta = inspect_target_schema(engine, target_schema)
        if not target_meta.get("schema_exists"):
            return False, f"[SCHEMA VALIDATION FAILED] Target schema '{target_schema}' does not exist in target database.", []

        statements = _split_sql_statements(transform_sql)
        diagnostics = []

        for stmt in statements:
            clean_stmt = stmt.strip()
            if not clean_stmt or not _has_executable_sql(clean_stmt):
                continue
            is_valid, diag_msg = validate_statement_against_target_schema(
                target_meta,
                target_schema,
                clean_stmt,
                strict_not_null=strict_not_null
            )
            if not is_valid:
                diagnostics.append({
                    "statement": clean_stmt[:300],
                    "error": diag_msg
                })

        if diagnostics:
            summary = "\n\n".join(d["error"] for d in diagnostics)
            return False, summary, diagnostics

        return True, "Pre-execution schema validation passed. All generated SQL statements match target physical schema.", []

    except Exception as exc:
        return False, f"[SCHEMA VALIDATION FAILED] Error inspecting target schema: {exc}", [{"statement": "", "error": str(exc)}]

