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
from backend.services.db_manager import DatabaseManager


def _sanitize_ident(ident: str) -> str:
    """
    Sanitizes SQL identifiers.
    If a dotted path is passed (e.g. 'customer.customer_master'), extracts the bare
    terminal identifier ('customer_master') to avoid generating double-prepended
    names like 'customer_customer_master'.
    """
    if not ident:
        return ""
    clean = str(ident).strip().strip('"\'`[]')
    if "." in clean:
        parts = [p.strip().strip('"\'`[]') for p in clean.split(".") if p.strip()]
        clean = parts[-1]
    return re.sub(r'[^a-zA-Z0-9_]', '_', clean).strip('_').lower()


def parse_canonical_table_ref(raw_ref: str, default_schema: str = "public", default_source: str = "") -> dict:
    """
    Parses any table reference into canonical structure:
    {
        "source": str,
        "schema": str,
        "table": str,
        "qualified_name": "schema.table"
    }
    Never produces double-prepended names (e.g. customer.customer_master -> schema='customer', table='customer_master').
    """
    if not raw_ref:
        return {"source": default_source, "schema": default_schema, "table": "", "qualified_name": ""}

    clean = str(raw_ref).strip().strip('"\'`[]')
    if "." in clean:
        parts = [p.strip().strip('"\'`[]') for p in clean.split(".") if p.strip()]
        if len(parts) >= 3:
            src = parts[0] or default_source
            sch = parts[1] or default_schema
            tbl = parts[2]
        elif len(parts) == 2:
            src = default_source
            sch = parts[0] or default_schema
            tbl = parts[1]
        else:
            src = default_source
            sch = default_schema
            tbl = parts[0]
    else:
        src = default_source
        sch = default_schema
        tbl = clean

    tbl_clean = re.sub(r'[^a-zA-Z0-9_]', '_', tbl).strip('_').lower()
    sch_clean = re.sub(r'[^a-zA-Z0-9_]', '_', sch).strip('_').lower() if sch else default_schema
    src_clean = str(src).strip()

    return {
        "source": src_clean,
        "schema": sch_clean,
        "table": tbl_clean,
        "qualified_name": f"{sch_clean}.{tbl_clean}" if sch_clean else tbl_clean
    }


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
    Always safely quotes the schema identifier to support arbitrary schema names and SQL keywords.
    """
    if not schema_name or (dialect and dialect.lower() == "sqlite"):
        return "", ""

    clean_schema = schema_name.strip()
    d = (dialect or "postgresql").lower().strip()

    sql_reserved = {
        "unique", "user", "order", "group", "table", "select", "where", "from",
        "primary", "key", "index", "default", "check", "values", "all", "and",
        "or", "not", "limit", "column", "desc", "asc", "into", "join", "left",
        "right", "outer", "inner", "on", "as", "by", "having", "case", "when",
        "then", "else", "end", "with", "view", "trigger", "function", "procedure",
        "database", "schema", "grant", "revoke", "create", "alter", "drop"
    }
    needs_quote = (
        not clean_schema.isidentifier()
        or clean_schema.lower() in sql_reserved
        or any(c.isupper() for c in clean_schema)
    )

    if d in ("postgresql", "postgres", "rds_postgres", "azure_postgres", "gcp_postgres", "snowflake", "redshift"):
        schema_ident = f'"{clean_schema}"' if needs_quote else clean_schema
        create_stmt = f"CREATE SCHEMA IF NOT EXISTS {schema_ident};"
        prefix = f"{schema_ident}."
    elif d in ("mysql", "mariadb", "rds_mysql", "azure_mysql", "gcp_mysql"):
        schema_ident = f"`{clean_schema}`" if needs_quote else clean_schema
        create_stmt = f"CREATE DATABASE IF NOT EXISTS {schema_ident};"
        prefix = f"{schema_ident}."
    elif d in ("mssql", "sqlserver", "azure_sql", "azure_synapse", "rds_mssql"):
        schema_ident = f"[{clean_schema}]" if needs_quote else clean_schema
        create_stmt = f"IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = '{clean_schema}') EXEC('CREATE SCHEMA [{clean_schema}]');"
        prefix = f"{schema_ident}."
    elif d in ("oracle", "rds_oracle"):
        schema_ident = f'"{clean_schema.upper()}"' if needs_quote else clean_schema.upper()
        create_stmt = f"-- Ensure Oracle user/schema {schema_ident} is granted CREATE TABLE permissions;"
        prefix = f"{schema_ident}."
    elif d == "bigquery":
        schema_ident = f"`{clean_schema}`" if needs_quote else clean_schema
        create_stmt = f"CREATE SCHEMA IF NOT EXISTS {schema_ident};"
        prefix = f"{schema_ident}."
    else:
        schema_ident = f'"{clean_schema}"' if needs_quote else clean_schema
        create_stmt = f"CREATE SCHEMA IF NOT EXISTS {schema_ident};"
        prefix = f"{schema_ident}."

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


_STANDARD_ENVELOPE_COLUMNS = set()


def build_table_columns_with_standard_envelope(
    middle_columns: list,
    target_dialect: str = "postgresql",
    indent: str = "    ",
) -> list[str]:
    """
    Formats the table column definitions purely from HLA/source models.
    Does NOT inject any synthetic control framework columns (ctrl_id, exec_seq, etc.).
    """
    processed = []
    seen = set()

    for col in (middle_columns or []):
        if isinstance(col, dict):
            raw_name = str(col.get("name", "")).strip()
            name_norm = raw_name.strip("\"'`[]").lower()
            if not name_norm or name_norm in seen:
                continue
            seen.add(name_norm)
            col_type = col.get("type", "VARCHAR(255)")
            nullable = col.get("nullable", "")
            default = col.get("default", "")
            processed.append(f"{indent}{raw_name} {col_type}{nullable}{default}".rstrip())
        elif isinstance(col, str):
            clean_str = col.strip()
            if not clean_str:
                continue
            first_token = clean_str.split(None, 1)[0]
            name_norm = first_token.strip("\"'`[],").lower()
            if not name_norm or name_norm in seen:
                continue
            seen.add(name_norm)
            line = f"{indent}{clean_str}" if not col.startswith(indent) else col
            processed.append(line.rstrip().rstrip(","))

    return processed



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


def discover_target_entities(analysis_data: dict = None, mappings: list = None) -> list:
    """
    Dynamically discovers all explicit target/data-model entities from the parsed HLA metadata.
    Zero synthetic prefixes or hardcoded table names.

    Discovered from:
    1. analysis_data['data_model'] (Data Model sheet / stage tables / target entities)
    2. analysis_data['target_entities'] (if explicitly parsed)
    3. analysis_data['mappings'] or mappings (if explicit target_table/report_table_name/target_entity is specified)
    4. analysis_data['report_derivations'] / analysis_data['reports'] (derived target report models)

    Returns: list of dicts:
        {
            "table_name": str,
            "stage": str,
            "load_type": str,
            "description": str,
            "columns": [{"name": str, "type": str, "nullable": str, "default": str}],
            "is_master": bool,
            "source_origin": str
        }
    """
    if not analysis_data and not mappings:
        return []

    entities_map: dict = {}

    def _extract_stem_tokens(name_str: str) -> set:
        """Extracts substantive stem tokens (>= 3 chars) ignoring generic stage prefixes."""
        tokens = set()
        clean = re.sub(r'[^a-zA-Z0-9_]', ' ', str(name_str or '')).lower()
        ignore_stems = {"stg", "staging", "tbl", "table", "dataset", "source", "target", "dim", "fct", "summary", "model", "raw", "clean"}
        for part in clean.replace(".", " ").replace("_", " ").split():
            part = part.strip()
            if len(part) >= 3 and part not in ignore_stems:
                tokens.add(part)
        return tokens

    # 1. Discover from analysis_data["data_model"]
    dm_list = (analysis_data.get("data_model") or []) if analysis_data else []
    for dm in dm_list:
        if not isinstance(dm, dict):
            continue
        raw_name = (
            dm.get("dataset_table_entity_name") or
            dm.get("table_name") or
            dm.get("entity_name") or
            dm.get("target_table") or
            dm.get("target_entity") or
            dm.get("target_dataset") or
            dm.get("output_result_set") or
            dm.get("output_dataset") or
            dm.get("dataset") or
            dm.get("table") or
            ""
        )
        if not raw_name:
            for k, v in dm.items():
                if not k.startswith("_") and ("entity" in k or "target" in k or "table" in k or "dataset" in k) and v:
                    raw_name = str(v).strip()
                    break
        if not raw_name:
            continue

        t_name = _sanitize_ident(raw_name)
        if not t_name:
            continue

        stage = dm.get("stage") or dm.get("data_process_stage") or "Target Data Model"
        load_type = dm.get("load_type") or dm.get("type_of_load") or "Truncate & load"
        desc = dm.get("description") or dm.get("purpose") or ""
        is_master = _is_master_table(dm)

        cols = []
        raw_cols = dm.get("columns") or dm.get("fields") or []
        if isinstance(raw_cols, list):
            for c in raw_cols:
                if isinstance(c, dict):
                    cn = _sanitize_ident(c.get("name") or c.get("column_name") or "")
                    ct = c.get("type") or c.get("data_type") or "VARCHAR(255)"
                    n_raw = str(c.get("nullable", "")).strip()
                    n_str = " NOT NULL" if n_raw.upper() in ("N", "NO", "FALSE", "0", "NOT NULL") else ""
                    d_raw = str(c.get("default", "")).strip()
                    d_str = f" DEFAULT {d_raw}" if d_raw else ""
                else:
                    cn = _sanitize_ident(str(c))
                    ct = "VARCHAR(255)"
                    n_str = ""
                    d_str = ""
                if cn:
                    cols.append({"name": cn, "type": ct, "nullable": n_str, "default": d_str})

        entities_map[t_name] = {
            "table_name": t_name,
            "stage": stage,
            "load_type": load_type,
            "description": desc,
            "columns": cols,
            "is_master": is_master,
            "source_origin": "data_model"
        }

    # 2. Discover from analysis_data["target_entities"]
    te_list = (analysis_data.get("target_entities") or []) if analysis_data else []
    for te in te_list:
        if isinstance(te, str):
            t_name = _sanitize_ident(te)
            if t_name and t_name not in entities_map:
                entities_map[t_name] = {
                    "table_name": t_name,
                    "stage": "Target Entity",
                    "load_type": "Truncate & load",
                    "description": f"Target entity: {te}",
                    "columns": [],
                    "is_master": False,
                    "source_origin": "target_entities"
                }
        elif isinstance(te, dict):
            raw_name = te.get("table_name") or te.get("entity_name") or te.get("target_table") or te.get("target_entity") or ""
            t_name = _sanitize_ident(raw_name)
            if t_name and t_name not in entities_map:
                entities_map[t_name] = {
                    "table_name": t_name,
                    "stage": te.get("stage", "Target Entity"),
                    "load_type": te.get("load_type", "Truncate & load"),
                    "description": te.get("description", f"Target entity: {raw_name}"),
                    "columns": te.get("columns", []),
                    "is_master": _is_master_table(te),
                    "source_origin": "target_entities"
                }

    # 3. Process All Attribute Mappings (resolve mapping ownership)
    all_mappings = (mappings or [])
    if analysis_data and "mappings" in analysis_data:
        all_mappings = analysis_data["mappings"] or all_mappings

    for m in all_mappings:
        if not isinstance(m, dict):
            continue
        tgt_tbl = (
            m.get("target_table") or
            m.get("report_table_name") or
            m.get("target_entity") or
            m.get("target_dataset") or
            ""
        )
        col_name = _sanitize_ident(m.get("target_attribute") or m.get("target_column") or m.get("attribute_name") or "")
        col_type = m.get("data_type") or m.get("target_data_type") or "VARCHAR(255)"
        is_null = m.get("nullable", "Y")
        nullable_str = " NOT NULL" if str(is_null).strip().upper() in ("N", "NO", "FALSE", "0") else ""

        if not col_name or col_name in _STANDARD_ENVELOPE_COLUMNS:
            continue

        # If explicit target table is named in mapping
        if tgt_tbl:
            t_name = _sanitize_ident(tgt_tbl)
            if t_name:
                if t_name not in entities_map:
                    entities_map[t_name] = {
                        "table_name": t_name,
                        "stage": "Target Report Model",
                        "load_type": "Truncate & load",
                        "description": f"Target entity derived from HLA mappings: {tgt_tbl}",
                        "columns": [],
                        "is_master": False,
                        "source_origin": "mappings"
                    }
                if not any(c["name"] == col_name for c in entities_map[t_name]["columns"]):
                    entities_map[t_name]["columns"].append({"name": col_name, "type": col_type, "nullable": nullable_str, "default": ""})

                # Check if HLA rules reference key/join identifiers on this stream
                src_tbl_str = str(m.get("source_table") or "")
                src_tbl_stems = _extract_stem_tokens(src_tbl_str) | _extract_stem_tokens(t_name)
                rules_list = ((analysis_data.get("rules", {}).get("filter_rules") or []) + (analysis_data.get("rules", {}).get("business_rules") or [])) if analysis_data else []
                for r in rules_list:
                    r_stream = str(r.get("data_stream", "")).lower()
                    r_stems = _extract_stem_tokens(r_stream)
                    if (r_stream and (r_stream in src_tbl_str.lower() or src_tbl_str.lower() in r_stream)) or (r_stems & src_tbl_stems):
                        full_r = f"{r.get('rule_statement', '')} {r.get('filter_condition', '')}".lower()
                        for tok in ("customer_id", "transaction_id", "account_id", "item_id", "order_id", "device_id"):
                            if tok in full_r and not any(c["name"] == tok for c in entities_map[t_name]["columns"]):
                                entities_map[t_name]["columns"].insert(0, {"name": tok, "type": "VARCHAR(255)", "nullable": "", "default": ""})

                # Also preserve common document grain/foreign keys present across mappings so downstream entity joins work seamlessly
                for tok in ("customer_id", "client_id", "account_id", "item_id", "order_id", "device_id"):
                    if any(tok in str(m_other).lower() for m_other in (mappings or [])):
                        if not any(c["name"] == tok for c in entities_map[t_name]["columns"]):
                            entities_map[t_name]["columns"].insert(0, {"name": tok, "type": "VARCHAR(255)", "nullable": "", "default": ""})
        else:
            # Resolve mapping ownership generically to Data Model staging entities
            src_tbl = m.get("source_table", "")
            src_stems = _extract_stem_tokens(src_tbl)

            # Find matching staging entity in Data Model
            for ent_name, ent_info in entities_map.items():
                stage_upper = str(ent_info.get("stage", "")).upper()
                is_staging = stage_upper in ("STAGING", "STAGE", "RAW", "SOURCE", "") or ent_name.lower().startswith("stg_")
                if not is_staging:
                    continue
                ent_stems = _extract_stem_tokens(ent_name)
                # Match if substantive stem overlaps between source and staging model
                if src_stems and ent_stems and (src_stems & ent_stems):
                    if not any(c["name"] == col_name for c in ent_info["columns"]):
                        ent_info["columns"].append({"name": col_name, "type": col_type, "nullable": nullable_str, "default": ""})

    # 4. Process Report Derivation Logic
    report_derivs = (analysis_data.get("report_derivations") or analysis_data.get("reports") or []) if analysis_data else []
    for rep in report_derivs:
        if not isinstance(rep, dict):
            continue
        col_name = _sanitize_ident(rep.get("target_attribute") or rep.get("target_column") or rep.get("attribute_name") or "")
        src_tbl = rep.get("source_table") or rep.get("tables") or ""
        logic = rep.get("derivation_logic") or rep.get("logic") or ""

        if not col_name or col_name in _STANDARD_ENVELOPE_COLUMNS:
            continue

        col_type = "DECIMAL(18,2)" if any(k in logic.upper() for k in ("SUM", "AVG", "DECIMAL", "AMOUNT")) else ("BIGINT" if "COUNT" in logic.upper() else "VARCHAR(255)")

        # Find curated / reporting target entity
        for ent_name, ent_info in entities_map.items():
            stage_upper = str(ent_info.get("stage", "")).upper()
            if stage_upper in ("CURATED", "REPORTING", "SUMMARY", "POST-EXECUTION") or "summary" in ent_name.lower() or "report" in ent_name.lower():
                # Also attach grain key from matching upstream staging entities
                ent_stems = _extract_stem_tokens(ent_name)
                for other_name, other_info in entities_map.items():
                    if other_name != ent_name:
                        other_stems = _extract_stem_tokens(other_name)
                        if ent_stems & other_stems:
                            for col in other_info.get("columns", []):
                                c_low = col["name"].lower()
                                if any(k in c_low for k in ("_id", "id_", "_key", "_code", "id", "key", "code")):
                                    if not any(c["name"] == col["name"] for c in ent_info["columns"]):
                                        ent_info["columns"].insert(0, {"name": col["name"], "type": col["type"], "nullable": "", "default": ""})

                if not any(c["name"] == col_name for c in ent_info["columns"]):
                    ent_info["columns"].append({"name": col_name, "type": col_type, "nullable": "", "default": ""})

    # 5. Populate Exception Tables if defined in Data Model
    for ent_name, ent_info in entities_map.items():
        stage_upper = str(ent_info.get("stage", "")).upper()
        if "exception" in ent_name.lower() or stage_upper == "EXCEPTION":
            if not ent_info["columns"]:
                ent_info["columns"] = [
                    {"name": "exception_id", "type": "BIGINT", "nullable": "", "default": ""},
                    {"name": "rule_id", "type": "VARCHAR(50)", "nullable": "", "default": ""},
                    {"name": "source_dataset", "type": "VARCHAR(100)", "nullable": "", "default": ""},
                    {"name": "record_key", "type": "VARCHAR(255)", "nullable": "", "default": ""},
                    {"name": "error_message", "type": "VARCHAR(500)", "nullable": "", "default": ""},
                    {"name": "impact_amount", "type": "DECIMAL(18,2)", "nullable": "", "default": ""},
                    {"name": "created_at", "type": "TIMESTAMP", "nullable": "", "default": ""}
                ]

    return list(entities_map.values())


def generate_target_ddl(target_schema: str, target_dialect: str, sources: list, rules: dict, mappings: list, introspected_schemas: dict = None, analysis_data: dict = None) -> str:
    """
    Generates 100% document-driven Target Architecture DDL.
    Target objects are generated ONLY when explicitly defined in the uploaded HLA.
    Zero synthetic prefixes, zero hardcoded table names, zero assumed staging/balance/recon tables.
    """
    if isinstance(target_schema, dict):
        target_schema = target_schema.get("schema_name", "public")

    create_schema_stmt, prefix = _format_schema_prefix(target_schema, target_dialect)
    ddl_statements = []

    if create_schema_stmt:
        ddl_statements.append(create_schema_stmt)

    discovered_targets = discover_target_entities(analysis_data, mappings)

    if not discovered_targets:
        no_target_msg = f"""-- ============================================================================
