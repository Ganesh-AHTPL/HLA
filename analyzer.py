import os
import re
import json
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

# Optional LLM clients
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


# ── Table Formatting Helpers ──────────────────────────────────────────

def _set_cell_background(cell, fill_hex):
    """Utility to set cell background shading in python-docx."""
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), fill_hex)
    tc_pr.append(shd)


def _set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    """Utility to set table cell padding."""
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_mar = OxmlElement('w:tcMar')
    for margin_name, val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
        node = OxmlElement(f'w:{margin_name}')
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        tc_mar.append(node)
    tc_pr.append(tc_mar)


def clean_text(text):
    """Sanitizes extracted string from table cells or paragraphs."""
    if not text:
        return ""
    return text.replace("\n", " ").strip()


def get_table_headers(table):
    """Extracts lowercase sanitized headers from table row 0."""
    if not table.rows:
        return []
    return [clean_text(c.text).lower() for c in table.rows[0].cells]


# ── Section Extractors for HLA Solution Design Template ───────────────

def extract_document_control(doc):
    """
    Extracts Table 1 (Version History), Table 2 (Reviewers & Approvers), and Stakeholders.
    """
    version_history = []
    reviewers = []
    stakeholders = []

    for table in doc.tables:
        headers = get_table_headers(table)
        hdr_str = " | ".join(headers)

        # Table 1: Version History
        if "version" in headers and "author" in headers:
            for row in table.rows[1:]:
                cells = [clean_text(c.text) for c in row.cells]
                if any(cells):
                    version_history.append({
                        "version": cells[0] if len(cells) > 0 else "",
                        "date": cells[1] if len(cells) > 1 else "",
                        "author": cells[2] if len(cells) > 2 else "",
                        "description": cells[3] if len(cells) > 3 else ""
                    })

        # Table 2: Reviewers & Approvers
        elif "role" in headers and "team" in headers and ("name" in headers or "reviewer" in hdr_str):
            for row in table.rows[1:]:
                cells = [clean_text(c.text) for c in row.cells]
                if any(cells):
                    reviewers.append({
                        "name": cells[0] if len(cells) > 0 else "",
                        "role": cells[1] if len(cells) > 1 else "",
                        "team": cells[2] if len(cells) > 2 else ""
                    })

    # Stakeholders from paragraphs
    capture_sh = False
    for p in doc.paragraphs:
        txt = clean_text(p.text)
        if "stakeholder" in txt.lower() and (p.style and p.style.name and p.style.name.startswith("Heading")):
            capture_sh = True
            continue
        elif capture_sh:
            if p.style and p.style.name and p.style.name.startswith("Heading"):
                break
            if txt and not txt.startswith("List business") and not txt.startswith("<"):
                stakeholders.append(txt)

    return {
        "version_history": version_history,
        "reviewers": reviewers,
        "stakeholders": stakeholders
    }


def extract_control_overview(doc):
    """
    Extracts Section 1:
    - Table 3: Control Identification
    - Table 4: Database Connection Details & Credentials
    - Table 5: Default Control Columns
    """
    control_id_data = {
        "control_number": "",
        "control_title": "",
        "control_owner": "",
        "purpose": ""
    }
    db_connections = []
    default_columns = []

    for table in doc.tables:
        headers = get_table_headers(table)
        if not table.rows:
            continue

        # Table 3: Control Identification
        if "field" in headers and "value" in headers and any("control" in clean_text(r.cells[0].text).lower() for r in table.rows[1:3]):
            for row in table.rows[1:]:
                cells = [clean_text(c.text) for c in row.cells]
                if len(cells) >= 2 and cells[0]:
                    k = cells[0].lower()
                    if "number" in k:
                        control_id_data["control_number"] = cells[1]
                    elif "title" in k:
                        control_id_data["control_title"] = cells[1]
                    elif "owner" in k or "team" in k:
                        control_id_data["control_owner"] = cells[1]
                    elif "purpose" in k or "objective" in k:
                        control_id_data["purpose"] = cells[1]

        # Table 4: DB Connection Details & Credentials
        elif any("server" in h or "host" in h or "database" in h or "connection" in h or "parameter" in h for h in headers) and any("port" in clean_text(r.cells[0].text).lower() or "server" in clean_text(r.cells[0].text).lower() or "host" in clean_text(r.cells[0].text).lower() or "environment" in clean_text(r.cells[0].text).lower() for r in table.rows[1:4]):
            col_count = len(table.rows[0].cells) if table.rows else 0
            if col_count > 2 and "parameter" in headers[0].lower():
                # Multi-column layout: Parameter in col 0, distinct DBs in cols 1..N
                for col_idx in range(1, col_count):
                    db_label = clean_text(table.rows[0].cells[col_idx].text)
                    conn_entry = {"source_db_name": db_label}
                    for row in table.rows[1:]:
                        param_name = clean_text(row.cells[0].text).lower()
                        val = clean_text(row.cells[col_idx].text) if col_idx < len(row.cells) else ""
                        if "environment" in param_name: conn_entry["environment"] = val
                        elif "server" in param_name or "host" in param_name: conn_entry["host"] = val
                        elif "port" in param_name: conn_entry["port"] = val
                        elif "database" in param_name: conn_entry["database_name"] = val
                        elif "schema" in param_name: conn_entry["schema_name"] = val
                        elif "credential" in param_name: conn_entry["credential_reference"] = val
                        elif "connection" in param_name or "type" in param_name: conn_entry["connection_type"] = val
                    if conn_entry.get("host") or conn_entry.get("database_name") or conn_entry.get("source_db_name"):
                        db_connections.append(conn_entry)
            else:
                # Standard 2-column key-value table
                conn_entry = {}
                for row in table.rows[1:]:
                    cells = [clean_text(c.text) for c in row.cells]
                    if len(cells) >= 2 and cells[0]:
                        param_name = cells[0].lower()
                        val = cells[1]
                        if "environment" in param_name: conn_entry["environment"] = val
                        elif "server" in param_name or "host" in param_name: conn_entry["host"] = val
                        elif "port" in param_name: conn_entry["port"] = val
                        elif "database" in param_name: conn_entry["database_name"] = val
                        elif "schema" in param_name: conn_entry["schema_name"] = val
                        elif "credential" in param_name: conn_entry["credential_reference"] = val
                        elif "connection" in param_name or "type" in param_name: conn_entry["connection_type"] = val
                if conn_entry:
                    db_connections.append(conn_entry)

        # Table 5: Default Control Columns
        elif any("control_id" in clean_text(r.cells[0].text).upper() for r in table.rows[1:3]) or ("column name" in headers and "data type" in headers and "description" in headers and len(headers) == 3):
            for row in table.rows[1:]:
                cells = [clean_text(c.text) for c in row.cells]
                if any(cells) and cells[0] and not cells[0].startswith("<..."):
                    default_columns.append({
                        "column_name": cells[0],
                        "data_type": cells[1] if len(cells) > 1 else "VARCHAR",
                        "description": cells[2] if len(cells) > 2 else ""
                    })

    # If title not found in table, check heading paragraphs
    if not control_id_data["control_title"]:
        for p in doc.paragraphs[:10]:
            txt = clean_text(p.text)
            if "control-" in txt.lower() or "reconciliation solution" in txt.lower():
                control_id_data["control_title"] = txt
                break

    # Derive dynamic control suffix (e.g. Control-23 -> '23', Control-24 -> '24')
    ctrl_raw = control_id_data["control_number"]
    match = re.search(r'(\d+)', ctrl_raw)
    ctrl_digits = match.group(1) if match else "23"

    # Derive dynamic target schema (e.g. ra_ctrl.ctrl_23, ra_ctrl.ctrl_24)
    # Check if Table 4 explicitly specified a schema name
    explicit_target_schema = None
    for conn in db_connections:
        s_schema = conn.get("schema_name", "")
        if s_schema and not s_schema.startswith("<") and s_schema.lower() not in ("public", "schema list", "schema"):
            explicit_target_schema = s_schema
            break

    target_schema = explicit_target_schema or f"ra_ctrl.ctrl_{ctrl_digits}"

    return {
        "identification": control_id_data,
        "control_digits": ctrl_digits,
        "target_schema": target_schema,
        "db_connections": db_connections,
        "default_columns": default_columns
    }


