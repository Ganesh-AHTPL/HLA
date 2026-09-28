"""
Generic Document Context Extractor for HLA Studio.
Extracts arbitrary structured sections, components, requirements, pipeline stages,
tables, columns, rules, parameters, and mappings from any uploaded document.
Zero hardcoding of sheet names, rule IDs, control IDs, or schemas.
The uploaded document is the single source of truth.
"""

from typing import Dict, Any, List, Optional


class HLAContextExtractor:
    """
    Parses arbitrary document analysis data dynamically into indexable semantic buckets.
    """

    @classmethod
    def index_document_analysis(cls, analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Dynamically indexes whatever sections exist in analysis_data.
        Handles generic architecture, requirements, pipelines, controls, and custom structures.
        """
        if not analysis_data or not isinstance(analysis_data, dict):
            return {}

        indexed = {
            "document_profile": {},
            "components": [],
            "requirements": [],
            "pipeline_stages": [],
            "source_tables": [],
            "target_attributes": [],
            "rules": [],
            "reconciliation": [],
            "parameters": {},
            "raw_sections": {}
        }

        # 1. Document / Control Identification (generic)
        ctrl_ov = analysis_data.get("control_overview") or analysis_data.get("overview") or analysis_data.get("metadata") or {}
        if isinstance(ctrl_ov, dict):
            ident = ctrl_ov.get("identification") or ctrl_ov
            if isinstance(ident, dict):
                indexed["document_profile"] = {
                    "identifier": ident.get("control_number") or ident.get("control_id") or ident.get("id") or ident.get("document_id") or "",
                    "title": ident.get("control_title") or ident.get("control_name") or ident.get("name") or ident.get("title") or "",
                    "frequency": ident.get("frequency") or ctrl_ov.get("frequency") or "Not specified",
                    "owner": ident.get("owner") or ident.get("author") or "Unassigned",
                    "description": ident.get("description") or ctrl_ov.get("purpose") or "",
                    "process": ident.get("process") or "",
                    "sub_process": ident.get("sub_process") or "",
                }

        # 2. Architecture Components (generic)
        components = analysis_data.get("components") or []
        if isinstance(components, list):
            for c in components:
                if isinstance(c, dict):
                    indexed["components"].append({
                        "name": c.get("component") or c.get("name") or c.get("system") or "",
                        "responsibility": c.get("responsibility") or c.get("purpose") or c.get("description") or "",
                        "input": c.get("input") or c.get("consumes") or "",
                        "output": c.get("output") or c.get("produces") or "",
                        "technology": c.get("technology") or c.get("platform") or "",
                        "interaction": c.get("interaction") or c.get("interface") or ""
                    })
                elif isinstance(c, str):
                    indexed["components"].append({"name": c, "responsibility": "", "input": "", "output": "", "technology": "", "interaction": ""})

        # 3. Requirements (generic)
        requirements = analysis_data.get("requirements") or []
        if isinstance(requirements, list):
            for r in requirements:
                if isinstance(r, dict):
                    indexed["requirements"].append({
                        "id": r.get("requirement") or r.get("req_id") or r.get("id") or "",
                        "description": r.get("description") or "",
                        "priority": r.get("priority") or "Medium",
                        "acceptance_criteria": r.get("acceptance_criteria") or r.get("criteria") or ""
                    })

        # 4. Pipeline Stages & Dependencies (generic)
        stages = analysis_data.get("pipeline_stages") or []
        if isinstance(stages, list):
            for st in stages:
                if isinstance(st, dict):
                    indexed["pipeline_stages"].append({
                        "stage": st.get("stage") or st.get("name") or "",
                        "process": st.get("process") or st.get("step") or "",
                        "dependencies": st.get("dependencies") or st.get("depends_on") or "",
                        "input": st.get("input") or "",
                        "output": st.get("output") or ""
                    })

        # 5. Source Datasets / Tables (generic)
        sources = analysis_data.get("sources") or analysis_data.get("source_tables") or analysis_data.get("input_datasets") or []
        if isinstance(sources, list):
            for s in sources:
                if isinstance(s, dict):
                    t_name = s.get("full_table_name") or s.get("source_table_name") or s.get("table_name") or s.get("name") or s.get("dataset_name") or ""
                    indexed["source_tables"].append({
                        "name": t_name,
                        "schema": s.get("schema_name") or s.get("schema") or "public",
                        "database": s.get("database_name") or s.get("database") or s.get("source_db") or "Default",
                        "load_type": s.get("type_of_load") or s.get("load_type") or "",
                        "frequency": s.get("frequency") or s.get("refresh_time") or "",
                        "schedule_time": s.get("schedule_time") or "",
                        "columns": s.get("columns") or s.get("fields") or []
                    })
                elif isinstance(s, str):
                    indexed["source_tables"].append({"name": s, "schema": "public", "database": "Default", "load_type": "", "frequency": "", "schedule_time": "", "columns": []})

        # 6. Rules & Business Logic (generic)
        raw_rules = analysis_data.get("rules") or analysis_data.get("business_rules") or analysis_data.get("transformations") or []
        if isinstance(raw_rules, dict):
            rule_list = []
            for k in ["filter_rules", "balance_rules", "business_rules", "reconciliation_flows", "transformations"]:
                rule_list.extend(raw_rules.get(k, []))
            raw_rules = rule_list

        if isinstance(raw_rules, list):
            for r in raw_rules:
                if isinstance(r, dict):
                    r_id = r.get("rule_id") or r.get("id") or r.get("code") or r.get("rule_number") or ""
                    r_name = r.get("category") or r.get("rule_name") or r.get("name") or r.get("title") or ""
                    r_desc = r.get("description") or r.get("rule_statement") or r.get("logic") or ""
                    indexed["rules"].append({
                        "id": str(r_id),
                        "name": str(r_name),
                        "description": str(r_desc),
                        "target": r.get("target") or r.get("data_stream") or r.get("source_table") or "",
                        "severity": r.get("severity") or "MANDATORY",
                        "expression": r.get("expression") or r.get("sql") or r.get("condition") or ""
                    })

        # 7. Target Attributes / Schema Definitions (generic)
        targets = analysis_data.get("mappings") or analysis_data.get("target_attributes") or analysis_data.get("attributes") or []
        if isinstance(targets, list):
            for t in targets:
                if isinstance(t, dict):
                    indexed["target_attributes"].append({
                        "name": t.get("target_column") or t.get("name") or "",
                        "target_column": t.get("target_column") or t.get("name") or "",
                        "source_field": t.get("source_field") or "-",
                        "source_table": t.get("source_table") or "-",
                        "mapping_type": t.get("mapping_type") or "Direct",
                        "type": t.get("type") or t.get("data_type") or "VARCHAR",
                        "derivation_logic": t.get("derivation_logic") or ""
                    })
                elif isinstance(t, str):
                    indexed["target_attributes"].append({"name": t, "target_column": t, "source_field": "-", "source_table": "-", "mapping_type": "Direct", "type": "VARCHAR", "derivation_logic": ""})


        # 8. Reconciliation & Buckets (generic)
        recon = analysis_data.get("reconciliation") or analysis_data.get("buckets") or []
        if isinstance(recon, list):
            for b in recon:
                if isinstance(b, dict):
                    indexed["reconciliation"].append(b)

        # 9. Capture any arbitrary other sections in the document
        for k, v in analysis_data.items():
            if k not in ("control_overview", "overview", "metadata", "components", "requirements", "pipeline_stages", "sources", "source_tables", "input_datasets", "rules", "business_rules", "mappings", "target_attributes", "attributes", "reconciliation", "buckets"):
                indexed["raw_sections"][k] = v

        return indexed