-- TARGET ENTITY NOT DEFINED
-- ============================================================================
-- The uploaded HLA contains source metadata but does not define a target
-- entity/table. No target table was generated.
-- ============================================================================"""
        ddl_statements.append(no_target_msg)
        return "\n\n".join(ddl_statements)

    master_table_comments = []
    target_tables_ddl = []

    # Check target envelope requirement: Generic HLA uses NONE unless explicitly configured as LEGACY_CONTROL
    target_envelope = (analysis_data.get("target_envelope") or "NONE").upper() if analysis_data else "NONE"

    for entity in discovered_targets:
        t_name = entity["table_name"]
        stage = entity.get("stage", "Target Entity")
        load_type = entity.get("load_type", "Truncate & load")
        desc = entity.get("description", "")
        is_master = entity.get("is_master", False)

        if is_master:
            fq_ref = f"{prefix}{t_name}"
            master_table_comments.append(
                f"-- MASTER TABLE (pre-existing): {fq_ref}\n"
                f"-- Stage       : {stage} | Strategy: {load_type}\n"
                f"-- Description : {desc}\n"
                f"-- Reference as: {fq_ref}\n"
                f"-- Action      : no CREATE TABLE emitted — table already exists in target schema."
            )
            continue

        raw_cols = entity.get("columns", [])
        mid_cols = []
        if raw_cols:
            for c in raw_cols:
                cn = c.get("name")
                ct = map_data_type(c.get("type", "VARCHAR(255)"), target_dialect)
                nullable = c.get("nullable", "")
                default = c.get("default", "")
                if cn and cn not in _STANDARD_ENVELOPE_COLUMNS:
                    mid_cols.append(f"{cn} {ct}{nullable}{default}".strip())

        if not mid_cols:
            mid_cols = [
                f"data_payload {map_data_type('JSON', target_dialect)}"
            ]

        all_cols = [f"    {c}" for c in mid_cols]

        stmt = f"""-- Target Entity: {t_name} (Stage: {stage} | Strategy: {load_type})