def extract_source_inventory(doc):
    """
    Extracts Table 6: Source Systems & Table Details.
    Columns: Source System | DB / Schema | Table Name | Refresh Frequency / Timing | Load Type
    Also supports legacy table layouts where Table Name is column 0.
    """
    sources = []
    seen = set()

    for table in doc.tables:
        if not table.rows:
            continue
        headers = get_table_headers(table)

        # Match Table 6 (or legacy source table) - exclude ETL process stage tables
        is_stage_table = any("data process stage" in h or "dataset/table entity name" in h or "standard /non standard" in h for h in headers)
        if is_stage_table:
            continue

        is_source_table = (
            any("source system" in h for h in headers)
            or (any("table name" in h for h in headers) and any("load" in h or "frequency" in h or "refresh" in h for h in headers))
        )

        if not is_source_table:
            continue

        col_table = next((i for i, h in enumerate(headers) if "table name" in h or h == "table"), -1)
        col_src_sys = next((i for i, h in enumerate(headers) if "source system" in h or "system" in h), -1)
        col_db = next((i for i, h in enumerate(headers) if "db / schema" in h or "schema" in h or "db" in h), -1)
        col_freq = next((i for i, h in enumerate(headers) if "frequency" in h or "refresh" in h or "timing" in h), -1)
        col_load = next((i for i, h in enumerate(headers) if "load type" in h or "type of load" in h or "load" in h), -1)

        for row in table.rows[1:]:
            cells = [clean_text(c.text) for c in row.cells]
            if not any(cells):
                continue

            tbl_name = cells[col_table] if col_table >= 0 and col_table < len(cells) else cells[0]
            src_sys = cells[col_src_sys] if col_src_sys >= 0 and col_src_sys < len(cells) else ""
            db_schema = cells[col_db] if col_db >= 0 and col_db < len(cells) else ""
            freq = cells[col_freq] if col_freq >= 0 and col_freq < len(cells) else "Daily"
            load_type = cells[col_load] if col_load >= 0 and col_load < len(cells) else "Truncate & Load"

            clean_lower = (tbl_name or "").strip().lower()
            if not clean_lower or clean_lower in ["table name", "<table_name>"]:
                continue
            if any(clean_lower.startswith(prefix) for prefix in ["found in", "not found in", "grand total", "total"]):
                continue

            # Parse schema vs table
            source_schema = "public"
            source_table = tbl_name
            source_db = ""

            if "." in tbl_name:
                p = tbl_name.split(".", 1)
                source_schema, source_table = p[0].strip(), p[1].strip()
            elif "." in db_schema:
                p = db_schema.split(".", 1)
                source_db, source_schema = p[0].strip(), p[1].strip()
            elif db_schema:
                source_db = db_schema

            load_category = "Append" if "append" in load_type.lower() else "Truncate and load"

            key = f"{src_sys}:{source_db}:{source_schema}:{source_table}"
            if key not in seen:
                seen.add(key)
                sources.append({
                    "full_table_name": f"{source_schema}.{source_table}" if source_schema != "public" else source_table,
                    "source_system": src_sys,
                    "source_db": source_db,
                    "source_schema": source_schema,
                    "source_table": source_table,
                    "frequency": freq,
                    "refresh_time": freq,
                    "type_of_load": load_category,
                    "raw_load_notes": load_type
                })

    return sources


def extract_extraction_requirements(doc):
    """
    Extracts Table 7: Data Extraction Requirements.
    Columns: Source Table | Extraction Type | Extraction Logic / Window | Justification
    """
    extractions = []

    for table in doc.tables:
        headers = get_table_headers(table)
        if any("extraction" in h for h in headers):
            col_src = next((i for i, h in enumerate(headers) if "source" in h or "table" in h), 0)
            col_ext_type = next((i for i, h in enumerate(headers) if "extraction type" in h or "type" in h), 1)
            col_logic = next((i for i, h in enumerate(headers) if "logic" in h or "window" in h), 2)
            col_just = next((i for i, h in enumerate(headers) if "justification" in h), 3)

            for row in table.rows[1:]:
                cells = [clean_text(c.text) for c in row.cells]
                if any(cells) and cells[0]:
                    extractions.append({
                        "source_table": cells[col_src] if col_src < len(cells) else "",
                        "extraction_type": cells[col_ext_type] if col_ext_type < len(cells) else "Full Dump",
                        "extraction_logic": cells[col_logic] if col_logic < len(cells) else "",
                        "justification": cells[col_just] if col_just < len(cells) else ""
                    })

    return extractions


def extract_development_flow(doc):
    """
    Extracts Section 4: High-Level Development Flow steps.
    """
    flow_steps = []
    capture = False

    for p in doc.paragraphs:
        txt = clean_text(p.text)
        if "development flow" in txt.lower():
            capture = True
            continue
        elif capture:
            if p.style and p.style.name and p.style.name.startswith("Heading 1"):
                break
            if txt.startswith("Step ") or (p.style and "list" in p.style.name.lower() and txt):
                flow_steps.append(txt)

    return flow_steps


