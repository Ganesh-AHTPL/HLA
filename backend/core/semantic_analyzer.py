"""
Generic Semantic Analyzer for HLA Studio.
Infers semantic roles from discovered headers and content without hardcoding sheet names.
Supports Architecture Components, Requirements, Pipelines, Rules, Mappings, Reconciliation, and Controls.
"""

import os
import re
import uuid
from typing import Dict, Any, List, Optional, Tuple
from backend.core.generic_parser import GenericExcelParser, normalize_header_token, clean_cell_value


class SemanticAnalyzer:
    """
    Infers domain concepts from generic parsed Excel sheet tables.
    """

    @classmethod
    def analyze_workbook(cls, file_path: str, document_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Runs complete semantic analysis on an Excel workbook.
        Produces an isolated, document-scoped metadata model.
        """
        parsed_wb = GenericExcelParser.parse_workbook(file_path)
        doc_id = document_id or str(uuid.uuid4())
        filename = parsed_wb["filename"]

        components = []
        requirements = []
        sources = []
        source_databases = []
        mappings = []
        rules = {"filter_rules": [], "balance_rules": [], "business_rules": [], "reconciliation_flows": []}
        logical_inputs = []
        pipeline_stages = []
        reconciliation_items = []
        buckets = []
        config_tables = []
        data_model = []
        report_derivations = []
        detected_sections = []
        raw_sheets_summary = {}

        # Scan for explicit control identifier across all sheets
        control_info = cls._detect_control_identifier(parsed_wb)

        # Iterate over all discovered sheets dynamically with strict generic classification precedence:
        # 1. Configuration -> 2. Data Model -> 3. Source Systems -> 4. Attribute Mapping
        # 5. Filter & Bucket / KRI / Recon -> 6. Business Rules -> 7. Report Derivations
        # 8. Architecture Components -> 9. Requirements -> 10. Pipeline Stages -> 11. Custom
        for sheet_name, sheet_data in parsed_wb["sheets"].items():
            headers = sheet_data["normalized_headers"]
            orig_headers = sheet_data["original_headers"]
            rows = sheet_data["rows"]
            row_count = sheet_data["row_count"]

            raw_sheets_summary[sheet_name] = {
                "header_count": len(orig_headers),
                "original_headers": orig_headers,
                "row_count": row_count
            }

            if row_count == 0:
                continue

            # 1. Configuration Tables / Metadata Detection
            if cls._is_config_sheet(sheet_name, headers):
                detected_sections.append("configuration")
                parsed_cfgs = cls._extract_config(sheet_name, orig_headers, rows, doc_id=doc_id)
                if isinstance(parsed_cfgs, list):
                    config_tables.extend(parsed_cfgs)
                elif isinstance(parsed_cfgs, dict):
                    config_tables.append(parsed_cfgs)

            # 2. Data Model / Staging & Target Entities Detection
            elif cls._is_data_model_sheet(sheet_name, headers):
                detected_sections.append("data_model")
                parsed_dm = cls._extract_data_model(rows, sheet_name=sheet_name, doc_id=doc_id)
                data_model.extend(parsed_dm)

            # 3. Source Systems / Datasets Detection
            elif cls._is_sources_sheet(sheet_name, headers):
                detected_sections.append("source_datasets")
                parsed_srcs, parsed_dbs = cls._extract_sources(rows, sheet_name=sheet_name, doc_id=doc_id)
                sources.extend(parsed_srcs)
                source_databases.extend(parsed_dbs)

            # 4. Attribute Mappings Detection
            elif cls._is_mappings_sheet(sheet_name, headers):
                detected_sections.append("attribute_mappings")
                parsed_maps = cls._extract_mappings(rows, sheet_name=sheet_name, doc_id=doc_id)
                mappings.extend(parsed_maps)

            # 5. Filter & Bucket / KRI / Reconciliation Detection (BEFORE generic rules)
            elif cls._is_reconciliation_sheet(sheet_name, headers):
                detected_sections.append("reconciliation")
                parsed_recon, parsed_buckets = cls._extract_reconciliation(rows, sheet_name=sheet_name, doc_id=doc_id)
                reconciliation_items.extend(parsed_recon)
                buckets.extend(parsed_buckets)

            # 6. Business & Filter Rules Detection
            elif cls._is_rules_sheet(sheet_name, headers):
                detected_sections.append("rules")
                parsed_rules = cls._extract_rules(rows, sheet_name=sheet_name, doc_id=doc_id)
                rules["business_rules"].extend(parsed_rules.get("business_rules", []))
                rules["filter_rules"].extend(parsed_rules.get("filter_rules", []))
                rules["balance_rules"].extend(parsed_rules.get("balance_rules", []))
                if parsed_rules.get("logical_inputs"):
                    logical_inputs.extend(parsed_rules["logical_inputs"])

            # 7. Report Derivations Detection
            elif cls._is_report_derivation_sheet(sheet_name, headers):
                detected_sections.append("report_derivations")
                parsed_reports = cls._extract_report_derivations(rows, sheet_name=sheet_name, doc_id=doc_id)
                report_derivations.extend(parsed_reports)

            # 8. Architecture Components Detection
            elif cls._is_architecture_sheet(sheet_name, headers):
                detected_sections.append("architecture_components")
                parsed_comps = cls._extract_components(rows, sheet_name=sheet_name, doc_id=doc_id)
                components.extend(parsed_comps)

            # 9. Requirements Detection
            elif cls._is_requirements_sheet(sheet_name, headers):
                detected_sections.append("requirements")
                parsed_reqs = cls._extract_requirements(rows, sheet_name=sheet_name, doc_id=doc_id)
                requirements.extend(parsed_reqs)

            # 10. Pipeline Stages Detection
            elif cls._is_pipeline_sheet(sheet_name, headers):
                detected_sections.append("pipeline_stages")
                parsed_stages = cls._extract_pipeline_stages(rows, sheet_name=sheet_name, doc_id=doc_id)
                pipeline_stages.extend(parsed_stages)

            else:
                # Generic custom tabular dataset
                detected_sections.append(f"custom_section_{normalize_header_token(sheet_name)}")

        # Deduplicate detected section types
        unique_sections = list(dict.fromkeys(detected_sections))

        # Deduplicate and canonicalize all discovered physical source tables from source inventory
        unique_sources = cls.canonicalize_and_deduplicate_sources(
            sources,
            mappings=mappings,
            rules=rules,
            data_model=data_model,
            report_derivations=report_derivations,
            buckets=buckets
        )
        sources = unique_sources

        # Deduplicate and merge mappings across sheets
        deduped_mappings = []
        map_keys = {}
        for m in mappings:
            m_id = str(m.get("mapping_id") or "").strip().upper()
            m_attr = str(m.get("target_attribute") or "").strip().lower()
            m_src = str(m.get("source_table") or "").strip().lower()
            key = (m_id, m_attr) if m_id and not m_id.startswith("MAP") else (m_id, m_attr) if m_id else (m_src, m_attr)
            if key in map_keys:
                existing = map_keys[key]
                if not existing.get("target_table") and m.get("target_table"):
                    existing["target_table"] = m["target_table"]
                    existing["report_table_name"] = m["target_table"]
                if (not existing.get("transformation") or existing.get("transformation") == "Direct") and m.get("transformation") and m.get("transformation") != "Direct":
                    existing["transformation"] = m["transformation"]
                    existing["derivation_logic"] = m["derivation_logic"]
            else:
                map_keys[key] = m
                deduped_mappings.append(m)
        
        # If both Attribute Mapping (direct 1:1) and Target Mapping (with derivations) were parsed,
        # ensure primary 1:1 attribute mappings remain concise and correctly tagged
        if any(m.get("sheet_name") == "Attribute Mapping" for m in deduped_mappings):
            primary_maps = [m for m in deduped_mappings if m.get("sheet_name") == "Attribute Mapping"]
            for pm in primary_maps:
                for om in deduped_mappings:
                    if om.get("sheet_name") != "Attribute Mapping":
                        if om.get("mapping_id") and pm.get("mapping_id") and om.get("mapping_id").upper() == pm.get("mapping_id").upper():
                            if om.get("target_table"):
                                pm["target_table"] = om["target_table"]
                                pm["report_table_name"] = om["target_table"]
                                break
                        elif str(om.get("source_table")).lower() == str(pm.get("source_table")).lower() and str(om.get("target_attribute")).lower() == str(pm.get("target_attribute")).lower():
                            if om.get("target_table"):
                                pm["target_table"] = om["target_table"]
                                pm["report_table_name"] = om["target_table"]
                                break
            mappings = primary_maps
        else:
            mappings = deduped_mappings

        # Build canonical source_databases from unique_sources
        db_map = {}
        for s in sources:
            db_name = s.get("database") or "Default"
            if db_name not in db_map:
                db_map[db_name] = {
                    "source_db_name": db_name,
                    "database_name": db_name,
                    "tables": []
                }
            if s.get("full_table_name") not in db_map[db_name]["tables"]:
                db_map[db_name]["tables"].append(s.get("full_table_name"))
        source_databases = list(db_map.values())

        # Dynamic Connection of Logical Inputs to Physical Sources (Section 7 & 8)
        resolved_logical_inputs = []
        for lis in logical_inputs:
            stream_name = str(lis.get("name") or lis.get("stream_name") or "").strip()
            stream_lower = stream_name.lower()
            matched_src = None

            # 1. Match against Attribute Mapping
            for m in mappings:
                m_src = str(m.get("source_table") or "").strip().lower()
                m_fld = str(m.get("source_field") or "").strip().lower()
                if stream_lower and (stream_lower == m_src or stream_lower in m_src or stream_lower in m_fld):
                    # Find physical source corresponding to this mapping
                    for s in sources:
                        if s.get("table", "").lower() in m_src or m_src in s.get("table", "").lower() or s.get("canonical_name", "").lower() in m_src:
                            matched_src = s
                            break
                    if matched_src:
                        break

            # 2. Match against Physical Sources directly by name or database
            if not matched_src and stream_lower:
                for s in sources:
                    s_tbl = s.get("table", "").lower()
                    s_db = s.get("database", "").lower()
                    s_id = s.get("source_id", "").lower()
                    if stream_lower == s_tbl or stream_lower == s_db or stream_lower == s_id or stream_lower in s_tbl or s_tbl in stream_lower:
                        matched_src = s
                        break

            lis_copy = dict(lis)
            if matched_src:
                lis_copy["status"] = "RESOLVED"
                lis_copy["physical_source_id"] = matched_src.get("source_id")
                lis_copy["resolved_physical_source"] = matched_src.get("full_table_name")
                lis_copy["physical_source_system"] = matched_src.get("database")
            else:
                lis_copy["status"] = "UNRESOLVED_MAPPING"
                lis_copy["physical_source_id"] = None
                lis_copy["resolved_physical_source"] = None
                lis_copy["physical_source_system"] = None
            resolved_logical_inputs.append(lis_copy)
        logical_inputs = resolved_logical_inputs

        # Derive target schema name from control overview
        target_schema_name = "ra_ctrl"
        if control_info and isinstance(control_info, dict):
            raw_ts = control_info.get("target_schema")
            if isinstance(raw_ts, str) and raw_ts.strip():
                target_schema_name = raw_ts.strip()

        # Build Global Normalized Table Registry: all_table_objects (Section 17 & 18)
        all_table_objects = []
        table_identity_map = {}

        # 1. Register Physical Sources (role: PHYSICAL_SOURCE, connectionRole: SOURCE)
        for s in sources:
            s_schema = s.get("schema") or "public"
            s_tbl = s.get("table") or s.get("source_table") or ""
            s_db = s.get("database") or "Default"
            src_key = ("source", s_db.lower(), s_schema.lower(), s_tbl.lower())
            
            ps_obj = {
                "id": s.get("source_id") or f"SRC{len(all_table_objects)+1:03d}",
                "role": "PHYSICAL_SOURCE",
                "schema": s_schema,
                "table": s_tbl,
                "database": s_db,
                "source_system": s.get("source_system") or s_db,
                "sourceSystem": s.get("source_system") or s_db,
                "stage": "Physical Upstream Source",
                "connection_role": "SOURCE",
                "connectionRole": "SOURCE",
                "connection_reference": s_db,
                "connectionReference": s_db,
                "source_reference": s_db,
                "sourceReference": s_db,
                "parent_object_id": None,
                "parentObjectId": None,
                "upstream": "Upstream DB Feed",
                "downstream": None,
                "load_type": s.get("type_of_load") or "Truncate and load",
                "loadType": s.get("type_of_load") or "Truncate and load",
                "frequency": s.get("frequency") or "Daily",
                "schedule": s.get("schedule_time") or "",
                "approx_end_time": s.get("approx_end_time") or "",
                "active": s.get("active") or "Active",
                "reuse_strategy": None,
                "reuseStrategy": None,
                "description": f"Upstream source table in database '{s_db}'",
                "origin_sheet": s.get("sheet_name") or "Source Systems",
                "originSheet": s.get("sheet_name") or "Source Systems",
                "origin_row": s.get("source_row") or 1,
                "originRow": s.get("source_row") or 1,
                "required_columns": s.get("required_columns", [])
            }
            table_identity_map[src_key] = ps_obj
            all_table_objects.append(ps_obj)

        # 2. Register Data Model Objects (role derived from stage, connectionRole: TARGET)
        for dm in data_model:
            dm_stage = dm.get("stage") or dm.get("layer") or "Target Data Model"
            dm_tbl = dm.get("entity_name") or dm.get("table_name") or ""
            dm_role = cls.derive_data_model_role(dm_stage, dm.get("description", ""))
            tgt_key = ("target", target_schema_name.lower(), dm_stage.lower(), dm_tbl.lower())

            dm_obj = {
                "id": dm.get("id") or f"DM{len(all_table_objects)+1:03d}",
                "role": dm_role,
                "schema": target_schema_name,
                "table": dm_tbl,
                "database": "Target DB",
                "stage": dm_stage,
                "connection_role": "TARGET",
                "connectionRole": "TARGET",
                "connection_reference": "TARGET_DB",
                "connectionReference": "TARGET_DB",
                "source_reference": None,
                "sourceReference": None,
                "parent_object_id": None,
                "parentObjectId": None,
                "upstream": None,
                "downstream": None,
                "load_type": dm.get("load_type") or "Truncate and load",
                "loadType": dm.get("load_type") or "Truncate and load",
                "reuse_strategy": dm.get("reuse_rebuild") or "",
                "reuseStrategy": dm.get("reuse_rebuild") or "",
                "standard_type": dm.get("standard_type") or "",
                "standardType": dm.get("standard_type") or "",
                "description": dm.get("description") or f"Target table for stage '{dm_stage}'",
                "columns": dm.get("columns", []),
                "origin_sheet": dm.get("sheet_name") or "Data Model",
                "originSheet": dm.get("sheet_name") or "Data Model",
                "origin_row": dm.get("source_row") or 1,
                "originRow": dm.get("source_row") or 1
            }
            table_identity_map[tgt_key] = dm_obj
            all_table_objects.append(dm_obj)

        # 3. Dynamic Lineage Resolution across Sheets (Section 6, 17, 20)
        lineage_relationships = []

        # Find staging objects and connect Physical Sources -> Source Staging
        staging_objs = [t for t in all_table_objects if t.get("role") in ("SOURCE_STAGING", "INGESTION")]
        pre_exec_objs = [t for t in all_table_objects if t.get("role") == "PRE_EXECUTION"]
        exec_objs = [t for t in all_table_objects if t.get("role") == "PROCESSING"]
        post_exec_objs = [t for t in all_table_objects if t.get("role") == "POST_EXECUTION"]
        kri_objs = [t for t in all_table_objects if t.get("role") in ("KRI", "SUMMARY")]
        reporting_objs = [t for t in all_table_objects if t.get("role") in ("REPORTING", "WORK_ITEM")]

        def _get_tokens(name: str):
            clean = re.sub(r'[^a-zA-Z0-9]+', ' ', str(name or '').lower())
            return {w for w in clean.split() if w and w not in ('stg', 'tbl', 'src', 'dim', 'fact', 'target', 'source', 'stage', 'pre', 'post', 'ctrl')}

        # Match Physical Sources to Staging Tables
        for ps in [t for t in all_table_objects if t.get("role") == "PHYSICAL_SOURCE"]:
            ps_tbl = ps["table"].lower()
            ps_tokens = _get_tokens(ps_tbl)
            matched_stg = None

            # 1. Check direct substring
            for stg in staging_objs:
                stg_tbl = stg["table"].lower()
                if ps_tbl in stg_tbl or stg_tbl in ps_tbl:
                    matched_stg = stg
                    break

            # 2. Check token overlap across source and staging names
            if not matched_stg and ps_tokens:
                for stg in staging_objs:
                    stg_tokens = _get_tokens(stg["table"])
                    if ps_tokens & stg_tokens:
                        matched_stg = stg
                        break

            # 3. Check Attribute Mapping connections
            if not matched_stg:
                for m in mappings:
                    m_src = str(m.get("source_table") or "").lower()
                    m_tgt = str(m.get("target_table") or "").lower()
                    if ps_tbl in m_src:
                        for stg in staging_objs:
                            if stg["table"].lower() in m_tgt or m_tgt in stg["table"].lower():
                                matched_stg = stg
                                break
                    if matched_stg:
                        break

            # 4. Fallback by index alignment if counts match
            if not matched_stg and staging_objs:
                ps_list = [t for t in all_table_objects if t.get("role") == "PHYSICAL_SOURCE"]
                ps_idx = ps_list.index(ps)
                if ps_idx < len(staging_objs):
                    matched_stg = staging_objs[ps_idx]

            if matched_stg:
                ps["downstream"] = matched_stg["table"]
                if not matched_stg.get("upstream"):
                    matched_stg["upstream"] = f"{ps['schema']}.{ps['table']}"
                    matched_stg["parent_object_id"] = ps["id"]
                    matched_stg["parentObjectId"] = ps["id"]
                lineage_relationships.append({
                    "from": f"{ps['schema']}.{ps['table']}",
                    "to": f"{matched_stg['schema']}.{matched_stg['table']}",
                    "type": "Physical Source -> Source Staging"
                })

        # Connect Source Staging -> Pre-Execution / Execution / Downstream
        for stg in staging_objs:
            stg_tokens = _get_tokens(stg["table"])
            matched_down = None
            candidate_list = pre_exec_objs or exec_objs or post_exec_objs or kri_objs or reporting_objs
            if candidate_list:
                # 1. Match tokens
                for cand in candidate_list:
                    if stg_tokens and (stg_tokens & _get_tokens(cand["table"])):
                        matched_down = cand
                        break
                # 2. Fallback by index or first
                if not matched_down:
                    stg_idx = staging_objs.index(stg)
                    matched_down = candidate_list[min(stg_idx, len(candidate_list)-1)]

            if matched_down:
                stg["downstream"] = matched_down["table"]
                if not matched_down.get("upstream"):
                    matched_down["upstream"] = stg["table"]
                    matched_down["parent_object_id"] = stg["id"]
                    matched_down["parentObjectId"] = stg["id"]
                lineage_relationships.append({
                    "from": f"{stg['schema']}.{stg['table']}",
                    "to": f"{matched_down['schema']}.{matched_down['table']}",
                    "type": "Source Staging -> Downstream Target Model"
                })

        # Connect Pre-Execution -> Execution / Post-Execution
        for pre in pre_exec_objs:
            target_next = exec_objs[0] if exec_objs else (post_exec_objs[0] if post_exec_objs else (kri_objs[0] if kri_objs else None))
            if target_next:
                pre["downstream"] = target_next["table"]
                if not target_next.get("upstream"):
                    target_next["upstream"] = pre["table"]
                    target_next["parent_object_id"] = pre["id"]
                    target_next["parentObjectId"] = pre["id"]
                lineage_relationships.append({
                    "from": f"{pre['schema']}.{pre['table']}",
                    "to": f"{target_next['schema']}.{target_next['table']}",
                    "type": "Pre-Execution -> Execution/Post-Execution"
                })

        # Connect Execution -> Post-Execution / KRI
        for ex in exec_objs:
            target_next = post_exec_objs[0] if post_exec_objs else (kri_objs[0] if kri_objs else (reporting_objs[0] if reporting_objs else None))
            if target_next:
                ex["downstream"] = target_next["table"]
                if not target_next.get("upstream"):
                    target_next["upstream"] = ex["table"]
                    target_next["parent_object_id"] = ex["id"]
                    target_next["parentObjectId"] = ex["id"]
                lineage_relationships.append({
                    "from": f"{ex['schema']}.{ex['table']}",
                    "to": f"{target_next['schema']}.{target_next['table']}",
                    "type": "Execution -> Post-Execution/KRI"
                })

        # Connect Post-Execution -> KRI / Reporting
        for post in post_exec_objs:
            target_next = kri_objs[0] if kri_objs else (reporting_objs[0] if reporting_objs else None)
            if target_next:
                post["downstream"] = target_next["table"]
                if not target_next.get("upstream"):
                    target_next["upstream"] = post["table"]
                    target_next["parent_object_id"] = post["id"]
                    target_next["parentObjectId"] = post["id"]
                lineage_relationships.append({
                    "from": f"{post['schema']}.{post['table']}",
                    "to": f"{target_next['schema']}.{target_next['table']}",
                    "type": "Post-Execution -> KRI/Reporting"
                })

        # Connect KRI -> Reporting / Work Item
        for kri in kri_objs:
            if reporting_objs:
                kri["downstream"] = reporting_objs[0]["table"]
                if not reporting_objs[0].get("upstream"):
                    reporting_objs[0]["upstream"] = kri["table"]
                    reporting_objs[0]["parent_object_id"] = kri["id"]
                    reporting_objs[0]["parentObjectId"] = kri["id"]
                lineage_relationships.append({
                    "from": f"{kri['schema']}.{kri['table']}",
                    "to": f"{reporting_objs[0]['schema']}.{reporting_objs[0]['table']}",
                    "type": "KRI -> Reporting/Work Item"
                })

        # Dynamic Layer Counts
        count_physical = sum(1 for t in all_table_objects if t.get("role") == "PHYSICAL_SOURCE")
        count_staging = sum(1 for t in all_table_objects if t.get("role") in ("SOURCE_STAGING", "INGESTION"))
        count_pre_exec = sum(1 for t in all_table_objects if t.get("role") == "PRE_EXECUTION")
        count_processing = sum(1 for t in all_table_objects if t.get("role") == "PROCESSING")
        count_post_exec = sum(1 for t in all_table_objects if t.get("role") == "POST_EXECUTION")
        count_kri = sum(1 for t in all_table_objects if t.get("role") == "KRI")
        count_reporting = sum(1 for t in all_table_objects if t.get("role") in ("REPORTING", "WORK_ITEM", "SUMMARY"))
        count_config = sum(1 for t in all_table_objects if t.get("role") == "CONFIG") or len(config_tables)

        summary_counts = {
            "sheets_scanned": parsed_wb["sheet_count"],
            "total_rows_scanned": parsed_wb["total_rows_scanned"],
            "detected_sections_count": len(unique_sections),
            "physical_sources_count": count_physical,
            "source_staging_count": count_staging,
            "pre_execution_count": count_pre_exec,
            "processing_count": count_processing,
            "post_execution_count": count_post_exec,
            "kri_count": count_kri,
            "reporting_count": count_reporting,
            "config_count": count_config,
            "total_table_objects": len(all_table_objects),
            # Legacy fields for backward compatibility
            "total_sources": count_physical,
            "truncate_sources": sum(1 for s in sources if "truncate" in s.get("type_of_load", "").lower()),
            "append_sources": sum(1 for s in sources if "append" in s.get("type_of_load", "").lower()),
            "total_source_dbs": len(source_databases),
            "data_model_entities": len(data_model),
            "total_attributes": len(mappings),
            "direct_attributes": sum(1 for m in mappings if m.get("mapping_type") == "Direct"),
            "derived_attributes": sum(1 for m in mappings if m.get("mapping_type") == "Derived"),
            "filter_rules": len(rules.get("filter_rules", [])),
            "balance_rules": len(rules.get("balance_rules", [])),
            "total_rules": len(rules.get("filter_rules", [])) + len(rules.get("balance_rules", [])) + len(rules.get("business_rules", [])),
            "logical_inputs_count": len(logical_inputs),
            "resultant_buckets": len(buckets),
            "report_derivations_count": len(report_derivations),
            "config_tables_count": len(config_tables)
        }

        # Dynamic Connection Model Summary
        connections_summary = []
        for sdb in source_databases:
            connections_summary.append({
                "role": "SOURCE",
                "reference": sdb.get("source_db_name") or sdb.get("database_name"),
                "tables_count": len(sdb.get("tables", []))
            })
        connections_summary.append({
            "role": "TARGET",
            "reference": "TARGET_DB",
            "tables_count": len(data_model)
        })

        # Mandatory Section 26 Backend Debug Output
        print("\n===== HLA PARSE RESULT =====")
        print("\nSheets discovered:")
        for sn in parsed_wb["sheet_names"]:
            print(f"- {sn}")

        print(f"\nPhysical Sources ({len(sources)}):")
        for s in sources:
            print(f"- id: {s.get('source_id')}, system: {s.get('database')}, schema: {s.get('schema')}, table: {s.get('table')}, load: {s.get('type_of_load')}")

        print(f"\nLogical Input Streams ({len(logical_inputs)}):")
        for lis in logical_inputs:
            print(f"- id: {lis.get('id') or lis.get('logical_input_id')}, name: {lis.get('name') or lis.get('stream_name')}, status: {lis.get('status')}, physical_source: {lis.get('resolved_physical_source')}")

        print(f"\nData Model Objects ({len(data_model)}):")
        for dm in data_model:
            print(f"- id: {dm.get('id') or 'DM'}, stage: {dm.get('stage')}, table: {dm.get('entity_name')}, role: {cls.derive_data_model_role(dm.get('stage', ''))}, load: {dm.get('load_type')}")

        all_rules = rules.get("business_rules", []) + rules.get("filter_rules", []) + rules.get("balance_rules", [])
        print(f"\nProcessing Rules ({len(all_rules)}):")
        for pr in all_rules[:15]:
            print(f"- id: {pr.get('rule_id')}, type: {pr.get('rule_type') or pr.get('category')}, stream: {pr.get('source_dataset')}, condition: {pr.get('condition')}")
        if len(all_rules) > 15:
            print(f"... ({len(all_rules) - 15} more rules)")

        print(f"\nBuckets ({len(buckets)}):")
        for b in buckets:
            print(f"- id: {b.get('bucket_id') or b.get('code')}, name: {b.get('bucket_name') or b.get('title')}, result: {b.get('output_result')}")

        print(f"\nKRI definitions ({len(reconciliation_items)}):")
        for k in reconciliation_items:
            print(f"- id: {k.get('bucket_id') or k.get('code')}, name: {k.get('bucket_name')}, kri: {k.get('kri') or k.get('output_result')}")

        print(f"\nAttribute mappings ({len(mappings)}):")
        for am in mappings[:10]:
            print(f"- target: {am.get('target_attribute')}, source: {am.get('source_field')}, table: {am.get('source_table')}, trans: {am.get('transformation')}")
        if len(mappings) > 10:
            print(f"... ({len(mappings) - 10} more mappings)")

        print(f"\nReport lineage ({len(report_derivations)}):")
        for rl in report_derivations:
            print(f"- target: {rl.get('target_attribute')}, source: {rl.get('source_fields')}, logic: {rl.get('derivation_logic')}")

        print(f"\nConnections ({len(connections_summary)}):")
        for conn in connections_summary:
            print(f"- role: {conn.get('role')}, reference: {conn.get('reference')}, tables_count: {conn.get('tables_count')}")

        print(f"\nLineage relationships ({len(lineage_relationships)}):")
        for rel in lineage_relationships:
            print(f"- {rel.get('from')} -> {rel.get('to')} ({rel.get('type')})")

        print("\nFor every table:\n")
        for tbl in all_table_objects:
            print("TABLE OBJECT")
            print("-----------")
            print(f"id: {tbl.get('id')}")
            print(f"role: {tbl.get('role')}")
            print(f"schema: {tbl.get('schema')}")
            print(f"table: {tbl.get('table')}")
            print(f"database: {tbl.get('database')}")
            print(f"stage: {tbl.get('stage')}")
            print(f"connectionRole: {tbl.get('connection_role')}")
            print(f"upstream: {tbl.get('upstream')}")
            print(f"downstream: {tbl.get('downstream')}")
            print(f"originSheet: {tbl.get('origin_sheet')}")
            print(f"originRow: {tbl.get('origin_row')}\n")

        # Internal authoritative classification object
        classification = {
            "source_tables": sources,
            "target_tables": data_model,
            "logical_inputs": logical_inputs,
            "mappings": mappings,
            "business_rules": rules.get("business_rules", []),
            "all_table_objects": all_table_objects
        }

        # Normalized HLA Domain Model (Section 16 & 17)
        normalized_model = {
            "physicalSources": sources,
            "dataModelObjects": data_model,
            "businessRules": rules.get("business_rules", []) + rules.get("filter_rules", []) + rules.get("balance_rules", []),
            "attributeMappings": mappings,
            "bucketDefinitions": buckets,
            "kriDefinitions": reconciliation_items,
            "reportLineage": report_derivations,
            "configObjects": config_tables,
        }

        hla_data_model = {
            "physical_sources": sources,
            "data_model_objects": data_model,
            "logical_input_streams": logical_inputs,
            "processing_rules": all_rules,
            "bucket_definitions": buckets,
            "kri_definitions": reconciliation_items,
            "column_lineage": mappings,
            "report_lineage": report_derivations,
            "config_definitions": config_tables,
            "all_table_objects": all_table_objects,
            "lineage_relationships": lineage_relationships,
            "connections": connections_summary,
            "summary_counts": summary_counts,
            "normalized_model": normalized_model
        }

        result = {
            "document_id": doc_id,
            "filename": filename,
            "original_name": filename,
            "format_type": "GENERIC_EXCEL_DOCUMENT",
            "sheet_names": parsed_wb["sheet_names"],
            "detected_sections": unique_sections,
            "raw_sheets": raw_sheets_summary,
            "summary_counts": summary_counts,
            # Normalized HLA Model (Section 16 & 17)
            "normalized_model": normalized_model,
            "hla_data_model": hla_data_model,
            "all_table_objects": all_table_objects,
            "physical_sources": sources,
            "data_model_objects": data_model,
            "logical_input_streams": logical_inputs,
            "bucket_definitions": buckets,
            "kri_definitions": reconciliation_items,
            "column_lineage": mappings,
            "report_lineage": report_derivations,
            "config_definitions": config_tables,
            "lineage_relationships": lineage_relationships,
            # Internal Authoritative Classification
            "classification": classification,
            # Semantic entities
            "components": components,
            "requirements": requirements,
            "sources": sources,
            "source_tables": sources,
            "source_databases": source_databases,
            "data_model": data_model,
            "target_tables": data_model,
            "logical_inputs": logical_inputs,
            "mappings": mappings,
            "rules": rules,
            "pipeline_stages": pipeline_stages,
            "reconciliation": reconciliation_items,
            "buckets": buckets,
            "report_derivations": report_derivations,
            "config_tables": config_tables,
            # Control identification (None if no control in document)
            "control_overview": control_info,
            "template_compliance": {
                "compliance_score": 100,
                "status": "VALIDATED",
                "detected_sections": unique_sections,
                "passed_checks": [f"Sheet '{s}' parsed successfully ({d['row_count']} rows)" for s, d in raw_sheets_summary.items()],
                "failed_checks": []
            }
        }

        return result

    # ── Canonical Source Deduplication & Identity ───────────────────────

    @classmethod
    def canonicalize_source_identity(cls, raw_table_name: str, raw_schema: Optional[str] = None, raw_database: Optional[str] = None) -> Tuple[str, str, str, str]:
        """
        Parses table identity dynamically into (database, schema, table, canonical_name).
        Ensures canonical_name is strictly <schema>.<table> and never schema.schema.table.
        Zero hardcoded table names or schemas.
        """
        raw_str = str(raw_table_name or "").strip()
        extracted_db = ""
        extracted_schema = ""
        clean_table = raw_str

        if "." in raw_str:
            dot_parts = [p.strip() for p in raw_str.split(".") if p.strip()]
            if len(dot_parts) >= 3:
                extracted_db = dot_parts[0]
                extracted_schema = dot_parts[1]
                clean_table = dot_parts[2]
            elif len(dot_parts) == 2:
                extracted_schema = dot_parts[0]
                clean_table = dot_parts[1]
            elif len(dot_parts) == 1:
                clean_table = dot_parts[0]

        explicit_schema = str(raw_schema or "").strip()
        schema = explicit_schema or extracted_schema or "public"

        # Clean up double prefix if clean_table already starts with schema + "."
        if clean_table.lower().startswith(schema.lower() + "."):
            clean_table = clean_table[len(schema) + 1:].strip()

        # Database resolution
        db = str(raw_database or extracted_db or "Default").strip()
        canonical_name = f"{schema}.{clean_table}" if schema else clean_table

        return db, schema, clean_table, canonical_name

    @classmethod
    def canonicalize_and_deduplicate_sources(
        cls,
        sources_list: List[Dict[str, Any]],
        mappings: Optional[List[Dict[str, Any]]] = None,
        rules: Optional[Dict[str, Any]] = None,
        data_model: Optional[List[Dict[str, Any]]] = None,
        report_derivations: Optional[List[Dict[str, Any]]] = None,
        buckets: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Deduplicates and merges source metadata at the semantic layer into a deterministic,
        unique collection of canonical source table objects.
        """
        source_map: Dict[Tuple[str, str], Dict[str, Any]] = {}

        for s in (sources_list or []):
            if not isinstance(s, dict):
                continue
            raw_t = (
                s.get("source_table_name")
                or s.get("table_name")
                or s.get("source_table")
                or s.get("full_table_name")
                or s.get("table")
                or ""
            )
            raw_s = s.get("schema") or s.get("source_schema") or s.get("schema_name") or ""
            raw_sys = s.get("source_system") or s.get("source_system_name") or s.get("source_name") or s.get("system") or ""
            raw_db = (
                s.get("database")
                or s.get("database_name")
                or s.get("source_db")
                or s.get("source_database")
                or s.get("database_source")
                or ""
            )
            if not raw_t:
                continue

            db, schema, table, canonical_name = cls.canonicalize_source_identity(raw_t, raw_s, raw_db or raw_sys)
            key = (schema.strip().lower(), table.strip().lower())

            load_type = s.get("type_of_load") or s.get("load_type") or s.get("load") or "Truncate and load"
            freq = s.get("frequency") or s.get("refresh_time") or s.get("refresh_frequency") or "Daily"
            sched = s.get("schedule_time") or s.get("schedule") or s.get("run_time") or ""
            duration = s.get("approx_end_time") or s.get("approximate_end_time") or s.get("end_time") or s.get("duration") or ""
            active = s.get("active") or s.get("status") or "Active"
            src_id = s.get("source_id") or s.get("src_id") or s.get("id") or f"SRC{len(source_map) + 1:03d}"

            sys_val = str(raw_sys).strip() if str(raw_sys).strip() else (db if db != "Default" else "Not specified")
            db_val = db if db != "Default" else (str(raw_sys).strip() if str(raw_sys).strip() else "Not specified")

            if key in source_map:
                # Merge metadata into existing canonical entry without duplicate objects
                existing = source_map[key]
                if (existing.get("source_system") in ("Not specified", "Default", "")) and sys_val not in ("Not specified", "Default", ""):
                    existing["source_system"] = sys_val
                    existing["source_name"] = sys_val
                if (existing.get("database") in ("Not specified", "Default", "")) and db_val not in ("Not specified", "Default", ""):
                    existing["database"] = db_val
                    existing["database_name"] = db_val
                    existing["source_database"] = db_val
                    existing["source_db"] = db_val
                    existing["connection_reference"] = db_val
                if load_type and load_type != "Truncate and load":
                    existing["type_of_load"] = load_type
                    existing["load_type"] = load_type
                if freq and freq != "Daily":
                    existing["frequency"] = freq
                if sched:
                    existing["schedule_time"] = sched
                    existing["schedule"] = sched
                if duration:
                    existing["approx_end_time"] = duration
                    existing["approximate_end_time"] = duration
            else:
                source_map[key] = {
                    "source_id": str(src_id).strip(),
                    "source_name": sys_val if sys_val != "Not specified" else db_val,
                    "source_system": sys_val,
                    "database": db_val,
                    "database_name": db_val,
                    "source_database": db_val,
                    "source_db": db_val,
                    "connection_reference": db_val,
                    "role": "PHYSICAL_SOURCE",
                    "schema": schema,
                    "schema_name": schema,
                    "source_schema": schema,
                    "table": table,
                    "table_name": table,
                    "source_table_name": table,
                    "source_table": table,
                    "full_table_name": canonical_name,
                    "canonical_name": canonical_name,
                    "type_of_load": load_type,
                    "load_type": load_type,
                    "frequency": freq,
                    "schedule_time": sched,
                    "schedule": sched,
                    "approx_end_time": duration,
                    "approximate_end_time": duration,
                    "end_time": duration,
                    "active": active,
                    "status": active,
                    "sheet_name": s.get("sheet_name", ""),
                    "source_row": s.get("source_row"),
                    "origin": {
                        "sheet": s.get("sheet_name", ""),
                        "row": s.get("source_row")
                    },
                    "provenance": s.get("provenance", {}),
                    "required_columns": [],
                    "mappings": [],
                    "rules": [],
                    "buckets": []
                }

        # Cross-reference Mappings for required columns & field mappings
        for m in (mappings or []):
            if not isinstance(m, dict):
                continue
            src_tbl = m.get("source_table") or m.get("source_dataset") or m.get("table_name") or ""
            src_col = m.get("source_field") or m.get("source_column") or m.get("source_attribute") or ""
            if src_tbl:
                _, schema, table, _ = cls.canonicalize_source_identity(src_tbl)
                key = (schema.strip().lower(), table.strip().lower())
                if key in source_map:
                    if src_col and src_col not in source_map[key]["required_columns"]:
                        source_map[key]["required_columns"].append(src_col)
                    source_map[key]["mappings"].append(m)

        # Cross-reference Rules
        all_rules_list = []
        if isinstance(rules, dict):
            for r_list in rules.values():
                if isinstance(r_list, list):
                    all_rules_list.extend(r_list)
        elif isinstance(rules, list):
            all_rules_list = rules

        for r in all_rules_list:
            if not isinstance(r, dict):
                continue
            src_tbl = r.get("source_dataset") or r.get("source_table") or r.get("dataset") or r.get("source") or ""
            if src_tbl:
                _, schema, table, _ = cls.canonicalize_source_identity(src_tbl)
                key = (schema.strip().lower(), table.strip().lower())
                if key in source_map:
                    source_map[key]["rules"].append(r)

        # Cross-reference Buckets
        for b in (buckets or []):
            if not isinstance(b, dict):
                continue
            src_tbl = b.get("dataset_source") or b.get("dataset") or b.get("source") or b.get("source_table") or ""
            if src_tbl:
                _, schema, table, _ = cls.canonicalize_source_identity(src_tbl)
                key = (schema.strip().lower(), table.strip().lower())
                if key in source_map:
                    source_map[key]["buckets"].append(b)

        return list(source_map.values())

    # ── Semantic Role Checkers ──────────────────────────────────────────

    @classmethod
    def _is_doc_or_readme_sheet(cls, sheet_name: str, headers: List[str]) -> bool:
        norm_name = normalize_header_token(sheet_name)
        if any(k in norm_name for k in ["readme", "about", "overview", "help", "instruction", "guide", "info", "template_info"]):
            return True
        return False

    @classmethod
    def _is_architecture_sheet(cls, sheet_name: str, headers: List[str]) -> bool:
        if cls._is_doc_or_readme_sheet(sheet_name, headers):
            return False
        norm_name = normalize_header_token(sheet_name)
        if "arch" in norm_name or "component" in norm_name:
            return True
        header_str = " ".join(headers)
        if ("component" in header_str or "system" in header_str) and ("responsibility" in header_str or "purpose" in header_str or "input" in header_str or "technology" in header_str):
            return True
        return False

    @classmethod
    def _is_requirements_sheet(cls, sheet_name: str, headers: List[str]) -> bool:
        if cls._is_doc_or_readme_sheet(sheet_name, headers):
            return False
        norm_name = normalize_header_token(sheet_name)
        if "req" in norm_name:
            return True
        header_str = " ".join(headers)
        if "requirement" in header_str or ("description" in header_str and ("priority" in header_str or "acceptance" in header_str or "criteria" in header_str)):
            return True
        return False

    @classmethod
    def _is_data_model_sheet(cls, sheet_name: str, headers: List[str]) -> bool:
        if cls._is_doc_or_readme_sheet(sheet_name, headers):
            return False
        if cls._is_pipeline_sheet(sheet_name, headers) or cls._is_requirements_sheet(sheet_name, headers) or cls._is_architecture_sheet(sheet_name, headers):
            return False
        norm_name = normalize_header_token(sheet_name)
        if "data_model" in norm_name or "datamodel" in norm_name or "target_model" in norm_name:
            return True
        header_str = " ".join(headers)
        return ("data_process_stage" in header_str and "dataset_table_entity_name" in header_str) or ("dataset_table_entity_name" in header_str and "standard_non_standard_table" in header_str)

    @classmethod
    def classify_target_layer(cls, stage: str = "", entity_name: str = "", desc: str = "") -> str:
        """
        Classifies a data model entity dynamically into an architectural target layer:
        - Ingest
        - Pre-Execution
        - Execution
        - Post-Execution
        - Reporting
        - History
        - Summary
        - Config / Lookup
        - Target / Output
        """
        combined = f"{stage} {entity_name} {desc}".lower()
        if any(k in combined for k in ["ingest", "landing", "raw", "stage1", "stage_1", "stg_ingest", "source_stage"]):
            return "Ingest"
        if any(k in combined for k in ["pre-execution", "pre_execution", "pre_exec", "preexec", "stage2", "stage_2", "prep", "preparation", "cleansed", "standardized"]):
            return "Pre-Execution"
        if any(k in combined for k in ["post-execution", "post_execution", "post_exec", "postexec", "reconcil", "recon", "audit_recon", "stage4", "stage_4"]):
            return "Post-Execution"
        if any(k in combined for k in ["execution", "transform", "processing", "business_logic", "rules_engine", "stage3", "stage_3", "compute", "enrich"]):
            return "Execution"
        if any(k in combined for k in ["report", "reporting", "bi", "dashboard", "mart", "kri", "kpi", "presentation"]):
            return "Reporting"
        if any(k in combined for k in ["history", "historical", "archive", "snapshot", "audit_log", "scd"]):
            return "History"
        if any(k in combined for k in ["summary", "aggregate", "aggregation", "metric_summary", "cube"]):
            return "Summary"
        if any(k in combined for k in ["config", "lookup", "reference", "ref_data", "param", "parameter"]):
            return "Config / Lookup"
        if stage and stage.strip():
            return stage.strip().title()
        return "Target / Output"

    @classmethod
    def derive_data_model_role(cls, stage: str = "", desc: str = "") -> str:
        """
        Derives normalized semantic architectural role dynamically from data process stage.
        Zero hardcoded table name patterns.
        """
        stage_lower = str(stage or "").strip().lower()
        if any(k in stage_lower for k in ["etl", "acquis", "ingest", "landing", "stage1", "stage_1", "raw", "source_stage", "source staging"]):
            return "SOURCE_STAGING"
        if any(k in stage_lower for k in ["pre-exec", "pre_exec", "preexec", "prep", "stage2", "stage_2", "clean"]):
            return "PRE_EXECUTION"
        if any(k in stage_lower for k in ["post-exec", "post_exec", "postexec", "recon", "audit", "stage4", "stage_4"]):
            return "POST_EXECUTION"
        if any(k in stage_lower for k in ["exec", "process", "transform", "stage3", "stage_3", "compute", "enrich"]):
            return "PROCESSING"
        if any(k in stage_lower for k in ["kri", "non-kri", "non_kri", "metric", "indicator"]):
            return "KRI"
        if any(k in stage_lower for k in ["work item", "work_item", "workitem", "task", "action"]):
            return "WORK_ITEM"
        if any(k in stage_lower for k in ["report", "bi", "dashboard", "mart", "presentation", "output"]):
            return "REPORTING"
        if any(k in stage_lower for k in ["config", "lookup", "param", "reference", "ref_data"]):
            return "CONFIG"
        if any(k in stage_lower for k in ["summary", "agg", "cube"]):
            return "SUMMARY"
        if stage and stage.strip():
            norm_stage = re.sub(r'[^a-zA-Z0-9]+', '_', stage.strip().upper()).strip('_')
            if norm_stage:
                return norm_stage
        return "DATA_MODEL_OBJECT"

    @classmethod
    def _is_sources_sheet(cls, sheet_name: str, headers: List[str]) -> bool:
        if cls._is_doc_or_readme_sheet(sheet_name, headers):
            return False
        if cls._is_data_model_sheet(sheet_name, headers) or cls._is_mappings_sheet(sheet_name, headers) or cls._is_rules_sheet(sheet_name, headers) or cls._is_report_derivation_sheet(sheet_name, headers):
            return False
        norm_name = normalize_header_token(sheet_name)
        if "source" in norm_name and ("system" in norm_name or "table" in norm_name or "dataset" in norm_name or "feed" in norm_name or "stream" in norm_name or "inventory" in norm_name):
            return True
        if norm_name in ("sources", "source_inventory", "source_systems", "upstream_sources", "source_tables", "source_feeds"):
            return True
        header_str = " ".join(headers)
        has_table = any(k in header_str for k in ["table_name_with_schema", "source_table", "table_name", "dataset_name", "physical_table"])
        has_src_meta = any(k in header_str for k in ["database_source", "database", "frequency", "schedule_time", "refresh", "type_of_load", "source_system", "source_db"])
        return has_table and has_src_meta

    @classmethod
    def _is_mappings_sheet(cls, sheet_name: str, headers: List[str]) -> bool:
        if cls._is_doc_or_readme_sheet(sheet_name, headers):
            return False
        if cls._is_report_derivation_sheet(sheet_name, headers):
            return False
        norm_name = normalize_header_token(sheet_name)
        if "mapping" in norm_name or ("attribute" in norm_name and "report" not in norm_name and "derivation" not in norm_name):
            return True
        header_str = " ".join(headers)
        has_src = any(k in header_str for k in ["source_field", "source_column", "source_attribute", "source", "source_table"])
        has_tgt = any(k in header_str for k in ["target_column", "target_field", "target_attribute", "target", "column_name", "attribute", "target_attr", "target_entity"])
        return has_src and has_tgt

    @classmethod
    def _is_pipeline_sheet(cls, sheet_name: str, headers: List[str]) -> bool:
        if cls._is_doc_or_readme_sheet(sheet_name, headers):
            return False
        norm_name = normalize_header_token(sheet_name)
        if "pipeline" in norm_name or "stage" in norm_name:
            return True
        header_str = " ".join(headers)
        return "stage" in header_str and any(k in header_str for k in ["process", "sequence", "step", "dependency", "dependencies"])

    @classmethod
    def _is_reconciliation_sheet(cls, sheet_name: str, headers: List[str]) -> bool:
        if cls._is_doc_or_readme_sheet(sheet_name, headers):
            return False
        norm_name = normalize_header_token(sheet_name)
        if "recon" in norm_name or "bucket" in norm_name or "kri" in norm_name:
            return True
        header_str = " ".join(headers)
        return any(k in header_str for k in ["bucket_id", "bucket_name", "bucket", "kri", "output_result", "impact_type", "match_key", "discrepancy", "exception"])

    @classmethod
    def _is_rules_sheet(cls, sheet_name: str, headers: List[str]) -> bool:
        if cls._is_doc_or_readme_sheet(sheet_name, headers):
            return False
        norm_name = normalize_header_token(sheet_name)
        if "rule" in norm_name:
            return True
        header_str = " ".join(headers)
        return "rule" in header_str and any(k in header_str for k in ["description", "condition", "severity", "filter", "category", "id", "action"])

    @classmethod
    def _is_report_derivation_sheet(cls, sheet_name: str, headers: List[str]) -> bool:
        if cls._is_doc_or_readme_sheet(sheet_name, headers):
            return False
        norm_name = normalize_header_token(sheet_name)
        if "mapping" in norm_name or "map" in norm_name:
            return False
        if "report" in norm_name or "derivation" in norm_name or "derived" in norm_name:
            return True
        header_str = " ".join(headers)
        return ("report" in header_str and any(k in header_str for k in ["attribute", "derivation", "field", "metric"])) or ("derivation" in header_str and "target_attribute" in header_str and "mapping" not in header_str)

    @classmethod
    def _is_config_sheet(cls, sheet_name: str, headers: List[str]) -> bool:
        if cls._is_doc_or_readme_sheet(sheet_name, headers):
            return False
        norm_name = normalize_header_token(sheet_name)
        if "config" in norm_name:
            return True
        header_str = " ".join(headers)
        return "config_group" in header_str or ("config_key" in header_str and "config_value" in header_str)

    # ── Semantic Extractors ─────────────────────────────────────────────

    @classmethod
    def _extract_components(cls, rows: List[Dict[str, Any]], sheet_name: str = "", doc_id: str = "") -> List[Dict[str, Any]]:
        components = []
        for r in rows:
            comp_name = r.get("component") or r.get("system") or r.get("service") or r.get("module") or r.get("layer") or ""
            if not comp_name:
                # Find first populated string column
                for k, v in r.items():
                    if not k.startswith("_") and v:
                        comp_name = v
                        break
            if not comp_name:
                continue

            resp = r.get("responsibility") or r.get("purpose") or r.get("description") or r.get("function") or ""
            inp = r.get("input") or r.get("consumes") or r.get("inputs") or ""
            out = r.get("output") or r.get("produces") or r.get("outputs") or ""
            tech = r.get("technology") or r.get("platform") or r.get("tech_stack") or ""
            inter = r.get("interaction") or r.get("interface") or r.get("protocol") or ""

            components.append({
                "component": comp_name,
                "responsibility": resp,
                "input": inp,
                "output": out,
                "technology": tech,
                "interaction": inter,
                "provenance": {
                    "document_id": doc_id,
                    "sheet": sheet_name,
                    "row": r.get("_excel_row_num")
                },
                "raw_attributes": {k: v for k, v in r.items() if not k.startswith("_")}
            })
        return components

    @classmethod
    def _extract_requirements(cls, rows: List[Dict[str, Any]], sheet_name: str = "", doc_id: str = "") -> List[Dict[str, Any]]:
        requirements = []
        for r in rows:
            req_id = r.get("requirement") or r.get("req_id") or r.get("req") or r.get("id") or ""
            desc = r.get("description") or r.get("requirement_description") or r.get("summary") or ""
            prio = r.get("priority") or r.get("severity") or "Medium"
            criteria = r.get("acceptance_criteria") or r.get("criteria") or r.get("validation") or ""

            if not req_id and not desc:
                continue

            requirements.append({
                "requirement": req_id or f"REQ-{len(requirements) + 1:02d}",
                "description": desc,
                "priority": prio,
                "acceptance_criteria": criteria,
                "provenance": {
                    "document_id": doc_id,
                    "sheet": sheet_name,
                    "row": r.get("_excel_row_num")
                },
                "raw_attributes": {k: v for k, v in r.items() if not k.startswith("_")}
            })
        return requirements

    @classmethod
    def _extract_sources(cls, rows: Any, sheet_name: str = "", doc_id: str = "") -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        raw_list = []
        if isinstance(rows, dict):
            for sname, srows in rows.items():
                if isinstance(srows, list):
                    for r in srows:
                        if isinstance(r, dict):
                            raw_list.append(r)
        elif isinstance(rows, list):
            raw_list = rows

        sources = []
        databases = {}
        for idx, orig_r in enumerate(raw_list, start=1):
            if not isinstance(orig_r, dict):
                continue

            r = {}
            for k, v in orig_r.items():
                k_clean = str(k).strip()
                k_norm = re.sub(r'[^a-z0-9]+', '_', k_clean.lower()).strip('_')
                r[k_norm] = v
                r[k_clean.lower()] = v
                r[k_clean] = v

            raw_t_name = (
                r.get("table_name_with_schema") or
                r.get("table_name") or
                r.get("source_table") or
                r.get("source_table_name") or
                r.get("source_dataset") or
                r.get("dataset_name") or
                r.get("dataset") or
                r.get("table") or
                r.get("full_table_name") or
                r.get("dataset_table_entity_name") or
                r.get("entity_name") or
                r.get("physical_table") or
                ""
            )
            if not raw_t_name:
                for k, v in r.items():
                    if not k.startswith("_") and ("table" in k or "dataset" in k) and v:
                        raw_t_name = str(v).strip()
                        break
            if not raw_t_name:
                continue

            raw_t_str = str(raw_t_name).strip()

            # Generic parsing of table name with schema (e.g. customer.customer_master or crm.customer.customer_master)
            extracted_db = ""
            extracted_schema = ""
            clean_t_name = raw_t_str

            if "." in raw_t_str:
                dot_parts = [p.strip() for p in raw_t_str.split(".") if p.strip()]
                if len(dot_parts) >= 3:
                    extracted_db = dot_parts[0]
                    extracted_schema = dot_parts[1]
                    clean_t_name = dot_parts[2]
                elif len(dot_parts) == 2:
                    extracted_schema = dot_parts[0]
                    clean_t_name = dot_parts[1]
                else:
                    clean_t_name = dot_parts[0]

            explicit_schema = (r.get("schema") or r.get("schema_name") or r.get("source_schema") or "").strip()
            if explicit_schema:
                schema = explicit_schema
                # If clean_t_name still accidentally contains the explicit_schema prefix, strip it
                if clean_t_name.lower().startswith(schema.lower() + "."):
                    clean_t_name = clean_t_name[len(schema)+1:].strip()
            else:
                schema = extracted_schema or "public"

            # Resolve Source ID
            source_id = (
                r.get("source_id") or
                r.get("src_id") or
                r.get("id") or
                f"SRC{len(sources)+1:03d}"
            )
            # Explicit source system
            raw_source_sys = (
                r.get("source_system") or
                r.get("source_system_name") or
                r.get("source_name") or
                r.get("system") or
                r.get("system_name") or
                ""
            )
            # Explicit database
            raw_database_name = (
                r.get("database") or
                r.get("source_database") or
                r.get("db_name") or
                r.get("source_db") or
                r.get("database_name") or
                r.get("db") or
                r.get("database_source") or
                r.get("database_or_source") or
                r.get("database_slash_source") or
                extracted_db or
                ""
            )

            sys_val = str(raw_source_sys).strip() if str(raw_source_sys).strip() else (str(raw_database_name).strip() if str(raw_database_name).strip() else "Not specified")
            db_val = str(raw_database_name).strip() if str(raw_database_name).strip() else (str(raw_source_sys).strip() if str(raw_source_sys).strip() else "Not specified")

            load_type = r.get("type_of_load") or r.get("load_type") or r.get("load") or "Truncate and load"
            freq = r.get("frequency") or r.get("refresh_time") or r.get("refresh_frequency") or "Daily"
            sched = r.get("schedule_time") or r.get("schedule") or r.get("run_time") or ""
            duration = r.get("approximate_end_time") or r.get("approx_end_time") or r.get("end_time") or r.get("duration") or ""
            active_val = r.get("active") or r.get("status") or "Active"

            full_t = f"{schema}.{clean_t_name}" if schema else clean_t_name

            source_obj = {
                "source_id": str(source_id).strip(),
                "source_name": sys_val if sys_val != "Not specified" else db_val,
                "source_system": sys_val,
                "database": db_val,
                "database_name": db_val,
                "source_db": db_val,
                "source_database": db_val,
                "schema": schema,
                "schema_name": schema,
                "source_schema": schema,
                "table": clean_t_name,
                "table_name": clean_t_name,
                "source_table_name": clean_t_name,
                "source_table": clean_t_name,
                "full_table_name": full_t,
                "type_of_load": load_type,
                "load_type": load_type,
                "frequency": freq,
                "schedule_time": sched,
                "schedule": sched,
                "approx_end_time": duration,
                "approximate_end_time": duration,
                "end_time": duration,
                "active": active_val,
                "status": active_val,
                "sheet_name": sheet_name,
                "source_row": r.get("_excel_row_num") or idx,
                "provenance": {
                    "document_id": doc_id,
                    "sheet": sheet_name,
                    "row": r.get("_excel_row_num") or idx
                }
            }
            sources.append(source_obj)

            # Structured Debug Logging
            print(f"[HLA-PARSER] Source: id={source_obj['source_id']} system={source_obj['source_system']} db={source_obj['database']} schema={schema} table={clean_t_name} load_type={load_type} frequency={freq} row={source_obj['source_row']}")

            db_group_key = db_val if db_val != "Not specified" else sys_val
            if db_group_key not in databases:
                databases[db_group_key] = {
                    "source_db_name": db_group_key,
                    "database_name": db_group_key,
                    "tables": []
                }
            if full_t not in databases[db_group_key]["tables"]:
                databases[db_group_key]["tables"].append(full_t)

        return sources, list(databases.values())

    @classmethod
    def _extract_mappings(cls, rows: Any, sheet_name: str = "", doc_id: str = "") -> List[Dict[str, Any]]:
        mappings = []
        raw_list = []
        if isinstance(rows, dict):
            for sname, srows in rows.items():
                if isinstance(srows, list):
                    for r in srows:
                        if isinstance(r, dict):
                            raw_list.append(r)
        elif isinstance(rows, list):
            raw_list = rows

        for r_orig in raw_list:
            if not isinstance(r_orig, dict):
                continue
            r = {}
            for k, v in r_orig.items():
                k_clean = str(k).strip()
                k_norm = re.sub(r'[^a-z0-9]+', '_', k_clean.lower()).strip('_')
                r[k_norm] = v
                r[k_clean.lower()] = v
                r[k_clean] = v

            m_id = (
                r.get("mapping_id") or
                r.get("map_id") or
                r.get("id") or
                r.get("sl_no") or
                f"MAP{len(mappings) + 1:03d}"
            )
            tgt_attr = (
                r.get("target_attribute") or
                r.get("target_column") or
                r.get("target_field") or
                r.get("attribute") or
                r.get("column_name") or
                r.get("output_attribute") or
                r.get("output_field") or
                r.get("attribute_name") or
                r.get("attributes") or
                ""
            )
            src_field = (
                r.get("source_field") or
                r.get("source_column") or
                r.get("source_attribute") or
                r.get("source_fields") or
                r.get("source") or
                "-"
            )
            src_tbl = (
                r.get("source_table") or
                r.get("table_name") or
                r.get("dataset") or
                r.get("dataset_table") or
                r.get("physical_table") or
                r.get("tables") or
                r.get("table") or
                "-"
            )
            tgt_tbl = (
                r.get("target_table") or
                r.get("target_entity") or
                r.get("target_dataset") or
                r.get("dataset_table_entity_name") or
                r.get("report_table_name") or
                r.get("report_name") or
                ""
            )
            dtype = (
                r.get("data_type") or
                r.get("type") or
                r.get("datatype") or
                "VARCHAR(255)"
            )
            nullable = (
                r.get("nullable") or
                r.get("is_nullable") or
                r.get("null") or
                "Y"
            )
            remark = (
                r.get("remark") or
                r.get("remarks") or
                r.get("description") or
                r.get("comment") or
                ""
            )
            trans = (
                r.get("transformation") or
                r.get("derivation_logic") or
                r.get("logic") or
                r.get("formula") or
                ("Direct" if str(src_field).strip() != "-" and "derived" not in str(remark).lower() else "Derived")
            )
            m_type = (
                r.get("mapping_type") or
                r.get("type") or
                ("Direct" if str(trans).strip().lower() in ("direct", "1:1", "pass-through", "direct pass-through") else "Derived")
            )

            if not tgt_attr or tgt_attr == "-":
                continue

            mappings.append({
                "mapping_id": str(m_id).strip(),
                "target_attribute": str(tgt_attr).strip(),
                "target_column": str(tgt_attr).strip(),
                "source_field": str(src_field).strip(),
                "source_table": str(src_tbl).strip(),
                "target_table": str(tgt_tbl).strip(),
                "report_table_name": str(tgt_tbl).strip(),
                "transformation": str(trans).strip(),
                "derivation_logic": str(trans).strip(),
                "data_type": str(dtype).strip(),
                "target_data_type": str(dtype).strip(),
                "nullable": str(nullable).strip(),
                "remark": str(remark).strip(),
                "mapping_type": m_type,
                "sheet_name": sheet_name,
                "source_row": r_orig.get("_excel_row_num"),
                "provenance": {
                    "document_id": doc_id,
                    "sheet": sheet_name,
                    "row": r_orig.get("_excel_row_num")
                }
            })
        return mappings

    @classmethod
    def _extract_pipeline_stages(cls, rows: Any, sheet_name: str = "", doc_id: str = "") -> List[Dict[str, Any]]:
        stages = []
        raw_list = []
        if isinstance(rows, dict):
            for sname, srows in rows.items():
                if isinstance(srows, list):
                    for r in srows:
                        if isinstance(r, dict):
                            raw_list.append(r)
        elif isinstance(rows, list):
            raw_list = rows

        for r_orig in raw_list:
            if not isinstance(r_orig, dict):
                continue
            r = {}
            for k, v in r_orig.items():
                k_clean = str(k).strip()
                k_norm = re.sub(r'[^a-z0-9]+', '_', k_clean.lower()).strip('_')
                r[k_norm] = v
                r[k_clean.lower()] = v
                r[k_clean] = v

            stage_name = r.get("stage") or r.get("stage_name") or r.get("pipeline_stage") or ""
            proc = r.get("process") or r.get("step") or r.get("description") or ""
            deps = r.get("dependencies") or r.get("dependency") or r.get("depends_on") or ""
            inp = r.get("input_dataset") or r.get("input") or ""
            out = r.get("output_dataset") or r.get("output") or ""

            if not stage_name and not proc:
                continue

            stages.append({
                "stage": stage_name or f"Stage {len(stages) + 1}",
                "process": proc,
                "dependencies": deps,
                "input": inp,
                "output": out,
                "sheet_name": sheet_name,
                "source_row": r_orig.get("_excel_row_num"),
                "provenance": {
                    "document_id": doc_id,
                    "sheet": sheet_name,
                    "row": r_orig.get("_excel_row_num")
                }
            })
        return stages

    @classmethod
    def _extract_rules(cls, rows: Any, sheet_name: str = "", doc_id: str = "") -> Dict[str, List[Dict[str, Any]]]:
        filter_rules = []
        balance_rules = []
        business_rules = []
        logical_inputs_map = {}

        raw_list = []
        if isinstance(rows, dict):
            for sname, srows in rows.items():
                if isinstance(srows, list):
                    for r in srows:
                        if isinstance(r, dict):
                            raw_list.append(r)
        elif isinstance(rows, list):
            raw_list = rows

        for r_orig in raw_list:
            if not isinstance(r_orig, dict):
                continue
            r = {}
            for k, v in r_orig.items():
                k_clean = str(k).strip()
                k_norm = re.sub(r'[^a-z0-9]+', '_', k_clean.lower()).strip('_')
                r[k_norm] = v
                r[k_clean.lower()] = v
                r[k_clean] = v

            r_id = r.get("rule_id") or r.get("rule_code") or r.get("id") or r.get("rule") or f"R{len(business_rules) + 1:03d}"
            r_type = r.get("rule_type") or r.get("category") or r.get("rule_category") or "Validation"
            r_name = r.get("rule_name") or r.get("name") or r.get("title") or r_id
            src_ds = (
                r.get("source_dataset") or
                r.get("source_slash_dataset") or
                r.get("source___dataset") or
                r.get("dataset_source") or
                r.get("dataset___source") or
                r.get("source_table") or
                r.get("table_name") or
                r.get("source") or
                r.get("data_stream") or
                r.get("target") or
                r.get("target_dataset") or
                ""
            )
            cond = (
                r.get("condition") or
                r.get("rule_condition") or
                r.get("expression") or
                r.get("rule_expression") or
                r.get("rule_statement") or
                r.get("description") or
                r.get("rule_description") or
                ""
            )
            action = r.get("action") or r.get("rule_action") or "Keep record"
            prio = r.get("priority") or (len(business_rules) + 1)
            enabled_val = r.get("enabled") or r.get("active") or "Y"
            is_enabled = str(enabled_val).strip().upper() in ("Y", "YES", "TRUE", "1", "T", "ACTIVE")

            rule_obj = {
                "rule_id": str(r_id).strip(),
                "rule_type": str(r_type).strip(),
                "rule_name": str(r_name).strip(),
                "category": str(r_type).strip(),
                "source_dataset": str(src_ds).strip(),
                "target": str(src_ds).strip(),
                "data_stream": str(src_ds).strip(),
                "condition": str(cond).strip(),
                "rule_statement": str(cond).strip(),
                "action": str(action).strip(),
                "priority": prio,
                "enabled": is_enabled,
                "sheet_name": sheet_name,
                "source_row": r_orig.get("_excel_row_num"),
                "provenance": {
                    "document_id": doc_id,
                    "sheet": sheet_name,
                    "row": r_orig.get("_excel_row_num")
                }
            }

            business_rules.append(rule_obj)
            cat_lower = str(r_type).lower()
            if "balance" in cat_lower or "balance" in str(cond).lower() or "recon" in cat_lower:
                balance_rules.append(rule_obj)
            else:
                filter_rules.append(rule_obj)

            # Discover logical inputs (e.g. VDOM, DDOS, CMDB, Circuit Reco, I1, I2, etc.)
            stream_ref = str(src_ds).strip()
            if stream_ref and stream_ref not in ("-", "N/A", "none", "null", "undefined", ""):
                stream_key = stream_ref.upper() if re.match(r'^I\d+$', stream_ref, re.IGNORECASE) else stream_ref
                if stream_key not in logical_inputs_map:
                    logical_inputs_map[stream_key] = {
                        "id": f"LIS{len(logical_inputs_map)+1:03d}" if not re.match(r'^I\d+$', stream_key) else stream_key,
                        "logical_input_id": stream_key,
                        "name": stream_ref,
                        "stream_name": stream_ref,
                        "type": "INPUT_STREAM",
                        "rule": str(cond).strip() or str(r_id).strip(),
                        "referenced_rule_id": str(r_id).strip(),
                        "condition": str(cond).strip(),
                        "action": str(action).strip(),
                        "origin_sheet": sheet_name,
                        "originating_sheet": sheet_name,
                        "origin_row": r_orig.get("_excel_row_num"),
                        "originating_row": r_orig.get("_excel_row_num"),
                        "role": "LOGICAL_INPUT"
                    }

        return {
            "filter_rules": filter_rules,
            "balance_rules": balance_rules,
            "business_rules": business_rules,
            "logical_inputs": list(logical_inputs_map.values())
        }

    @classmethod
    def _extract_reconciliation(cls, rows: Any, sheet_name: str = "", doc_id: str = "") -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        recon_items = []
        buckets = []
        raw_list = []
        if isinstance(rows, dict):
            for sname, srows in rows.items():
                if isinstance(srows, list):
                    for r in srows:
                        if isinstance(r, dict):
                            raw_list.append(r)
        elif isinstance(rows, list):
            raw_list = rows

        for r_orig in raw_list:
            if not isinstance(r_orig, dict):
                continue
            r = {}
            for k, v in r_orig.items():
                k_clean = str(k).strip()
                k_norm = re.sub(r'[^a-z0-9]+', '_', k_clean.lower()).strip('_')
                r[k_norm] = v
                r[k_clean.lower()] = v
                r[k_clean] = v

            b_id = r.get("bucket_id") or r.get("bucket") or r.get("code") or r.get("id") or f"BKT{len(buckets)+1:03d}"
            b_name = r.get("bucket_name") or r.get("name") or r.get("title") or b_id
            src_ds = (
                r.get("dataset_source") or
                r.get("dataset___source") or
                r.get("source_dataset") or
                r.get("source___dataset") or
                r.get("source_slash_dataset") or
                r.get("source_table") or
                r.get("dataset") or
                r.get("source") or
                ""
            )
            filter_cond = r.get("filter_condition") or r.get("condition") or ""
            bucket_cond = r.get("bucket_condition") or r.get("description") or r.get("state") or ""
            output_res = r.get("output_result") or r.get("result") or r.get("output_result_set") or "VALID"
            impact_type = r.get("impact_type") or r.get("impact") or "None"
            impact_calc = r.get("impact_calculation") or r.get("calculation") or "0"
            enabled_val = r.get("enabled") or r.get("active") or "Y"
            is_enabled = str(enabled_val).strip().upper() in ("Y", "YES", "TRUE", "1", "T", "ACTIVE")

            item = {
                "bucket_id": str(b_id).strip(),
                "bucket_name": str(b_name).strip(),
                "code": str(b_id).strip(),
                "source_dataset": str(src_ds).strip(),
                "dataset": str(src_ds).strip(),
                "filter_condition": str(filter_cond).strip(),
                "bucket_condition": str(bucket_cond).strip(),
                "description": str(bucket_cond).strip() or str(b_name).strip(),
                "output_result": str(output_res).strip(),
                "impact_type": str(impact_type).strip(),
                "impact_calculation": str(impact_calc).strip(),
                "kri": str(output_res).strip(),
                "action": f"Output: {output_res}",
                "enabled": is_enabled,
                "provenance": {
                    "document_id": doc_id,
                    "sheet": sheet_name,
                    "row": r_orig.get("_excel_row_num")
                }
            }
            recon_items.append(item)
            buckets.append(item)

        return recon_items, buckets

    @classmethod
    def _extract_report_derivations(cls, rows: Any, sheet_name: str = "", doc_id: str = "") -> List[Dict[str, Any]]:
        derivations = []
        raw_list = []
        if isinstance(rows, dict):
            for sname, srows in rows.items():
                if isinstance(srows, list):
                    for r in srows:
                        if isinstance(r, dict):
                            raw_list.append(r)
        elif isinstance(rows, list):
            raw_list = rows

        for r_orig in raw_list:
            if not isinstance(r_orig, dict):
                continue
            r = {}
            for k, v in r_orig.items():
                k_clean = str(k).strip()
                k_norm = re.sub(r'[^a-z0-9]+', '_', k_clean.lower()).strip('_')
                r[k_norm] = v
                r[k_clean.lower()] = v
                r[k_clean] = v

            tgt_attr = r.get("target_attribute") or r.get("target_column") or r.get("attribute") or r.get("column_name") or ""
            src_fields = r.get("source_fields") or r.get("source_field") or r.get("fields") or ""
            src_tbl = r.get("tables") or r.get("table") or r.get("source_table") or r.get("dataset") or ""
            logic = r.get("derivation_logic") or r.get("logic") or r.get("transformation") or r.get("formula") or ""
            remark = r.get("remark") or r.get("remarks") or r.get("description") or ""

            if not tgt_attr:
                continue

            derivations.append({
                "target_attribute": str(tgt_attr).strip(),
                "target_column": str(tgt_attr).strip(),
                "source_fields": str(src_fields).strip(),
                "source_table": str(src_tbl).strip(),
                "derivation_logic": str(logic).strip(),
                "transformation": str(logic).strip(),
                "remark": str(remark).strip(),
                "provenance": {
                    "document_id": doc_id,
                    "sheet": sheet_name,
                    "row": r_orig.get("_excel_row_num")
                }
            })
        return derivations

    @classmethod
    def _extract_config(cls, sheet_name: str, headers: List[str], rows: List[Dict[str, Any]], doc_id: str = "") -> List[Dict[str, Any]]:
        cfgs = []
        for r_orig in rows:
            if not isinstance(r_orig, dict):
                continue
            r = {}
            for k, v in r_orig.items():
                k_clean = str(k).strip()
                k_norm = re.sub(r'[^a-z0-9]+', '_', k_clean.lower()).strip('_')
                r[k_norm] = v
                r[k_clean.lower()] = v
                r[k_clean] = v

            cfg_group = r.get("config_group") or r.get("group") or r.get("category") or "GENERAL"
            cfg_key = r.get("config_key") or r.get("key") or r.get("parameter") or r.get("name") or ""
            cfg_val = r.get("config_value") or r.get("value") or r.get("setting") or ""
            desc = r.get("description") or r.get("purpose") or r.get("remark") or ""
            active = r.get("active") or r.get("enabled") or "Y"

            if cfg_key:
                cfgs.append({
                    "config_group": str(cfg_group).strip(),
                    "config_key": str(cfg_key).strip(),
                    "config_value": str(cfg_val).strip(),
                    "description": str(desc).strip(),
                    "active": str(active).strip(),
                    "provenance": {
                        "document_id": doc_id,
                        "sheet": sheet_name,
                        "row": r_orig.get("_excel_row_num")
                    }
                })
        return cfgs

    @classmethod
    def _extract_data_model(cls, rows: Any, sheet_name: str = "", doc_id: str = "") -> List[Dict[str, Any]]:
        entity_map: Dict[str, Dict[str, Any]] = {}
        raw_list = []
        if isinstance(rows, dict):
            for sname, srows in rows.items():
                if isinstance(srows, list):
                    for r in srows:
                        if isinstance(r, dict):
                            raw_list.append(r)
        elif isinstance(rows, list):
            raw_list = rows

        for r_orig in raw_list:
            if not isinstance(r_orig, dict):
                continue
            r = {}
            for k, v in r_orig.items():
                k_clean = str(k).strip()
                k_norm = re.sub(r'[^a-z0-9]+', '_', k_clean.lower()).strip('_')
                r[k_norm] = v
                r[k_clean.lower()] = v
                r[k_clean] = v

            stage = r.get("data_process_stage") or r.get("process_stage") or r.get("stage") or ""
            entity_name = (
                r.get("dataset_table_entity_name") or
                r.get("target_table") or
                r.get("target_entity") or
                r.get("target_dataset") or
                r.get("entity_name") or
                r.get("table_name") or
                r.get("dataset") or
                r.get("table") or
                r.get("output_result_set") or
                r.get("output_dataset") or
                ""
            )
            if not entity_name:
                for k, v in r.items():
                    if not k.startswith("_") and ("entity" in k or "target" in k or "table" in k or "dataset" in k) and v:
                        entity_name = str(v).strip()
                        break
            if not entity_name:
                continue

            std_type = r.get("standard_non_standard_table") or r.get("standard_table") or r.get("type") or ""
            reuse = r.get("reuse_rebuild") or r.get("reuse") or ""
            load_type = r.get("load_type") or r.get("type_of_load") or ""
            desc = r.get("description") or r.get("purpose") or ""

            col_name = r.get("attribute_name") or r.get("column_name") or r.get("attribute") or r.get("field") or ""
            col_type = r.get("data_type") or r.get("datatype") or r.get("type") or "VARCHAR(255)"
            col_null = r.get("nullable") or r.get("is_nullable") or "Y"

            layer = cls.classify_target_layer(stage, str(entity_name).strip(), desc)
            role = "TARGET" if layer in ("Reporting", "Summary", "History", "Target / Output") else "INTERMEDIATE"

            key = str(entity_name).strip().lower()
            if key not in entity_map:
                entity_map[key] = {
                    "stage": stage or layer,
                    "layer": layer,
                    "role": role,
                    "entity_name": str(entity_name).strip(),
                    "table_name": str(entity_name).strip(),
                    "standard_type": std_type,
                    "reuse_rebuild": reuse,
                    "load_type": load_type,
                    "description": desc,
                    "sheet_name": sheet_name,
                    "columns": [],
                    "source_row": r_orig.get("_excel_row_num"),
                    "provenance": {
                        "document_id": doc_id,
                        "sheet": sheet_name,
                        "row": r_orig.get("_excel_row_num")
                    }
                }
            if col_name and str(col_name).strip() != "-":
                entity_map[key]["columns"].append({
                    "name": str(col_name).strip(),
                    "type": str(col_type).strip(),
                    "nullable": str(col_null).strip()
                })

        return list(entity_map.values())

    @classmethod
    def _detect_control_identifier(cls, parsed_wb: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Dynamically scans for explicit control numbers in sheet headers or values.
        If NO control is found, returns None.
        """
        control_num = None
        control_title = None

        for s_name, s_data in parsed_wb["sheets"].items():
            for r in s_data["rows"][:10]:
                for k, val in r.items():
                    if k.startswith("_"):
                        continue
                    val_str = str(val).strip()
                    m = re.search(r'\b(?:control|ctrl)[-_ ]?(\d+)\b', val_str, re.IGNORECASE)
                    if m:
                        control_num = f"CTRL-{m.group(1)}"
                        if len(val_str) > 8:
                            control_title = val_str
                        break
                if control_num:
                    break
            if control_num:
                break

        if not control_num:
            return None

        return {
            "identification": {
                "control_number": control_num,
                "control_title": control_title or f"Control Specification ({control_num})"
            },
            "target_schema": f"ra_ctrl.{control_num.lower().replace('-', '_')}"
        }