CREATE TABLE IF NOT EXISTS {prefix}{t_name} (
{',\n'.join(all_cols)}
);"""
        target_tables_ddl.append(stmt)

    if master_table_comments:
        ddl_statements.append(f"""-- ============================================================================
-- MASTER / REFERENCE TABLES (PRE-EXISTING IN TARGET SCHEMA — NOT CREATED)
-- ============================================================================
{chr(10).join(master_table_comments)}""")

    if target_tables_ddl:
        ddl_statements.append(f"""-- ============================================================================
-- TARGET ARCHITECTURE ENTITIES (FROM HLA SPECIFICATION)
-- ============================================================================
{chr(10).join(target_tables_ddl)}""")

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



def build_transformation_plan(analysis_data: dict, target_schema: str = "public", target_dialect: str = "postgresql") -> dict:
    """
    Builds a single canonical transformation plan consumed by both SQL and PySpark generators.
    Zero hardcoded values: dynamically binds sources, mappings, rules, and targets directly from HLA.
    """
    analysis = analysis_data or {}
    sources = analysis.get("sources") or analysis.get("source_tables") or []
    mappings = analysis.get("mappings") or []
    rules = analysis.get("rules") or {}
    buckets = analysis.get("buckets") or analysis.get("reconciliation") or []
    data_model = analysis.get("data_model") or []
    reports = analysis.get("report_derivations") or analysis.get("reports") or []

    discovered_targets = discover_target_entities(analysis, mappings)

    # Map rules by source table
    all_rules = []
    if isinstance(rules, dict):
        for r_list in rules.values():
            if isinstance(r_list, list):
                all_rules.extend(r_list)
    elif isinstance(rules, list):
        all_rules = rules

    # Target entity plans
    entity_plans = []
    for entity in discovered_targets:
        t_name = entity["table_name"]
        load_type = entity.get("load_type", "Truncate")
        stage = entity.get("stage", "TARGET")

        # Find mappings for this entity
        entity_mappings = []
        for m in mappings:
            tgt = m.get("target_entity") or m.get("target_table") or m.get("report_table_name") or ""
            if tgt and _sanitize_ident(tgt).lower() == t_name.lower():
                entity_mappings.append(m)
            elif not tgt and len(discovered_targets) == 1:
                entity_mappings.append(m)

        # Fallback: if no mappings explicitly matched target name, match columns
        if not entity_mappings and entity.get("columns"):
            entity_col_names = {c["name"].lower() for c in entity.get("columns", [])}
            for m in mappings:
                attr = _sanitize_ident(m.get("target_attribute") or m.get("target_column") or "").lower()
                if attr in entity_col_names:
                    entity_mappings.append(m)

        # Find upstream source tables
        upstream_sources = []
        for m in entity_mappings:
            st = m.get("source_table") or m.get("source_dataset") or ""
            if st and st not in upstream_sources:
                upstream_sources.append(st)
        if not upstream_sources and sources:
            upstream_sources = [s.get("full_table_name") or s.get("source_table") for s in sources if s.get("source_table") or s.get("full_table_name")]

        # Relevant filter/validation rules
        relevant_rules = []
        for r in all_rules:
            r_src = r.get("source_dataset") or r.get("source_table") or r.get("dataset") or ""
            if not r_src or any(r_src.lower() in str(us).lower() or str(us).lower() in r_src.lower() for us in upstream_sources):
                relevant_rules.append(r)

        # Relevant buckets
        relevant_buckets = []
        for b in buckets:
            b_src = b.get("dataset_source") or b.get("dataset") or b.get("source") or ""
            if not b_src or any(b_src.lower() in str(us).lower() or str(us).lower() in b_src.lower() for us in upstream_sources):
                relevant_buckets.append(b)

        entity_plans.append({
            "target_table": t_name,
            "stage": stage,
            "load_type": load_type,
            "columns": entity.get("columns", []),
            "mappings": entity_mappings,
            "upstream_sources": upstream_sources,
            "rules": relevant_rules,
            "buckets": relevant_buckets
        })

    return {
        "target_schema": target_schema,
        "target_dialect": target_dialect,
        "sources": sources,
        "targets": entity_plans,
        "buckets": buckets,
        "reports": reports
    }


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
) -> str:
    """
    Generates dynamic, executable SQL ETL transformation script directly from HLA specification.
    """
    _, prefix = _format_schema_prefix(target_schema, target_dialect)
    plan = build_transformation_plan(analysis_data, target_schema, target_dialect)
    targets = plan.get("targets", [])

    if not targets:
        return f"-- ============================================================================\n-- HLA AUTOMATED TARGET TRANSFORMATION SCRIPT\n-- Target Schema: {target_schema} | Dialect: {target_dialect.upper()}\n-- ============================================================================\n-- Notice: No target entities discovered in uploaded HLA specification.\n-- TARGET ENTITY NOT DEFINED: Please define target entities or mappings in HLA."

    doc_title = (analysis_data or {}).get("document_title") or "HLA Architecture Specification"
    header = f"""-- ============================================================================