def extract_rules_and_filters(doc):
    """
    Extracts Section 5 & 6:
    - Table 8: Filter Buckets & Source Table Rules
    - Table 9: Filtration Procedure Execution Steps
    - Legacy rule tables with Rule ID & Rule statements
    """
    input_streams = []
    filter_rules = []
    balance_rules = []
    reconciliation_flows = []
    filtration_steps = []

    for table in doc.tables:
        if not table.rows:
            continue
        headers = get_table_headers(table)
        hdr_str = " | ".join(headers)

        # 1. Standard Template Table 8: Filter Buckets & Source Table Rules
        if any("bucket" in h or "balanced records" in h or "filter rule applied" in h for h in headers):
            col_src = next((i for i, h in enumerate(headers) if "source" in h or "table" in h), 0)
            col_rule = next((i for i, h in enumerate(headers) if "rule" in h), 1)
            col_flt = next((i for i, h in enumerate(headers) if "filtered" in h or "exception" in h), 2)
            col_bal = next((i for i, h in enumerate(headers) if "balanced" in h or "pass-through" in h), 3)

            for row in table.rows[1:]:
                cells = [clean_text(c.text) for c in row.cells]
                if any(cells) and cells[0]:
                    src_tbl = cells[col_src] if col_src < len(cells) else ""
                    rule_text = cells[col_rule] if col_rule < len(cells) else ""
                    flt_bucket = cells[col_flt] if col_flt < len(cells) else ""
                    bal_bucket = cells[col_bal] if col_bal < len(cells) else ""

                    rule_obj = {
                        "rule_id": f"FLT-{len(filter_rules)+1}",
                        "data_stream": src_tbl,
                        "category": "Pre-Execution Filter",
                        "rule_statement": rule_text,
                        "filtered_out_bucket": flt_bucket,
                        "balanced_bucket": bal_bucket,
                        "source_table": src_tbl
                    }
                    filter_rules.append(rule_obj)

                    if bal_bucket and bal_bucket not in [b.get("category") for b in balance_rules]:
                        balance_rules.append({
                            "rule_id": f"BAL-{len(balance_rules)+1}",
                            "data_stream": src_tbl,
                            "category": bal_bucket,
                            "rule_statement": f"Pass-through clean balanced dataset for downstream reconciliation."
                        })

        # 2. Standard Template Table 9: Filtration Procedure
        elif "step" in headers and any("description" in h for h in headers) and any("logic" in h or "reference" in h for h in headers):
            for row in table.rows[1:]:
                cells = [clean_text(c.text) for c in row.cells]
                if any(cells):
                    filtration_steps.append({
                        "step": cells[0] if len(cells) > 0 else "",
                        "description": cells[1] if len(cells) > 1 else "",
                        "logic_reference": cells[2] if len(cells) > 2 else ""
                    })

        # 3. Legacy Table with "Rule ID" and "Rule"
        elif any('rule id' in h for h in headers) and any('rule' in h for h in headers):
            for row in table.rows[1:]:
                cells = [clean_text(c.text) for c in row.cells]
                if not cells or not any(cells):
                    continue

                rule_id = cells[0] if len(cells) > 0 else ""
                data_stream = cells[1] if len(cells) > 1 else ""
                rule_desc = cells[2] if len(cells) > 2 else ""
                rule_detail = cells[3] if len(cells) > 3 else ""

                if not rule_id and not data_stream and not rule_detail:
                    continue

                rule_obj = {
                    "rule_id": rule_id,
                    "data_stream": data_stream,
                    "category": rule_desc,
                    "rule_statement": rule_detail
                }

                if rule_id.upper().startswith("I") or "input data" in rule_desc.lower():
                    input_streams.append(rule_obj)
                elif "filter" in rule_desc.lower() or rule_id.upper() in [f"R{i}" for i in range(1, 11)]:
                    filter_rules.append(rule_obj)
                elif "balance" in rule_desc.lower() or "balance" in rule_detail.lower():
                    balance_rules.append(rule_obj)
                else:
                    reconciliation_flows.append(rule_obj)

    # Paragraph fallbacks for filters & buckets
    if not filter_rules:
        for p in doc.paragraphs:
            text = clean_text(p.text)
            if any(k in text.lower() for k in ["filter out duplicate", "filter out records", "remove internal", "remove test/dummy"]):
                filter_rules.append({
                    "rule_id": f"FLT-{len(filter_rules)+1}",
                    "data_stream": "General",
                    "category": "Filter",
                    "rule_statement": text
                })
            elif any(k in text.lower() for k in ["balance dataset", "bucket rule", "balance summary"]):
                balance_rules.append({
                    "rule_id": f"BAL-{len(balance_rules)+1}",
                    "data_stream": "Recon",
                    "category": "Balance Node",
                    "rule_statement": text
                })

    return {
        "input_streams": input_streams,
        "filter_rules": filter_rules,
        "balance_rules": balance_rules,
        "reconciliation_flows": reconciliation_flows,
        "filtration_steps": filtration_steps
    }


def extract_derivation_catalog(doc):
    """
    Extracts detailed derivation formulas, conditional logic, and rules from document paragraphs.
    """
    catalog = {}
    current_key = None
    buffer = []

    for p in doc.paragraphs:
        text = clean_text(p.text)
        if not text:
            continue

        if any(cue in text.lower() for cue in ["logic to derive", "logic to driving", "derivation logic"]):
            if current_key and buffer:
                catalog[current_key] = "\n".join(buffer).strip()
                buffer = []
            current_key = text
        elif current_key:
            if p.style and p.style.name and (p.style.name.startswith("Heading") or (len(text) < 40 and not any(kw in text.lower() for kw in ["if", "then", "else", "check", "derive", "case"]))):
                catalog[current_key] = "\n".join(buffer).strip()
                current_key = None
                buffer = []
            else:
                buffer.append(text)

    if current_key and buffer:
        catalog[current_key] = "\n".join(buffer).strip()

    return catalog


def find_specific_derivation_logic(col_name, doc_text, catalog):
    """
    Locates exact derivation logic for a derived column name.
    """
    col_clean = col_name.strip().lower()

    for heading, logic in catalog.items():
        if col_clean in heading.lower() or any(term in heading.lower() for term in col_clean.split("_")):
            return logic


    # Scan doc lines
    lines = doc_text.split("\n")
    matching_block = []
    found = False
    for line in lines:
        if col_clean in line.lower() and ("logic" in line.lower() or "derive" in line.lower() or "if" in line.lower()):
            found = True
            matching_block.append(line.strip())
        elif found:
            if any(k in line.lower() for k in ["if", "then", "else", "check", "case", "like", "when", "="]):
                matching_block.append(line.strip())
            else:
                break

    if matching_block:
        return "\n".join(matching_block)

    return "Conditional derivation logic specified in solution business rules."


