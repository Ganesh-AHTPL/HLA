"""
Generic Document Retrieval Engine (RAG) for HLA Studio.
Extracts relevant slices from whatever document is loaded without assuming fixed control IDs,
fixed sheet names, fixed rule IDs, or fixed database schemas.
"""

import json
from typing import Dict, Any, Tuple, Optional, List
from models import Document, Project, ControlRunHistory, db
from backend.ai.nlu.context_resolver import ContextResolver
from backend.ai.nlu.intent_parser import (
    INTENT_LIST_COMPONENTS,
    INTENT_LIST_REQUIREMENTS,
    INTENT_COMPONENT_INPUT,
    INTENT_COMPONENT_OUTPUT,
    INTENT_EXPLAIN_ARCHITECTURE,
    INTENT_LIST_DEPENDENCIES,
    INTENT_LIST_SOURCE_TABLES,
    INTENT_ANALYZE_NULL_VALUES,
    INTENT_BUILD_TARGET,
    INTENT_RECONCILIATION_LOGIC,
    INTENT_CHECK_CONTROL,
    INTENT_EXPLAIN_FAILURE,
    INTENT_MAKE_GENERIC,
    INTENT_SUMMARIZE_PROJECT,
)


class HLARetrievalEngine:
    """
    Retrieves targeted facts from the loaded document metadata.
    """

    @classmethod
    def get_document_context(cls, document_id: int) -> Dict[str, Any]:
        """
        Retrieves fully sanitized and indexed context strictly for a specific document.
        """
        doc = db.session.get(Document, document_id)
        if not doc:
            return {}
        _, context_data = ContextResolver.resolve_control_context(document_id=document_id)
        return context_data

    @classmethod
    def retrieve_context(
        cls,
        intent: str,
        entities: Dict[str, Any],
        project_id: Optional[int] = None,
        document_id: Optional[int] = None
    ) -> Tuple[str, bool]:
        """
        Dynamically extracts document context matching the user's intent.
        """
        control_ref = entities.get("control_number")
        rule_filter = entities.get("rule_id")
        req_filter = entities.get("requirement_id")
        comp_filter = entities.get("component_name")
        col_filter = entities.get("column")
        tab_filter = entities.get("table_name")

        matched_doc, context_data = ContextResolver.resolve_control_context(
            control_ref=control_ref,
            project_id=project_id,
            document_id=document_id
        )

        blocks = []
        has_data = False

        # 1. Project-level summary
        if intent == INTENT_SUMMARIZE_PROJECT:
            if project_id:
                proj = db.session.get(Project, project_id)
                if proj:
                    has_data = True
                    docs = Document.query.filter_by(project_id=project_id).all()
                    b = [
                        f"PROJECT SUMMARY: {proj.name}",
                        f"DESCRIPTION: {proj.description or 'None'}",
                        f"DOCUMENTS ({len(docs)} total):"
                    ]
                    for d in docs:
                        title = d.original_name
                        if d.analysis_data:
                            ctrl_ov = d.analysis_data.get("control_overview") or {}
                            ident = ctrl_ov.get("identification", {}) if isinstance(ctrl_ov, dict) else {}
                            if ident.get("control_number"):
                                title = f"Control {ident.get('control_number')} - {ident.get('control_title') or title}"
                        b.append(f"  • Document #{d.id}: {title} (Status: {d.status})")
                    blocks.append("\n".join(b))
            return "\n\n".join(blocks), has_data

        # 2. Document-driven context retrieval
        if context_data:
            has_data = True
            doc_name = context_data.get("document_name", "Uploaded Document")
            profile = context_data.get("profile", {})
            components = context_data.get("components", [])
            requirements = context_data.get("requirements", [])
            sources = context_data.get("sources", [])
            rules = context_data.get("rules", [])
            targets = context_data.get("target_attributes", [])
            pipeline_stages = context_data.get("pipeline_stages", [])

            header_lines = [f"DOCUMENT SOURCE OF TRUTH: {doc_name} (ID: {context_data.get('document_id')})"]
            if profile.get("identifier"):
                header_lines.append(f"IDENTIFIER: {profile.get('identifier')}")
            if profile.get("title"):
                header_lines.append(f"TITLE: {profile.get('title')}")
            if profile.get("frequency") and profile.get("frequency") != "Not specified":
                header_lines.append(f"FREQUENCY: {profile.get('frequency')}")
            if profile.get("description"):
                header_lines.append(f"DESCRIPTION: {profile.get('description')}")
            blocks.append("\n".join(header_lines))

            # ── Slices by Intent ──

            # Intent: Components
            if intent == INTENT_LIST_COMPONENTS:
                c_lines = [f"ARCHITECTURE COMPONENTS ({len(components)} defined in document):"]
                if components:
                    for c in components:
                        c_lines.append(f"  • Component: {c.get('name')}")
                        if c.get("responsibility"):
                            c_lines.append(f"    - Responsibility: {c.get('responsibility')}")
                        if c.get("technology"):
                            c_lines.append(f"    - Technology: {c.get('technology')}")
                        if c.get("input"):
                            c_lines.append(f"    - Input: {c.get('input')}")
                        if c.get("output"):
                            c_lines.append(f"    - Output: {c.get('output')}")
                        if c.get("interaction"):
                            c_lines.append(f"    - Interaction: {c.get('interaction')}")
                else:
                    c_lines.append("  No specific architecture components defined in this document.")
                blocks.append("\n".join(c_lines))

            # Intent: Requirements
            elif intent == INTENT_LIST_REQUIREMENTS:
                r_lines = [f"DOCUMENT REQUIREMENTS ({len(requirements)} defined in document):"]
                matched_reqs = requirements
                if req_filter:
                    matched_reqs = [r for r in requirements if req_filter.lower() in str(r.get("id", "")).lower() or req_filter.lower() in str(r.get("description", "")).lower()]
                if matched_reqs:
                    for r in matched_reqs:
                        r_lines.append(f"  • [{r.get('id')}] (Priority: {r.get('priority')}): {r.get('description')}")
                        if r.get("acceptance_criteria"):
                            r_lines.append(f"    - Acceptance Criteria: {r.get('acceptance_criteria')}")
                else:
                    r_lines.append(f"  No requirements found matching '{req_filter}'.")
                blocks.append("\n".join(r_lines))

            # Intent: Component Input ("what goes into validation service?")
            elif intent == INTENT_COMPONENT_INPUT:
                in_lines = ["COMPONENT INPUTS & INGESTION SPECIFICATION:"]
                matched_c = components
                if comp_filter:
                    matched_c = [c for c in components if comp_filter.lower() in c.get("name", "").lower()]
                if matched_c:
                    for c in matched_c:
                        in_lines.append(f"  • Component '{c.get('name')}':")
                        in_lines.append(f"    - Input Received: {c.get('input') or 'Not specified'}")
                        in_lines.append(f"    - Responsibility: {c.get('responsibility') or 'N/A'}")
                        in_lines.append(f"    - Technology: {c.get('technology') or 'N/A'}")
                else:
                    in_lines.append(f"  No components found matching '{comp_filter}'.")
                blocks.append("\n".join(in_lines))

            # Intent: Component Output ("what comes out of processing layer?")
            elif intent == INTENT_COMPONENT_OUTPUT:
                out_lines = ["COMPONENT OUTPUTS & EMISSION SPECIFICATION:"]
                matched_c = components
                if comp_filter:
                    matched_c = [c for c in components if comp_filter.lower() in c.get("name", "").lower()]
                if matched_c:
                    for c in matched_c:
                        out_lines.append(f"  • Component '{c.get('name')}':")
                        out_lines.append(f"    - Output Produced: {c.get('output') or 'Not specified'}")
                        out_lines.append(f"    - Responsibility: {c.get('responsibility') or 'N/A'}")
                        in_lines_inter = c.get('interaction')
                        if in_lines_inter:
                            out_lines.append(f"    - Downstream Interaction: {in_lines_inter}")
                else:
                    out_lines.append(f"  No components found matching '{comp_filter}'.")
                blocks.append("\n".join(out_lines))

            # Intent: Explain Architecture & Overview
            elif intent == INTENT_EXPLAIN_ARCHITECTURE:
                arch_lines = ["ARCHITECTURE OVERVIEW & DATA FLOW:"]
                if components:
                    arch_lines.append(f"Components Flow ({len(components)} stages):")
                    for i, c in enumerate(components, 1):
                        arch_lines.append(
                            f"  {i}. {c.get('name')} ({c.get('technology') or 'Service'}): "
                            f"{c.get('input')} → [{c.get('responsibility')}] → {c.get('output')}"
                        )
                if requirements:
                    arch_lines.append(f"\nKey Requirements ({len(requirements)} items):")
                    for r in requirements:
                        arch_lines.append(f"  • {r.get('id')}: {r.get('description')} (Priority: {r.get('priority')})")
                if pipeline_stages:
                    arch_lines.append(f"\nPipeline Stages ({len(pipeline_stages)} stages):")
                    for st in pipeline_stages:
                        arch_lines.append(f"  • {st.get('stage')}: {st.get('process')} (Depends on: {st.get('dependencies') or 'None'})")
                blocks.append("\n".join(arch_lines))

            # Intent: Dependencies & Interactions
            elif intent == INTENT_LIST_DEPENDENCIES:
                dep_lines = ["COMPONENT INTERACTIONS & DEPENDENCIES:"]
                if components:
                    for c in components:
                        dep_lines.append(f"  • {c.get('name')}:")
                        dep_lines.append(f"    - Consumes: {c.get('input')}")
                        dep_lines.append(f"    - Produces: {c.get('output')}")
                        dep_lines.append(f"    - Interface/Interaction: {c.get('interaction')}")
                elif pipeline_stages:
                    for st in pipeline_stages:
                        dep_lines.append(f"  • {st.get('stage')}: Depends on [{st.get('dependencies') or 'Start'}] | Output: {st.get('output')}")
                else:
                    dep_lines.append("  No explicit dependencies or component interactions found.")
                blocks.append("\n".join(dep_lines))

            # Intent: Source Tables
            elif intent == INTENT_LIST_SOURCE_TABLES:
                s_lines = [f"SOURCE DATASETS / TABLES ({len(sources)} defined in document):"]
                if sources:
                    for s in sources:
                        s_name = s.get("name", "Unknown")
                        s_schema = s.get("schema", "public")
                        s_load = s.get("load_type", "")
                        s_freq = s.get("frequency", "")
                        s_lines.append(f"  • {s_schema}.{s_name} [{s_load or 'Standard'}] (Frequency: {s_freq or 'N/A'})")
                else:
                    s_lines.append("  No explicit source tables listed in document analysis.")
                blocks.append("\n".join(s_lines))

            # Intent: Rules & Reconciliation
            elif intent == INTENT_RECONCILIATION_LOGIC:
                r_lines = [f"BUSINESS & RECONCILIATION RULES ({len(rules)} defined in document):"]
                matched_rules = [
                    r for r in rules
                    if not rule_filter or rule_filter.upper() in str(r.get("id", "")).upper() or rule_filter.upper() in str(r.get("name", "")).upper()
                ]
                if matched_rules:
                    for r in matched_rules:
                        r_id = r.get("id", "")
                        r_name = r.get("name", "")
                        r_desc = r.get("description", "")
                        r_lines.append(f"  • [{r_id or 'Rule'}] {r_name}: {r_desc}")
                else:
                    r_lines.append(f"  No specific rules matched filter '{rule_filter}'.")
                blocks.append("\n".join(r_lines))

            # Intent: Target Schema / Database Structure
            elif intent in (INTENT_BUILD_TARGET, INTENT_MAKE_GENERIC):
                t_lines = [
                    "RECOMMENDED DATABASE SCHEMA / STRUCTURE (DERIVED FROM DOCUMENT):",
                ]
                if components:
                    t_lines.append("Entity tables suggested from Architecture Components:")
                    for c in components:
                        c_safe = c.get("name", "").lower().replace(" ", "_")
                        t_lines.append(f"  • Table: {c_safe}_events / {c_safe}_records")
                        t_lines.append(f"    - Input schema: {c.get('input')}")
                        t_lines.append(f"    - Output schema: {c.get('output')}")
                        t_lines.append(f"    - Technology context: {c.get('technology')}")
                elif targets:
                    t_lines.append(f"Target Attributes ({len(targets)} defined):")
                    for t in targets[:15]:
                        t_lines.append(f"  • {t.get('target_column')} ({t.get('mapping_type')}) - Logic: {t.get('derivation_logic')}")
                else:
                    t_lines.append("  Generic table structure with enterprise audit columns: id, created_at, updated_at, status, payload_json.")
                blocks.append("\n".join(t_lines))

            # Default Overview
            else:
                summary_lines = ["EXTRACTED DOCUMENT METADATA:"]
                if components:
                    summary_lines.append(f"  • Architecture Components: {len(components)} ({', '.join([c.get('name', '') for c in components[:4]])})")
                if requirements:
                    summary_lines.append(f"  • Requirements: {len(requirements)} ({', '.join([r.get('id', '') for r in requirements[:4]])})")
                if sources:
                    summary_lines.append(f"  • Source Datasets: {len(sources)}")
                if rules:
                    summary_lines.append(f"  • Rules: {len(rules)}")
                if targets:
                    summary_lines.append(f"  • Target Attributes: {len(targets)}")
                blocks.append("\n".join(summary_lines))

        return "\n\n".join(blocks), has_data