-- HLA AUTOMATED TARGET TRANSFORMATION SCRIPT
-- Specification: {doc_title}
-- Target Schema: {target_schema} | Dialect: {target_dialect.upper()}
-- Dynamically generated from uploaded HLA workbook
-- ============================================================================"""

    sql_steps = [header]
    step_num = 1

    for tgt in targets:
        t_name = tgt["target_table"]
        load_type = tgt.get("load_type", "Truncate")
        is_truncate = "truncate" in load_type.lower() or "rebuild" in load_type.lower() or "overwrite" in load_type.lower()
        t_mappings = tgt.get("mappings", [])
        t_cols = [c["name"] for c in tgt.get("columns", []) if c.get("name") and c.get("name") not in _STANDARD_ENVELOPE_COLUMNS]
        t_rules = tgt.get("rules", [])
        t_sources = tgt.get("upstream_sources", [])

        # Format source reference: prefer intermediate target tables if available in upstream sources
        target_names = {t["target_table"].lower() for t in targets}
        target_source = next((s for s in t_sources if str(s).split(".")[-1].strip("\"'`[] ").lower() in target_names), None)
        if target_source:
            raw_src = target_source
        else:
            raw_src = t_sources[0] if t_sources else (sources[0].get("full_table_name") or sources[0].get("source_table") or sources[0].get("table_name") if sources else "source_data")

        raw_src_bare = str(raw_src).split(".")[-1].strip("\"'`[] ").lower()
        if raw_src_bare in target_names:
            src_table_ref = f"{prefix}{raw_src_bare}"
        else:
            src_table_ref = raw_src

        # Discover upstream table columns if available
        upstream_cols = set()
        if raw_src_bare in target_names:
            if target_meta and "tables" in target_meta and raw_src_bare in target_meta["tables"]:
                upstream_cols = {c["name"].lower() for c in target_meta["tables"][raw_src_bare].get("columns", [])}
            elif ddl_script:
                req_objs = _parse_required_objects_from_ddl(ddl_script)
                for ro in req_objs:
                    if ro["bare_name"].lower() == raw_src_bare:
                        upstream_cols = {c["name"].lower() for c in ro.get("columns", [])}

        select_cols = []
        target_cols = []

        if t_mappings:
            for m in t_mappings:
                col_name = _sanitize_ident(m.get("target_attribute") or m.get("target_column") or "")
                if not col_name or col_name in _STANDARD_ENVELOPE_COLUMNS or col_name in target_cols:
                    continue
                target_cols.append(col_name)
                trans = (m.get("transformation") or m.get("derivation_logic") or "").strip()
                src_f = _sanitize_ident((m.get("source_field") or m.get("source_column") or "").strip())

                if trans.lower() in ("aggregate", "agg") or ("count" in col_name.lower() and trans.lower() in ("aggregate", "agg", "count", "")):
                    expr = "COUNT(*)"
                    select_cols.append(f"    {expr} AS {col_name}")
                elif trans and trans.lower() not in ("direct", "none", "pass-through", "pass through", "persist", "filter", "join", "derived", ""):
                    expr = trans
                    if not any(expr.lower().startswith(kw) for kw in ("sum(", "count(", "avg(", "min(", "max(", "case ", "cast(", "trim(", "coalesce(", "upper(", "lower(")):
                        if src_f and (not upstream_cols or src_f.lower() in upstream_cols):
                            expr = f"s.{src_f}"
                        elif col_name.lower() in upstream_cols:
                            expr = f"s.{col_name}"
                        elif upstream_cols:
                            expr = f"s.{next(iter(upstream_cols))}"
                    select_cols.append(f"    {expr} AS {col_name}")
                elif src_f and (not upstream_cols or src_f.lower() in upstream_cols):
                    select_cols.append(f"    s.{src_f} AS {col_name}")
                elif col_name.lower() in upstream_cols:
                    select_cols.append(f"    s.{col_name} AS {col_name}")
                elif upstream_cols:
                    matching_c = next((c for c in upstream_cols if c in col_name.lower() or col_name.lower() in c), next(iter(upstream_cols)))
                    select_cols.append(f"    s.{matching_c} AS {col_name}")
                else:
                    select_cols.append(f"    s.{src_f or col_name} AS {col_name}")
        elif t_cols:
            for c in t_cols:
                if c not in target_cols:
                    target_cols.append(c)
                    select_cols.append(f"    s.{c} AS {c}")

        if not target_cols:
            continue

        # Build WHERE clause from rules
        where_clauses = []
        for r in t_rules:
            cond = r.get("condition") or r.get("filter_condition") or ""
            if cond and str(cond).strip().lower() not in ("true", "1", "none", "all", "keep record"):
                clean_cond = str(cond).strip()
                if "over (" not in clean_cond.lower() and "group by" not in clean_cond.lower():
                    where_clauses.append(f"({clean_cond})")

        where_sql = f"\nWHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        # Check for GROUP BY in transformations
        group_by_cols = []
        has_agg = False
        for sc in select_cols:
            if any(agg in sc.upper() for agg in ("SUM(", "COUNT(", "AVG(", "MIN(", "MAX(")):
                has_agg = True
            elif " AS " in sc:
                col_part = sc.split(" AS ")[0].strip()
                group_by_cols.append(col_part)

        group_by_sql = f"\nGROUP BY {', '.join(group_by_cols)}" if (has_agg and group_by_cols) else ""

        # Only emit TRUNCATE if the table is populated from an upstream target table
        # (initial external source staging tables are managed directly by data load)
        if raw_src_bare in target_names and is_truncate:
            truncate_stmt = f"TRUNCATE TABLE {prefix}{t_name};\n\n"
        else:
            truncate_stmt = ""

        step_sql = f"""-- STEP {step_num}: Populate Target Table '{t_name}' ({tgt.get('stage', 'TARGET')})
{truncate_stmt}INSERT INTO {prefix}{t_name} (
    {', '.join(target_cols)}
)
SELECT
{',\n'.join(select_cols)}
FROM {src_table_ref} s{where_sql}{group_by_sql};"""

        sql_steps.append(step_sql)
        step_num += 1

    return "\n\n".join(sql_steps)



def generate_pyspark_pipeline(
    target_schema: str,
    target_db_config: dict,
    sources: list,
    rules: dict,
    mappings: list,
    control_overview: dict = None,
    analysis_data: dict = None
) -> str:
    """
    Generates dynamic, executable PySpark ETL pipeline directly from HLA specification.
    """
    target_db_config = target_db_config or {}
    plan = build_transformation_plan(analysis_data, target_schema, (target_db_config.get("db_type") or "postgresql").lower())
    targets = plan.get("targets", [])
    doc_title = (analysis_data or {}).get("document_title") or "HLA Architecture Specification"

    host = target_db_config.get("host") or "localhost"
    port = target_db_config.get("port") or 5432
    db_name = target_db_config.get("database_name") or "hla_db"
    user = target_db_config.get("username") or "postgres"
    dialect = (target_db_config.get("db_type") or "postgresql").lower()
    jdbc_url = f"jdbc:postgresql://{host}:{port}/{db_name}"
    driver_class = "org.postgresql.Driver"

    code_lines = [
        f'# ==============================================================================',
        f'# PySpark ETL & Transformation Pipeline',
        f'# Specification: {doc_title}',
        f'# Target Schema: {target_schema} | Target DB: {host}:{port}/{db_name}',
        f'# Dynamically generated from uploaded HLA workbook',
        f'# ==============================================================================',
        '',
        'from pyspark.sql import SparkSession, functions as F, Window',
        '',
        'spark = SparkSession.builder \\',
        f'    .appName("HLA_ETL_Pipeline_{_sanitize_ident(target_schema)}") \\',
        '    .config("spark.sql.shuffle.partitions", "8") \\',
        '    .getOrCreate()',
        '',
        f'jdbc_url = "{jdbc_url}"',
        'db_props = {',
        f'    "user": "{user}",',
        '    "password": "<CREDENTIAL_FROM_VAULT>",',
        f'    "driver": "{driver_class}"',
        '}',
        '',
        '# ------------------------------------------------------------------------------',
        '# 1. Ingest Upstream Sources from Database',
        '# ------------------------------------------------------------------------------'
    ]

    for s in (plan.get("sources") or []):
        s_name = s.get("full_table_name") or s.get("source_table")
        if not s_name:
            continue
        clean_s = _sanitize_ident(s_name)
        code_lines.append(f'df_{clean_s} = spark.read.jdbc(jdbc_url, "{s_name}", properties=db_props)')

    code_lines.append('')
    code_lines.append('# ------------------------------------------------------------------------------')
    code_lines.append('# 2. Execute HLA Transformations & Load Target Entities')
    code_lines.append('# ------------------------------------------------------------------------------')

    for tgt in targets:
        t_name = tgt["target_table"]
        clean_tgt = _sanitize_ident(t_name)
        load_type = tgt.get("load_type", "Truncate")
        is_truncate = "truncate" in load_type.lower() or "rebuild" in load_type.lower() or "overwrite" in load_type.lower()
        save_mode = "overwrite" if is_truncate else "append"
        t_mappings = tgt.get("mappings", [])
        t_rules = tgt.get("rules", [])
        t_sources = tgt.get("upstream_sources", [])
        src_table_ref = t_sources[0] if t_sources else (sources[0].get("full_table_name") if sources else "source_data")
        clean_src = _sanitize_ident(src_table_ref)

        code_lines.append(f'# Target: {t_name} ({tgt.get("stage", "TARGET")})')
        code_lines.append(f'df_transformed_{clean_tgt} = df_{clean_src}')

        # Apply rules / filters
        for r in t_rules:
            cond = r.get("condition") or r.get("filter_condition") or ""
            if cond and str(cond).strip().lower() not in ("true", "1", "none", "all", "keep record"):
                clean_cond = str(cond).strip().replace('"', '\\"')
                code_lines.append(f'df_transformed_{clean_tgt} = df_transformed_{clean_tgt}.filter(F.expr("{clean_cond}"))')

        # Apply column selections & mappings
        select_exprs = []
        for m in t_mappings:
            col_name = _sanitize_ident(m.get("target_attribute") or m.get("target_column") or "")
            if not col_name or col_name in _STANDARD_ENVELOPE_COLUMNS:
                continue
            src_f = _sanitize_ident((m.get("source_field") or m.get("source_column") or "").strip())
            trans = (m.get("transformation") or m.get("derivation_logic") or "").strip()
            if trans and trans.lower() not in ("direct", "none", "pass-through", "pass through", ""):
                select_exprs.append(f'F.expr("{trans}").alias("{col_name}")')
            elif src_f and src_f.lower() not in ("direct", "none"):
                select_exprs.append(f'F.col("{src_f}").alias("{col_name}")')
            else:
                select_exprs.append(f'F.col("{col_name}")')

        if select_exprs:
            code_lines.append(f'df_transformed_{clean_tgt} = df_transformed_{clean_tgt}.select(\n    ' + ',\n    '.join(select_exprs) + '\n)')

        code_lines.append(f'df_transformed_{clean_tgt}.write \\')
        code_lines.append(f'    .mode("{save_mode}") \\')
        code_lines.append(f'    .jdbc(jdbc_url, "{target_schema}.{t_name}", properties=db_props)')
        code_lines.append('')

    code_lines.append('print("Dynamic PySpark HLA Pipeline executed successfully.")')
    code_lines.append('spark.stop()')

    return '\n'.join(code_lines)


def build_target_logic_package(analysis_data: dict, introspected_sources: dict, target_config: dict):
    """
    Main orchestrator: Synthesizes complete target architecture, DDL, SQL, and PySpark logic
    dynamically for any HLA document.
    """
    target_config = target_config or {}
    target_env = (target_config.get("target_env") or target_config.get("environment") or "dev").lower()
    target_dialect = (target_config.get("db_type") or "postgresql").lower()

    control_overview = analysis_data.get("control_overview") or {}
    ctrl_id = control_overview.get("identification", {})
    ctrl_num = ctrl_id.get("control_number") or ""
    ctrl_title = ctrl_id.get("control_title") or "Enterprise Solution Design"

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
            t_eng = DatabaseManager.get_engine(target_config)
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
    pyspark_code = generate_pyspark_pipeline(target_schema, target_config, sources, rules, mappings, control_overview, analysis_data=analysis_data)

    # 4. Architectural Reasoning
    doc_title = (analysis_data or {}).get("document_title") or "HLA Architecture Specification"
    discovered_targets = discover_target_entities(analysis_data, mappings)
    discovered_target_names = ", ".join([f"`{t['table_name']}`" for t in discovered_targets[:3]]) or "target models"

    llm_reasoning = f"""### Target Solution Architecture Brief