def extract_attribute_mappings(doc, catalog):
    """
    Extracts Table 10: Report Table Generation / Attribute Mappings.
    Columns: Report Table Name | Attribute Name | Source Type (Direct / Derived) | Source Table.Field / Derivation Logic
    Also supports legacy 4-column mappings table.
    """
    mappings = []
    seen = set()
    doc_text = "\n".join([clean_text(p.text) for p in doc.paragraphs])

    for table in doc.tables:
        if not table.rows:
            continue
        headers = get_table_headers(table)

        # Match Table 10 or legacy mapping table
        is_mapping_table = (
            any("attribute" in h or "column name" in h for h in headers)
            and any("derivation" in h or "source field" in h or "source type" in h or "source table" in h for h in headers)
        )

        if not is_mapping_table:
            continue

        col_tbl = next((i for i, h in enumerate(headers) if "report table" in h or "target table" in h), -1)
        col_attr = next((i for i, h in enumerate(headers) if "attribute" in h or "column name" in h or "field name" in h), 0)
        col_type = next((i for i, h in enumerate(headers) if "source type" in h or "type" in h or "classification" in h), -1)
        col_logic = next((i for i, h in enumerate(headers) if "derivation" in h or "source table.field" in h or "source field" in h or "logic" in h), -1)

        for row in table.rows[1:]:
            cells = [clean_text(c.text) for c in row.cells]
            if not any(cells):
                continue

            tbl_name = cells[col_tbl] if col_tbl >= 0 and col_tbl < len(cells) else "target_report"
            attr_name = cells[col_attr] if col_attr >= 0 and col_attr < len(cells) else cells[0]
            src_type = cells[col_type] if col_type >= 0 and col_type < len(cells) else ""
            logic_field = cells[col_logic] if col_logic >= 0 and col_logic < len(cells) else ""

            if not attr_name or attr_name.lower() in ["attribute name", "column name", "sno", "s.no"]:
                continue

            key = f"{tbl_name}:{attr_name}"
            if key in seen:
                continue
            seen.add(key)

            # Classify Direct vs Derived
            is_derived = (
                "derived" in src_type.lower()
                or "derived" in logic_field.lower()
                or any(logic_field.lower().startswith(kw) for kw in ["if ", "case ", "count(", "distinct", "sum(", "concat("])
            )

            if is_derived:
                mapping_type = "Derived"
                if any(logic_field.lower().startswith(kw) for kw in ["if ", "case "]):
                    logic = logic_field
                else:
                    logic = find_specific_derivation_logic(attr_name, doc_text, catalog)
                    if logic == "Conditional derivation logic specified in solution business rules." and logic_field:
                        logic = logic_field
            else:
                mapping_type = "Direct"
                clean_src = logic_field if logic_field else "(Direct pass-through)"
                logic = f"Direct 1:1 mapping of source attribute '{clean_src}' from {tbl_name}."

            mappings.append({
                "target_column": attr_name,
                "report_table_name": tbl_name,
                "source_field": logic_field if not is_derived else "(Derived Expression)",
                "source_table": tbl_name,
                "mapping_type": mapping_type,
                "derivation_logic": logic,
                "raw_source_type": src_type
            })

    return mappings


def extract_report_attributes_and_metrics(doc):
    """
    Extracts Table 11: Report Attributes & Report Numbers.
    Columns: Report Name | Key Attributes Shown | Report Numbers / Metrics (e.g., KRI counts, totals)
    """
    reports = []
    for table in doc.tables:
        headers = get_table_headers(table)
        if any("report name" in h for h in headers) and any("metrics" in h or "numbers" in h or "kri" in h for h in headers):
            for row in table.rows[1:]:
                cells = [clean_text(c.text) for c in row.cells]
                if any(cells) and cells[0]:
                    reports.append({
                        "report_name": cells[0],
                        "key_attributes": cells[1] if len(cells) > 1 else "",
                        "metrics": cells[2] if len(cells) > 2 else ""
                    })
    return reports


def extract_configuration_tables(doc):
    """
    Extracts Table 12: Configuration Values.
    Columns: Config Table Name | Purpose | Sample Fields | Consumed By (Report Name)
    """
    config_tables = []
    for table in doc.tables:
        headers = get_table_headers(table)
        if any("config" in h for h in headers) and any("purpose" in h for h in headers):
            for row in table.rows[1:]:
                cells = [clean_text(c.text) for c in row.cells]
                if any(cells) and cells[0]:
                    config_tables.append({
                        "config_table_name": cells[0],
                        "purpose": cells[1] if len(cells) > 1 else "",
                        "sample_fields": cells[2] if len(cells) > 2 else "",
                        "consumed_by": cells[3] if len(cells) > 3 else ""
                    })
    return config_tables


def extract_report_inventory_and_order(doc):
    """
    Extracts Table 13: Report Inventory & Generation Order.
    Columns: Sequence # | Report Name | Depends On | Notes
    """
    inventory = []
    for table in doc.tables:
        headers = get_table_headers(table)
        if any("sequence" in h for h in headers) and any("depends on" in h for h in headers):
            for row in table.rows[1:]:
                cells = [clean_text(c.text) for c in row.cells]
                if any(cells) and cells[0]:
                    inventory.append({
                        "sequence": cells[0],
                        "report_name": cells[1] if len(cells) > 1 else "",
                        "depends_on": cells[2] if len(cells) > 2 else "None",
                        "notes": cells[3] if len(cells) > 3 else ""
                    })
    return inventory


def extract_appendix_open_items(doc):
    """
    Extracts open questions and pending items from Appendix.
    """
    open_items = []
    capture = False
    for p in doc.paragraphs:
        txt = clean_text(p.text)
        if "appendix" in txt.lower() or "open item" in txt.lower():
            if p.style and p.style.name and p.style.name.startswith("Heading"):
                capture = True
                continue
        elif capture:
            if txt and not txt.startswith("Track open questions") and not txt.startswith("<"):
                open_items.append(txt)
    return open_items


# ── Template Conformance Validation ───────────────────────────────────

def validate_template_compliance(doc, parsed_data):
    """
    Evaluates whether an uploaded document strictly adheres to the standard
    13-Table HLA Solution Design Template.
    Returns compliance score (0-100%) and detailed section checklist.
    """
    checks = {
        "Document Control (Table 1/2)": bool(parsed_data.get("document_control", {}).get("version_history")),
        "Control Overview (Table 3)": bool(parsed_data.get("control_overview", {}).get("identification", {}).get("control_number") or parsed_data.get("control_overview", {}).get("identification", {}).get("control_title")),
        "Database Connection Details (Table 4)": bool(parsed_data.get("control_overview", {}).get("db_connections")),
        "Default Control Columns (Table 5)": bool(parsed_data.get("control_overview", {}).get("default_columns")),
        "Source Systems Inventory (Table 6)": bool(len(parsed_data.get("sources", [])) > 0),
        "Extraction Requirements (Table 7)": bool(len(parsed_data.get("extraction_requirements", [])) > 0),
        "Development Flow (Section 4)": bool(len(parsed_data.get("development_flow", [])) > 0),
        "Filter Buckets & Source Rules (Table 8)": bool(len(parsed_data.get("rules", {}).get("filter_rules", [])) > 0),
        "Filtration Procedure Steps (Table 9)": bool(len(parsed_data.get("rules", {}).get("filtration_steps", [])) > 0),
        "Report Table Generation / Mappings (Table 10)": bool(len(parsed_data.get("mappings", [])) > 0),
        "Report Attributes & Metrics (Table 11)": bool(len(parsed_data.get("report_attributes", [])) > 0),
        "Configuration Tables (Table 12)": bool(len(parsed_data.get("config_tables", [])) > 0),
        "Report Inventory & Sequence (Table 13)": bool(len(parsed_data.get("report_inventory", [])) > 0)
    }

    passed_count = sum(1 for v in checks.values() if v)
    total_count = len(checks)
    score = int((passed_count / total_count) * 100)

    missing = [name for name, passed in checks.items() if not passed]
    is_compliant = score >= 75  # Compliant if 75%+ of standard template sections present

    return {
        "is_compliant": is_compliant,
        "compliance_score": score,
        "total_checks": total_count,
        "passed_checks": passed_count,
        "checklist": checks,
        "missing_sections": missing,
        "standard_template": "HLA Solution Design Template (v0.1 Standard)"
    }


# ── LLM Integration ──────────────────────────────────────────────────

def call_ollama(prompt, model="llama3.2:3b", base_url="http://localhost:11434"):
    """
    Calls local Ollama API to enrich and synthesize analysis.
    """
    if not REQUESTS_AVAILABLE:
        return None
    try:
        url = f"{base_url}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2}
        }
        res = requests.post(url, json=payload, timeout=5)
        if res.status_code == 200:
            return res.json().get("response", "")
    except Exception:
        pass
    return None


def call_groq_or_openai(prompt):
    """
    Calls Groq or OpenAI API if keys are configured in environment.
    """
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        try:
            from groq import Groq
            client = Groq(api_key=groq_key)
            completion = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            return completion.choices[0].message.content
        except Exception:
            pass

    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        try:
            import openai
            client = openai.OpenAI(api_key=openai_key)
            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2
            )
            return completion.choices[0].message.content
        except Exception:
            pass

    return None


def synthesize_llm_overview(control_info, sources, rules, mappings, extractions=None, config_tables=None, report_inventory=None):
    """
    Synthesizes executive overview and data flow analysis using LLM or structured synthesis.
    Supplies clean, structured JSON from the standard template to avoid hallucinations.
    """
    ctrl_id = control_info.get("identification", {}) if isinstance(control_info, dict) else {}
    ctrl_num = ctrl_id.get("control_number") or "CTRL-01"
    ctrl_title = ctrl_id.get("control_title") or "Enterprise Reconciliation Solution"
    ctrl_purpose = ctrl_id.get("purpose") or "Automated reconciliation and KRI exception reporting."

    direct_count = sum(1 for m in mappings if m.get("mapping_type") == "Direct")
    derived_count = sum(1 for m in mappings if m.get("mapping_type") == "Derived")
    trunc_count = sum(1 for s in sources if s.get("type_of_load") == "Truncate and load")
    append_count = sum(1 for s in sources if s.get("type_of_load") == "Append")

    prompt = f"""You are a Lead Data Architect reviewing a client-submitted High-Level Architecture (HLA) Solution Design Document.
Analyze the following structured specifications extracted from the standardized HLA Template:

Control: {ctrl_num} - {ctrl_title}
Purpose: {ctrl_purpose}

1. Source Systems ({len(sources)} tables):
{json.dumps(sources[:6], indent=2)}

2. Data Extraction Strategies ({len(extractions or [])} rules):
{json.dumps((extractions or [])[:4], indent=2)}

3. Pre-Execution Filter Rules & Buckets ({len(rules.get('filter_rules', []))} rules):
{json.dumps(rules.get('filter_rules', [])[:6], indent=2)}

4. Target Report Model & Attribute Mappings ({len(mappings)} attributes, {direct_count} Direct, {derived_count} Derived):
{json.dumps(mappings[:8], indent=2)}

5. Dedicated Configuration Tables ({len(config_tables or [])} tables):
{json.dumps((config_tables or [])[:4], indent=2)}

6. Report Inventory & Execution Order ({len(report_inventory or [])} reports):
{json.dumps((report_inventory or [])[:4], indent=2)}

Provide a concise, professional Architectural Synthesis covering:
### 1. Executive Solution Summary
### 2. Ingestion & Extraction Orchestration
### 3. Pre-Execution Filtration & Balance Reconciliation Strategy
### 4. Target Data Model & Key Derivation Complexities
### 5. Configuration Tables & Report Dependency Orchestration
"""

    # 1. Try local Ollama
    response = call_ollama(prompt)
    if response:
        return {"content": response, "engine": "Ollama (local)"}

    # 2. Try Cloud API
    response = call_groq_or_openai(prompt)
    if response:
        return {"content": response, "engine": "Cloud LLM (Groq/OpenAI)"}

    # 3. Deterministic fallback synthesis adhering to the standard template
    src_systems = list(set(s.get("source_system") or s.get("source_db") for s in sources if s.get("source_system") or s.get("source_db")))
    systems_str = ", ".join(src_systems) if src_systems else "Enterprise Source Systems"

    synthesis = f"""### 1. Executive Solution Summary
**{ctrl_num}: {ctrl_title}** establishes an automated reconciliation and data governance pipeline across {len(sources)} source tables spanning {systems_str}. The architecture fulfills: *"{ctrl_purpose}"* by enforcing strict pre-execution data hygiene, balance dataset partitioning, dynamic configuration lookup, and automated KRI metric generation.

### 2. Ingestion & Extraction Orchestration
* **Snapshot Tables ({trunc_count})**: High-velocity daily snapshot datasets are acquired via Truncate and Load refresh mechanisms to maintain absolute synchronization with active operational states.
* **Audit & Chronological Tables ({append_count})**: High-watermark audit trails operate under Append loads, preserving chronological history while filtering for evaluation windows.
* **Extraction Slices**: Governed by {len(extractions or [])} extraction policies targeting rolling windows and delta timestamps.

### 3. Pre-Execution Filtration & Balance Reconciliation Strategy
Prior to reconciliation staging, raw records pass through {len(rules.get('filter_rules', []))} pre-execution validation rules:
* **Deduplication & Keys**: Discarding stream replays and multi-attribute duplicate telemetry.
* **Mandatory Field Integrity**: Dropping null combinations on critical identity attributes.
* **Exception Bucketing**: Excluded records are routed directly to dedicated exception tables, while clean balanced records feed downstream joins.

### 4. Target Data Model & Key Derivation Complexities
The target analytical model comprises **{len(mappings)} mapped attributes**:
* **{direct_count} Direct Attributes**: Sourced 1:1 from upstream operational systems.
* **{derived_count} Derived Attributes**: Governed by conditional multi-system lookups, fallback hierarchies, substring pattern matching, and business reconciliation logic.

### 5. Configuration Tables & Report Dependency Orchestration
* **Dynamic Config ({len(config_tables or [])} tables)**: Business exclusion parameters and threshold limits are maintained dynamically in dedicated config tables rather than hardcoded.
* **Execution Order ({len(report_inventory or [])} reports)**: Reports are sequenced according to dependency graphs to guarantee upstream dataset availability.
"""
    return {"content": synthesis, "engine": "Deterministic Architectural Engine (Ollama Standby)"}