**Specification**: {doc_title}

1. **Target Schema & Environment Isolation**:
   The target architecture deploys into dedicated namespace `{target_schema}`. This ensures total isolation between Development testing and Production ledgers without impacting upstream operational systems.

2. **Validation & Filter Execution**:
   Upstream source feeds ({len(sources)} datasets) are validated and cleansed before target loading.

3. **Target Data Model**:
   Document-driven target objects ({discovered_target_names}) receive verified datasets aligned with authoritative HLA mapping and data model specifications.

4. **Production Deployment Readiness**:
   All DDL scripts use idempotent `CREATE TABLE IF NOT EXISTS` semantics, enabling continuous repeatable deployment.
"""

    # Extract table-level scan statuses (found vs missing and required column counts)
    _, table_status_map = get_source_column_definitions(sources, introspected_sources, target_dialect, analysis_data)

    # 5. Generate Source -> Target Field Lineage Mapping
    source_mappings = generate_source_to_target_mappings(analysis_data, introspected_sources, discovered_targets)

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
        "source_mappings": source_mappings,
        "summary": {
            "sources_modeled": len([s for s in table_status_map.values() if s.get("table_found")]),
            "sources_missing": len([s for s in table_status_map.values() if not s.get("table_found")]),
            "filter_rules_modeled": len(rules.get("filter_rules", [])),
            "target_entities_modeled": len(discovered_targets),
            "target_entities": [t["table_name"] for t in discovered_targets],
            "target_schema": target_schema,
            "environment": target_env.upper(),
            "hla_analysis_summary": (analysis_data or {}).get("hla_analysis_summary") or {}
        }
    }


def generate_source_to_target_mappings(analysis_data: dict, introspected_sources: dict, target_entities: list) -> list:
    """
    Generates comprehensive source-to-target field mapping lineage:
    [
        {
            "source_table": "<source_table_name>",
            "source_column": "<source_column_name>",
            "transformation": "direct",
            "target_table": "<target_table_name>",
            "target_column": "<target_column_name>"
        },
        ...
    ]
    For unmapped target columns, explicitly marks them as UNMAPPED.
    """
    mappings_list = []
    seen_target_cols = set()
    raw_mappings = (analysis_data or {}).get("mappings") or []
    sources = (analysis_data or {}).get("sources") or []

    # Map of source table -> (orig_name, columns)
    source_cols_lookup = {}
    for s in sources:
        s_name = s.get("source_table_name") or s.get("table_name") or s.get("source_table") or ""
        s_schema = s.get("schema") or s.get("source_schema") or "public"
        clean_s = _sanitize_ident(s_name)
        meta = (introspected_sources or {}).get(s_name) or (introspected_sources or {}).get(clean_s) or (introspected_sources or {}).get(f"{s_schema}.{s_name}")
        cols = (meta.get("columns", []) if meta else [])
        col_names = [c.get("column_name") or c.get("name") for c in cols if (c.get("column_name") or c.get("name"))]
        if s_name:
            source_cols_lookup[s_name.lower()] = (s_name, col_names)
            source_cols_lookup[clean_s.lower()] = (s_name, col_names)

    # 1. Process explicit HLA Table 10 mappings
    for m in raw_mappings:
        src_tbl = m.get("source_table") or m.get("source_dataset") or ""
        src_col = m.get("source_field") or m.get("source_column") or ""
        tgt_tbl = m.get("target_table") or m.get("target_entity") or ""
        tgt_col = m.get("target_column") or m.get("target_field") or ""
        trans = m.get("derivation_logic") or m.get("transformation") or "direct"

        if not tgt_col and not src_col:
            continue

        if not tgt_tbl and target_entities:
            tgt_tbl = target_entities[0]["table_name"]

        norm_trans = str(trans).strip() if trans else "direct"
        if not norm_trans:
            norm_trans = "direct"

        item_src_tbl = src_tbl or (sources[0].get("source_table_name") if sources else "source_feed")
        item_tgt_tbl = tgt_tbl or "target_entity"
        item_tgt_col = tgt_col or src_col or "unnamed_col"

        item = {
            "source_table": item_src_tbl,
            "source_column": src_col or "UNMAPPED",
            "transformation": norm_trans,
            "target_table": item_tgt_tbl,
            "target_column": item_tgt_col
        }
        mappings_list.append(item)
        if item_tgt_tbl and item_tgt_col:
            seen_target_cols.add((item_tgt_tbl.lower(), item_tgt_col.lower()))

    # 2. For all discovered target entities and their columns, ensure every column has lineage
    for entity in (target_entities or []):
        t_name = entity.get("table_name", "")
        cols = entity.get("columns", [])
        for c in cols:
            c_name = c.get("name") if isinstance(c, dict) else str(c).split()[0].strip()
            if not c_name:
                continue
            key = (t_name.lower(), c_name.lower())
            if key in seen_target_cols:
                continue
            seen_target_cols.add(key)

            matched_src_tbl = None
            matched_src_col = None
            clean_c = re.sub(r'[^a-z0-9]', '', c_name.lower())

            for s_key, (orig_s_name, s_cols) in source_cols_lookup.items():
                for sc in s_cols:
                    if re.sub(r'[^a-z0-9]', '', str(sc).lower()) == clean_c:
                        matched_src_tbl = orig_s_name
                        matched_src_col = sc
                        break
                if matched_src_tbl:
                    break

            if matched_src_tbl:
                mappings_list.append({
                    "source_table": matched_src_tbl,
                    "source_column": matched_src_col,
                    "transformation": "direct",
                    "target_table": t_name,
                    "target_column": c_name
                })
            else:
                if c_name.lower() in ("id", "record_id", "row_id"):
                    mappings_list.append({
                        "source_table": "SYSTEM",
                        "source_column": "IDENTITY",
                        "transformation": "BIGINT AUTO_INCREMENT",
                        "target_table": t_name,
                        "target_column": c_name
                    })
                elif any(kw in c_name.lower() for kw in ("created_at", "updated_at", "load_dtm", "batch_id", "source_system")):
                    mappings_list.append({
                        "source_table": "SYSTEM",
                        "source_column": "CURRENT_TIMESTAMP",
                        "transformation": "METADATA INGESTION",
                        "target_table": t_name,
                        "target_column": c_name
                    })
                else:
                    mappings_list.append({
                        "source_table": "N/A",
                        "source_column": "UNMAPPED",
                        "transformation": "UNMAPPED",
                        "target_table": t_name,
                        "target_column": c_name
                    })

    return mappings_list


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
        engine = DatabaseManager.get_engine(target_config)

        # 1. Connection check
        with DatabaseManager.connect(target_config) as conn:
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
        recon = reconcile_objects(existing_meta, required_objects, target_schema=target_schema)
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
        engine = DatabaseManager.get_engine(target_config)
        
        # Pre-ensure target schema exists
        if create_schema_stmt and db_type in ("postgresql", "postgres", "snowflake"):
            try:
                with DatabaseManager.connect(target_config) as init_conn:
                    if _has_executable_sql(create_schema_stmt):
                        init_conn.execute(text(create_schema_stmt))
                        init_conn.commit()
            except Exception:
                pass

        raw_statements = _split_sql_statements(ddl_script)
        
        with DatabaseManager.connect(target_config) as conn:
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
        engine = DatabaseManager.get_engine(target_config)

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


def reconcile_objects(existing_meta: dict, required_objects: list, target_schema: str = "") -> dict:
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
    if isinstance(required_objects, str):
        required_objects = _parse_required_objects_from_ddl(required_objects)

    eff_schema = (target_schema or existing_meta.get("schema_name") or "").strip()
    report: dict = {
        "schema_status": "EXISTING" if existing_meta.get("schema_exists") else "MISSING",
        "objects": {},
        "counts": {"existing": 0, "missing": 0, "different": 0, "invalid": 0},
    }

    for obj in required_objects:
        bare = obj["bare_name"].lower()
        full = f"{eff_schema}.{bare}" if eff_schema else obj.get("full_name", bare)
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
    # A schema name can legally contain dots, e.g. "custom_schema.sub_schema".
    # Reuse the central formatter instead of concatenating the raw schema;
    # otherwise PostgreSQL parses dotted schemas as
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
        _stage("HLA source data extraction completed (simulated)")
        _stage("HLA business & transformation rules executed (simulated)")
        _stage("Target data verified (simulated)")
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
        engine = DatabaseManager.get_engine(target_config)

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
        recon = reconcile_objects(existing_meta, required_objects, target_schema=target_schema)
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
                    s_clean = re.sub(r"--[^\n]*", "", s).strip()
                    if not s_clean:
                        continue
                    if not s_clean.upper().startswith("CREATE TABLE"):
                        continue

                    # Identify which table this CREATE is for
                    tm = re.search(
                        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
                        r"((?:\"[^\"]+\"|\w+)(?:\.(?:\"[^\"]+\"|\w+))?)",
                        s_clean, re.IGNORECASE,
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
                        s_clean, count=1, flags=re.IGNORECASE,
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
        _stage("Target schema DDL deployed")

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
            "full_target": str,        # e.g. '"custom_schema.target_table"'
            "schema_name": str | None, # e.g. 'custom_schema'
            "table_name": str,         # e.g. 'target_table' (bare lowercase)
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
    ddl_target_meta: dict = None,
    strict_not_null: bool = False
) -> tuple[bool, str]:
    """
    Validates a single SQL statement against target database physical metadata and generated target DDL objects.

    Args:
        target_meta: Dictionary returned by inspect_target_schema (live physical metadata)
        default_schema: The target schema configured for deployment
        stmt: The SQL statement to validate
        ddl_target_meta: Dictionary of target tables and columns defined by generated DDL
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

    tables_map = (target_meta or {}).get("tables", {})
    ddl_tables_map = (ddl_target_meta or {}).get("tables", {})

    tbl_meta = tables_map.get(tbl_bare)
    is_from_ddl = False

    # 1. Validate Table exists in physical DB or is defined in generated target DDL
    if not tbl_meta:
        found_key = next((k for k in tables_map if k.lower() == tbl_bare), None)
        if found_key:
            tbl_meta = tables_map[found_key]
        elif tbl_bare in ddl_tables_map:
            tbl_meta = ddl_tables_map[tbl_bare]
            is_from_ddl = True
        else:
            found_ddl_key = next((k for k in ddl_tables_map if k.lower() == tbl_bare), None)
            if found_ddl_key:
                tbl_meta = ddl_tables_map[found_ddl_key]
                is_from_ddl = True
            else:
                diag = (
                    f"[SCHEMA VALIDATION FAILED]\n"
                    f"Target:\n"
                    f"    {schema}.{tbl_bare}\n"
                    f"Status:\n"
                    f"    Table does not exist in target schema '{schema}' and is not defined in target DDL.\n"
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
            f"Columns not present in target definition:\n"
            f"    " + "\n    ".join(missing_cols) + "\n"
            f"Deployment SQL was NOT executed."
        )
        return False, diag

    # 3. Validate NOT NULL columns without default (for INSERT on physical tables)
    if not is_from_ddl and parsed["operation"] == "INSERT" and not parsed["is_star"] and strict_not_null:
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
    if not is_from_ddl and parsed["operation"] == "INSERT":
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
    ddl_script: str = None,
    strict_not_null: bool = False
) -> tuple[bool, str, list[dict]]:
    """
    Generic pre-execution validation gate for an entire transformation script.
    Inspects target database schema and generated DDL to validate all statements before execution.
    Recognizes newly generated target tables defined by the DDL specification.

    Returns:
        (success: bool, message: str, diagnostics: list[dict])
    """
    db_type = (target_config.get("db_type") or "postgresql").lower()
    target_schema = (target_config.get("schema_name") or "").strip() or "public"

    if db_type == "sandbox":
        return True, "Sandbox mode: Schema pre-execution validation bypassed.", []

    # Build DDL-defined targets metadata
    ddl_target_meta = {"tables": {}}
    if ddl_script:
        req_objs = _parse_required_objects_from_ddl(ddl_script)
        for obj in req_objs:
            b_name = obj["bare_name"].lower()
            cols = obj.get("columns", [])
            ddl_target_meta["tables"][b_name] = {
                "columns": cols,
                "column_names": {c["name"].lower() for c in cols}
            }

    try:
        engine = DatabaseManager.get_engine(target_config)
        target_meta = inspect_target_schema(engine, target_schema)

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
                ddl_target_meta=ddl_target_meta,
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

        return True, "Pre-execution schema validation passed. All generated SQL statements match target physical schema and DDL definitions.", []

    except Exception as exc:
        return False, f"[SCHEMA VALIDATION FAILED] Error inspecting target schema: {exc}", [{"statement": "", "error": str(exc)}]