# ── Document Generator ────────────────────────────────────────────────

def generate_specification_document(analysis_result, output_path):
    """
    Generates a professional Word document (.docx) strictly following the
    10-Section HLA Solution Design Specification standard.
    """
    doc = docx.Document()
    ctrl_overview = analysis_result.get("control_overview", {})
    ctrl_id = ctrl_overview.get("identification", {})

    # Title & Subtitle
    title_p = doc.add_paragraph()
    ctrl_num = ctrl_id.get("control_number") or "Control-01"
    ctrl_title = ctrl_id.get("control_title") or "Reconciliation Solution Design Document"
    title_run = title_p.add_run(f"{ctrl_num}: {ctrl_title}\nRECONCILIATION SOLUTION DESIGN SPECIFICATION")
    title_run.bold = True
    title_run.font.size = Pt(20)
    title_run.font.color.rgb = RGBColor(13, 27, 42)
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    sub_p = doc.add_paragraph()
    sub_run = sub_p.add_run("Standardized Enterprise Architecture Specification per Solution Design Template")
    sub_run.font.size = Pt(11)
    sub_run.font.italic = True
    sub_run.font.color.rgb = RGBColor(99, 110, 114)
    sub_p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph()

    # Metadata Table
    meta_table = doc.add_table(rows=5, cols=2)
    meta_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    compliance = analysis_result.get("template_compliance", {})
    comp_badge = f"Template Compliant ({compliance.get('compliance_score', 100)}%)" if compliance.get("is_compliant") else "Partial Compliance"

    meta_data = [
        ("Control Number & Name:", f"{ctrl_num} - {ctrl_title}"),
        ("Source Document:", analysis_result.get("original_name", "HLA Source Document")),
        ("Template Standard:", "HLA Solution Design Template (v0.1)"),
        ("Compliance Status:", comp_badge),
        ("Analysis Engine:", f"HLA AI Engine ({analysis_result.get('llm_synthesis', {}).get('engine', 'Automated')})"),
    ]
    for row_idx, (label, val) in enumerate(meta_data):
        row = meta_table.rows[row_idx]
        row.cells[0].paragraphs[0].add_run(label).bold = True
        row.cells[1].paragraphs[0].add_run(val)
        _set_cell_background(row.cells[0], "F4F6F9")
        _set_cell_margins(row.cells[0])
        _set_cell_margins(row.cells[1])

    doc.add_page_break()

    # Section 1: Executive Architectural Overview
    h1 = doc.add_heading("1. Executive Architectural Overview", level=1)
    h1.style.font.color.rgb = RGBColor(13, 27, 42)
    overview_text = analysis_result.get("llm_synthesis", {}).get("content", "")
    for paragraph in overview_text.split("\n\n"):
        if paragraph.strip():
            p = doc.add_paragraph()
            if paragraph.startswith("### "):
                run = p.add_run(paragraph.replace("### ", "").strip())
                run.bold = True
                run.font.size = Pt(12)
            else:
                p.add_run(paragraph.strip())

    # Section 2: Source Systems & Database Details
    h2 = doc.add_heading("2. Source Systems & Database Inventory", level=1)
    h2.style.font.color.rgb = RGBColor(13, 27, 42)
    doc.add_paragraph("Table details all source database schemas, tables, refresh schedules, and data load mechanisms:")

    sources = analysis_result.get("sources", [])
    if sources:
        src_table = doc.add_table(rows=len(sources) + 1, cols=6)
        src_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        headers = ["Source System", "DB", "Schema", "Table Name", "Refresh Timing", "Type of Load"]
        for c_idx, h in enumerate(headers):
            cell = src_table.rows[0].cells[c_idx]
            run = cell.paragraphs[0].add_run(h)
            run.bold = True
            run.font.color.rgb = RGBColor(255, 255, 255)
            _set_cell_background(cell, "1B2A4A")
            _set_cell_margins(cell)

        for r_idx, src in enumerate(sources):
            row = src_table.rows[r_idx + 1]
            vals = [
                src.get("source_system") or "-",
                src.get("source_db") or "-",
                src.get("source_schema") or "public",
                src.get("source_table") or "-",
                src.get("frequency") or "Daily",
                src.get("type_of_load") or "Truncate and load"
            ]
            for c_idx, v in enumerate(vals):
                cell = row.cells[c_idx]
                cell.paragraphs[0].add_run(str(v))
                bg = "F9FAFC" if r_idx % 2 == 1 else "FFFFFF"
                _set_cell_background(cell, bg)
                _set_cell_margins(cell)

    # Section 3: Data Extraction Requirements
    extractions = analysis_result.get("extraction_requirements", [])
    if extractions:
        doc.add_heading("3. Data Extraction Requirements", level=1)
        ext_table = doc.add_table(rows=len(extractions) + 1, cols=4)
        ext_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        ext_headers = ["Source Table", "Extraction Type", "Extraction Logic / Window", "Justification"]
        for c_idx, h in enumerate(ext_headers):
            cell = ext_table.rows[0].cells[c_idx]
            run = cell.paragraphs[0].add_run(h)
            run.bold = True
            run.font.color.rgb = RGBColor(255, 255, 255)
            _set_cell_background(cell, "1B2A4A")
            _set_cell_margins(cell)

        for r_idx, ext in enumerate(extractions):
            row = ext_table.rows[r_idx + 1]
            vals = [ext.get("source_table", "-"), ext.get("extraction_type", "Full Dump"), ext.get("extraction_logic", "-"), ext.get("justification", "-")]
            for c_idx, v in enumerate(vals):
                cell = row.cells[c_idx]
                cell.paragraphs[0].add_run(str(v))
                bg = "F9FAFC" if r_idx % 2 == 1 else "FFFFFF"
                _set_cell_background(cell, bg)
                _set_cell_margins(cell)

    # Section 4: Development Flow
    dev_flow = analysis_result.get("development_flow", [])
    if dev_flow:
        doc.add_heading("4. Development & Pipeline Execution Flow", level=1)
        for step in dev_flow:
            p = doc.add_paragraph(style='List Bullet')
            p.add_run(step)

    # Section 5: Filter Buckets & Source Rules
    filters = analysis_result.get("rules", {}).get("filter_rules", [])
    if filters:
        doc.add_heading("5. Filter Buckets & Source Table Rules", level=1)
        flt_table = doc.add_table(rows=len(filters) + 1, cols=4)
        flt_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        flt_headers = ["Source Table", "Filter Rule Applied", "Filtered-Out Bucket (Exceptions)", "Balanced Records (Pass-Through)"]
        for c_idx, h in enumerate(flt_headers):
            cell = flt_table.rows[0].cells[c_idx]
            run = cell.paragraphs[0].add_run(h)
            run.bold = True
            run.font.color.rgb = RGBColor(255, 255, 255)
            _set_cell_background(cell, "1B2A4A")
            _set_cell_margins(cell)

        for r_idx, f in enumerate(filters):
            row = flt_table.rows[r_idx + 1]
            vals = [f.get("source_table") or f.get("data_stream", "-"), f.get("rule_statement", "-"), f.get("filtered_out_bucket", "-"), f.get("balanced_bucket", "-")]
            for c_idx, v in enumerate(vals):
                cell = row.cells[c_idx]
                cell.paragraphs[0].add_run(str(v))
                bg = "F9FAFC" if r_idx % 2 == 1 else "FFFFFF"
                _set_cell_background(cell, bg)
                _set_cell_margins(cell)

    # Section 6: Filtration Procedure Steps
    filtration_steps = analysis_result.get("rules", {}).get("filtration_steps", [])
    if filtration_steps:
        doc.add_heading("6. Filtration Technical Procedure", level=1)
        step_table = doc.add_table(rows=len(filtration_steps) + 1, cols=3)
        step_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        step_headers = ["Step", "Description", "Logic / Rule Reference"]
        for c_idx, h in enumerate(step_headers):
            cell = step_table.rows[0].cells[c_idx]
            run = cell.paragraphs[0].add_run(h)
            run.bold = True
            run.font.color.rgb = RGBColor(255, 255, 255)
            _set_cell_background(cell, "1B2A4A")
            _set_cell_margins(cell)

        for r_idx, st in enumerate(filtration_steps):
            row = step_table.rows[r_idx + 1]
            vals = [st.get("step", str(r_idx+1)), st.get("description", "-"), st.get("logic_reference", "-")]
            for c_idx, v in enumerate(vals):
                cell = row.cells[c_idx]
                cell.paragraphs[0].add_run(str(v))
                bg = "F9FAFC" if r_idx % 2 == 1 else "FFFFFF"
                _set_cell_background(cell, bg)
                _set_cell_margins(cell)

    doc.add_page_break()

    # Section 7: Report Table Generation & Attribute Mapping Matrix
    h7 = doc.add_heading("7. Report Table Generation & Attribute Mapping Matrix", level=1)
    h7.style.font.color.rgb = RGBColor(13, 27, 42)
    mappings = analysis_result.get("mappings", [])
    if mappings:
        map_table = doc.add_table(rows=len(mappings) + 1, cols=5)
        map_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        map_headers = ["S.No", "Report Table Name", "Attribute Name", "Type", "Source Table.Field / Derivation Logic"]
        for c_idx, h in enumerate(map_headers):
            cell = map_table.rows[0].cells[c_idx]
            run = cell.paragraphs[0].add_run(h)
            run.bold = True
            run.font.color.rgb = RGBColor(255, 255, 255)
            _set_cell_background(cell, "1B2A4A")
            _set_cell_margins(cell)

        for r_idx, m in enumerate(mappings):
            row = map_table.rows[r_idx + 1]
            is_der = m.get("mapping_type") == "Derived"
            vals = [
                str(r_idx + 1),
                m.get("report_table_name") or m.get("source_table", "-"),
                m.get("target_column", "-"),
                m.get("mapping_type", "Direct"),
                m.get("derivation_logic", "")
            ]
            for c_idx, v in enumerate(vals):
                cell = row.cells[c_idx]
                run = cell.paragraphs[0].add_run(str(v))
                if c_idx == 3:
                    run.bold = True
                    run.font.color.rgb = RGBColor(192, 57, 43) if is_der else RGBColor(41, 128, 185)
                bg = "FFF8F0" if is_der else ("F9FAFC" if r_idx % 2 == 1 else "FFFFFF")
                _set_cell_background(cell, bg)
                _set_cell_margins(cell)

    # Section 8: Report Attributes & Metrics
    rep_metrics = analysis_result.get("report_attributes", [])
    if rep_metrics:
        doc.add_heading("8. Report Attributes & Report Numbers", level=1)
        rm_table = doc.add_table(rows=len(rep_metrics) + 1, cols=3)
        rm_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        rm_headers = ["Report Name", "Key Attributes Shown", "Report Numbers / Metrics (KRI counts, totals)"]
        for c_idx, h in enumerate(rm_headers):
            cell = rm_table.rows[0].cells[c_idx]
            run = cell.paragraphs[0].add_run(h)
            run.bold = True
            run.font.color.rgb = RGBColor(255, 255, 255)
            _set_cell_background(cell, "1B2A4A")
            _set_cell_margins(cell)

        for r_idx, rm in enumerate(rep_metrics):
            row = rm_table.rows[r_idx + 1]
            vals = [rm.get("report_name", "-"), rm.get("key_attributes", "-"), rm.get("metrics", "-")]
            for c_idx, v in enumerate(vals):
                cell = row.cells[c_idx]
                cell.paragraphs[0].add_run(str(v))
                bg = "F9FAFC" if r_idx % 2 == 1 else "FFFFFF"
                _set_cell_background(cell, bg)
                _set_cell_margins(cell)

    # Section 9: Configuration Values
    configs = analysis_result.get("config_tables", [])
    if configs:
        doc.add_heading("9. Configuration Values & Tables", level=1)
        cfg_table = doc.add_table(rows=len(configs) + 1, cols=4)
        cfg_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        cfg_headers = ["Config Table Name", "Purpose", "Sample Fields", "Consumed By (Report Name)"]
        for c_idx, h in enumerate(cfg_headers):
            cell = cfg_table.rows[0].cells[c_idx]
            run = cell.paragraphs[0].add_run(h)
            run.bold = True
            run.font.color.rgb = RGBColor(255, 255, 255)
            _set_cell_background(cell, "1B2A4A")
            _set_cell_margins(cell)

        for r_idx, cfg in enumerate(configs):
            row = cfg_table.rows[r_idx + 1]
            vals = [cfg.get("config_table_name", "-"), cfg.get("purpose", "-"), cfg.get("sample_fields", "-"), cfg.get("consumed_by", "-")]
            for c_idx, v in enumerate(vals):
                cell = row.cells[c_idx]
                cell.paragraphs[0].add_run(str(v))
                bg = "F9FAFC" if r_idx % 2 == 1 else "FFFFFF"
                _set_cell_background(cell, bg)
                _set_cell_margins(cell)

    # Section 10: Report Inventory & Generation Order
    inv = analysis_result.get("report_inventory", [])
    if inv:
        doc.add_heading("10. Report Inventory & Generation Order", level=1)
        inv_table = doc.add_table(rows=len(inv) + 1, cols=4)
        inv_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        inv_headers = ["Sequence #", "Report Name", "Depends On", "Notes"]
        for c_idx, h in enumerate(inv_headers):
            cell = inv_table.rows[0].cells[c_idx]
            run = cell.paragraphs[0].add_run(h)
            run.bold = True
            run.font.color.rgb = RGBColor(255, 255, 255)
            _set_cell_background(cell, "1B2A4A")
            _set_cell_margins(cell)

        for r_idx, item in enumerate(inv):
            row = inv_table.rows[r_idx + 1]
            vals = [item.get("sequence", str(r_idx+1)), item.get("report_name", "-"), item.get("depends_on", "None"), item.get("notes", "-")]
            for c_idx, v in enumerate(vals):
                cell = row.cells[c_idx]
                cell.paragraphs[0].add_run(str(v))
                bg = "F9FAFC" if r_idx % 2 == 1 else "FFFFFF"
                _set_cell_background(cell, bg)
                _set_cell_margins(cell)

    # Save document
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    doc.save(output_path)
    return output_path


# ── Main Orchestrator ─────────────────────────────────────────────────

def analyze_document(file_path):
    """
    Complete analysis pipeline strictly aligned with the HLA Solution Design Template:
    1. Parses document tables, headings, paragraphs across all 13 standard tables.
    2. Validates template conformance (compliance score and section checks).
    3. Extracts document control, control overview, DB connection parameters.
    4. Extracts sources (DB, schema, tables, refresh time, type of load).
    5. Extracts data extraction requirements (Table 7) & development flow (Section 4).
    6. Extracts filter rules, buckets (Table 8), and filtration procedure steps (Table 9).
    7. Extracts report table generation attribute mappings and derivation formulas (Table 10).
    8. Extracts report attributes & metrics (Table 11), config tables (Table 12), and report sequence (Table 13).
    9. Calls LLM (Ollama or Cloud) using structured JSON to synthesize architectural insights.
    10. Generates compliant .docx specification document.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in (".xlsx", ".xls"):
        raise ValueError(
            f"Unsupported file format '{ext}'. Only Excel workbooks (.xlsx, .xls) conforming to the HLA Control Specification template are accepted. Word (.docx, .doc), PDF, and other document formats are strictly not permitted."
        )

    from excel_analyzer import analyze_excel_specification
    return analyze_excel_specification(file_path)

    # 1. Extract all 13 tables & sections from the standard template
    doc_control = extract_document_control(doc)
    control_overview = extract_control_overview(doc)
    sources = extract_source_inventory(doc)
    extractions = extract_extraction_requirements(doc)
    dev_flow = extract_development_flow(doc)
    rules = extract_rules_and_filters(doc)
    catalog = extract_derivation_catalog(doc)
    mappings = extract_attribute_mappings(doc, catalog)
    report_attributes = extract_report_attributes_and_metrics(doc)
    config_tables = extract_configuration_tables(doc)
    report_inventory = extract_report_inventory_and_order(doc)
    appendix_items = extract_appendix_open_items(doc)

    raw_payload = {
        "document_control": doc_control,
        "control_overview": control_overview,
        "sources": sources,
        "extraction_requirements": extractions,
        "development_flow": dev_flow,
        "rules": rules,
        "mappings": mappings,
        "report_attributes": report_attributes,
        "config_tables": config_tables,
        "report_inventory": report_inventory,
        "appendix_open_items": appendix_items
    }

    # 2. Template Conformance Validation
    compliance = validate_template_compliance(doc, raw_payload)

    # Clean source database inventory - maintains single custom DB or Table 4 entries
    db_conns = control_overview.get("db_connections", [])
    source_db_map = {}
    for conn in db_conns:
        name = conn.get("source_db_name") or conn.get("database_name")
        if name and not str(name).startswith("<"):
            source_db_map[name.lower()] = {
                "source_db_name": name,
                "database_name": conn.get("database_name", name),
                "host": conn.get("host", "localhost"),
                "port": conn.get("port", "5432"),
                "schema_name": conn.get("schema_name", "public"),
                "connection_type": conn.get("connection_type", "PostgreSQL"),
                "credential_reference": conn.get("credential_reference", ""),
                "environment": conn.get("environment", "Production"),
                "tables": []
            }

    all_tbls = [s.get("source_table") or s.get("full_table_name") for s in sources]
    if not source_db_map:
        source_databases = [{
            "source_db_name": "Custom Source DB",
            "database_name": "custom_db",
            "host": "localhost",
            "port": "5432",
            "schema_name": "public",
            "connection_type": "PostgreSQL",
            "credential_reference": "",
            "environment": "Production",
            "tables": all_tbls
        }]
    else:
        first_db = list(source_db_map.values())[0]
        for src in sources:
            s_db = src.get("source_db") or src.get("source_system") or ""
            tbl_label = src.get("source_table") or src.get("full_table_name")
            matched = None
            for k, v in source_db_map.items():
                if s_db and (k in s_db.lower() or s_db.lower() in k):
                    matched = v
                    break
            target_entry = matched or first_db
            if tbl_label and tbl_label not in target_entry["tables"]:
                target_entry["tables"].append(tbl_label)
        source_databases = list(source_db_map.values())

    # 3. Structured LLM Synthesis (Ollama local / Cloud fallback)
    llm_synthesis = synthesize_llm_overview(
        control_info=control_overview,
        sources=sources,
        rules=rules,
        mappings=mappings,
        extractions=extractions,
        config_tables=config_tables,
        report_inventory=report_inventory
    )

    # 4. Prepare complete analysis payload
    original_name = os.path.basename(file_path)
    analysis_payload = {
        "original_name": original_name,
        "template_compliance": compliance,
        "document_control": doc_control,
        "control_overview": control_overview,
        "source_databases": source_databases,
        "sources": sources,
        "extraction_requirements": extractions,
        "development_flow": dev_flow,
        "rules": rules,
        "mappings": mappings,
        "derivation_catalog": catalog,
        "report_attributes": report_attributes,
        "config_tables": config_tables,
        "report_inventory": report_inventory,
        "appendix_open_items": appendix_items,
        "llm_synthesis": llm_synthesis,
        "summary_counts": {
            "total_sources": len(sources),
            "total_source_dbs": len(source_databases),
            "truncate_sources": sum(1 for s in sources if s.get('type_of_load') == 'Truncate and load'),
            "append_sources": sum(1 for s in sources if s.get('type_of_load') == 'Append'),
            "filter_rules": len(rules.get('filter_rules', [])),
            "balance_rules": len(rules.get('balance_rules', [])),
            "total_attributes": len(mappings),
            "direct_attributes": sum(1 for m in mappings if m.get('mapping_type') == 'Direct'),
            "derived_attributes": sum(1 for m in mappings if m.get('mapping_type') == 'Derived'),
            "config_tables": len(config_tables),
            "total_reports": len(report_inventory),
            "compliance_score": compliance.get("compliance_score", 100)
        }
    }

    # 5. Generate formatted specification document
    generated_folder = os.path.join(os.path.dirname(file_path), "generated")
    base_name = os.path.splitext(original_name)[0]
    output_filename = f"{base_name}_ETL_Specification.docx"
    output_doc_path = os.path.join(generated_folder, output_filename)

    generate_specification_document(analysis_payload, output_doc_path)
    analysis_payload["generated_doc_path"] = output_doc_path
    analysis_payload["generated_doc_filename"] = output_filename

    return analysis_payload
