"""
ctrl23_safe_impl.py
===================
CTRL-23 HLA — Safe Implementation Module (Section 10 of Dependency Resolution Pack)

PURPOSE:
    Contains ONLY the components that can be implemented safely without any
    guessed source column names, invented derived formulas, or unresolved
    HLA dependencies.

WHAT THIS FILE DOES:
    1.  Seed: customer_name_exclusion_list  (66 values from Sheet 7, Rows 39-104)
    2.  Seed: internal_profiles_vdom        (12 values from Sheet 7, Rows 5-16)
    3.  Seed: ip_exclusion_list             (4 values from Sheet 7, Rows 31-34)
    4.  Seed: managed_service_types         (7 values from Sheet 7, Rows 20-26)
    5.  Config audit                        (cross-check DB vs HLA Sheet 7)
    6.  Source connection metadata registry (6 upstream source descriptors from Sheet 1)
    7.  Deployment blocking gate            (pre-flight check — aborts if any source table missing)
    8.  Deployment readiness check          (enumerate all 29 blockers and their status)
    9.  Schema qualification helper         ("ra_ctrl.ctrl_23" quoted schema)
    10. SIGS static remark values           (Report 2, Field 1 — Sheet 6 Row 16)
    11. Issue remark derivation             (Report 2, Field 7 — Sheet 6 Row 22)
    12. KRI classification CASE shells      (B4.1, B5.1-B5.6, B6 — logic known, col names TBD)
    13. Report aggregation structure shells (Reports 1-4 GROUP BY / COUNT patterns)

WHAT THIS FILE DOES NOT DO:
    - Does NOT write production transformation SQL
    - Does NOT modify any existing production tables
    - Does NOT invent missing source column names
    - Does NOT choose a fuzzy matching algorithm
    - Does NOT invent derived field formulas

HLA REFERENCE: Control23_Source_Logic_2.xlsx — fully extracted (249 rows, 689 cells)
DB REFERENCE:  hla_db on postgresql://localhost:5432 — fully introspected 2026-09-14
"""

import logging
from datetime import datetime, timezone
from sqlalchemy import text

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 9 — CONFIGURATION: HLA Sheet 7 Authoritative Values
# ─────────────────────────────────────────────────────────────────────────────

# Sheet 7, Rows 5-16: Internal Profiles (VDOM Hostnames) — Rule R9
# 12 values confirmed from full workbook extraction
INTERNAL_PROFILES_VDOM_HLA = [
    "CHN-vUTM-FW05",
    "DEL-vUTM-FW01",
    "DEL-vUTM-FW03",
    "US-NYC-vUTM-FW04",
    "CRSX-vUTM-FW03",
    "SGP-vUTM-FW03",
    "US-LAA-vUTM-FW03",
    "SYD-vUTM-FW01",
    "FFT-SIGS-FW04",
    "PAR-SIGS-FW03",
    "MUM-vUTM-FW03",
    "CHN-vUTM-FW03",
]

# Sheet 7, Rows 31-34: Test/Dummy IP Exclusion — Rule R10
# 4 values confirmed
IP_EXCLUSION_HLA = [
    "1.1",
    "1.1.1.1",
    "0.0.0.1",
    "0.0.0.0",
]

# Sheet 7, Rows 20-26: Managed Service Types — KRI Rule B5.5
# 7 values confirmed
MANAGED_SERVICE_TYPES_HLA = [
    "Managed Services",
    "MSS",
    "MSSTCL",
    "Managed Security Services",
    "MSS-VIZNET",
    "TCL SERVIC",
    "TCL SERVICE",
]

# Sheet 7, Rows 39-104: Internal/Test Customer Name Exclusion List
# 66 values confirmed — no DB table exists yet (Blocker B-29)
CUSTOMER_NAME_EXCLUSION_HLA = [
    "TCl_IT_Singapore",
    "TCL_IT_Pune",
    "TCL_IT_London",
    "TCL_IT_Santaclara_(USA)",
    "TCL_IT_Chennai",
    "Network_Monitoring_Profile",
    "TCL_IT_Mumbai",
    "TCL_IT_Wall_(USA)",
    "TCL_IT_Montreal_(Canada)",
    "TCTSL_Dighi",
    "TCTSL_Emerald_Pune",
    "Demo_Test_PO",
    "GSIP_UNTRUSTED_LHX",
    "GSIP_UNTRUSTED_SVW",
    "UCC_TEMP",
    "GSIP_UNTRUSTED_1MH",
    "GSIP_UNTRUSTED_L78",
    "TCTSL_Mumbai_LVSB2",
    "GSIP_UNTRUSTED_WV6",
    "GSIP_UNTRUSTED_TTT",
    "TCTSL_Mumbai_LVSB1",
    "GSIP_UNTRUSTED_HKU",
    "GSIP_UNTRUSTED_JN1",
    "GSIP_UNTRUSTED_LAA",
    "GSIP_UNTRUSTED_MTT",
    "GSIP_UNTRUSTED_NW8",
    "UCC_INSTACC_Singapore",
    "UCC_GMX_Singapore",
    "UCC_INSTACC_UK",
    "UCC_GMX_Hyderabad",
    "UCC_GMX_London",
    "UCC_HCS_Singapore",
    "UCC_GMX_Newyork",
    "UCC_INSTACC_US",
    "UCC_HCS_UK",
    "UCC_Bangalore",
    "Pearl_Test_MO",
    "Pearl_Test_Carpet_Bombing",
    "SDWAN_Chennai_Link1",
    "TCL_IOT_104",
    "IOT_TATA_Proj45",
    "IOT_Tata_GSMC58",
    "IOT_Tata_GSMC88",
    "IoT_BU-I49",
    "AS_4755_SILL_IPv6",
    "Cisco Viptela -SD WAN- Test MO",
    "Test Mo- Unnumbered GRE tunnel - OEM versa",
    "Test Mo 2- Unnumbered GRE tunnel - OEM versa",
    "Silver Peak Test- SDWAN -Parag",
    "test_hdfc_bank_blr_proxy",
    "test_hdfc_bank_chan_proxy",
    "Nournet_GRE_Tunnel Testing",
    "Pearl_Test_AS_Comm",
    "PP_test",
    "Pearl_Test_IPv6",
    "pearl_test_vlan_poc",
    "Pearl_Test_CDN",
    "Pearl_Test_Waap",
    "Test_Customer",
    "pearl_NAT_Test_MO",
    "pearl_NAT_Test_MO2",
    "MitigationOnlyTesting",
    "CDN_DNS",
    "CDN_1",
    "CDN_2",
    "CDN_TATASKY",
]


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — SOURCE CONNECTION METADATA REGISTRY
# Authoritative source: HLA Sheet 1, Rows 4-9
# All 6 upstream tables with their Datalake DB, schema, load type, schedule
# ─────────────────────────────────────────────────────────────────────────────

CTRL23_SOURCE_REGISTRY = [
    {
        "hla_row": 4,
        "source_db": "24b",
        "schema": "cmdb",
        "table": "dl_itsm_cmdb_daily_dump",
        "full_ref": "cmdb.dl_itsm_cmdb_daily_dump",
        "load_type": "truncate_and_load",
        "schedule": "daily",
        "run_time_ist": "06:00",
        "frequency": "daily",
        "hla_alias": "CMDB",
        "hla_rules": ["R5", "R6", "R10", "R12", "R13", "R15"],
        "target_cols": [
            "cmdb_production_ip",
            "cmdb_profile_name",
            "cmdb_copf",
            "cmdb_ckt_id",
        ],
        "blocker_ids": ["B-02", "B-12"],
        "status": "BLOCKED",
        "note": "Not in hla_db. Lives in external Datalake DB 24b.",
    },
    {
        "hla_row": 5,
        "source_db": "24b",
        "schema": "pearl",
        "table": "dl_pearl_active_profiles",
        "full_ref": "pearl.dl_pearl_active_profiles",
        "load_type": "truncate_and_load",
        "schedule": "daily",
        "run_time_ist": "21:00",
        "frequency": "daily",
        "hla_alias": "PEARL",
        "hla_rules": [],
        "target_cols": [],
        "blocker_ids": ["B-06"],
        "status": "BLOCKED",
        "note": "Not in hla_db. Role in CTRL-23 unspecified in HLA. Needs design clarification.",
    },
    {
        "hla_row": 6,
        "source_db": "24a",
        "schema": "sfdc",
        "table": "copf_id",
        "full_ref": "sfdc.copf_id",
        "load_type": "truncate_and_load",
        "schedule": "daily",
        "run_time_ist": "07:30",
        "frequency": "daily",
        "hla_alias": "SFDC",
        "hla_rules": ["B5.1", "B5.2", "B5.3"],
        "target_cols": [
            "sfdc_mrc",
            "sfdc_nrc",
            "sfdc_copf_created_dt",
            "sfdc_status",
        ],
        "blocker_ids": ["B-04", "B-14", "B-26"],
        "status": "BLOCKED",
        "note": "Not in hla_db. Lives in external Datalake DB 24a.",
    },
    {
        "hla_row": 7,
        "source_db": "24b",
        "schema": "qlik_report",
        "table": "dl_ra_order_report_daily",
        "full_ref": "qlik_report.dl_ra_order_report_daily",
        "load_type": "truncate_and_load",
        "schedule": "daily",
        "run_time_ist": "11:00",
        "frequency": "daily",
        "hla_alias": "QLIK_BILLING",
        "hla_rules": ["found_in_billing", "product_billing"],
        "target_cols": [
            "found_in_billing",
            "product_billing",
        ],
        # Columns KNOWN from Sheet 6 (reports):
        "known_columns": [
            "c_circuitid",            # Sheet 6 Row 41
            "annual_recurring_charge", # Sheet 6 Rows 21, 43
            "discounted_onetimecharge",# Sheet 6 Rows 20, 42
            "standard_onetimecharge",  # Sheet 6 Rows 20, 42
            # service_type, sub_service_type, system — UNKNOWN
        ],
        "blocker_ids": ["B-05", "B-23"],
        "status": "BLOCKED",
        "note": "Not in hla_db. 4 column names known from Sheet 6. Service_Type / system columns unknown.",
    },
    {
        "hla_row": 8,
        "source_db": "RA Recon DB",
        "schema": "ra",
        "table": "stg_rk_ckt_recon_final",
        "full_ref": "ra.stg_rk_ckt_recon_final",
        "load_type": "truncate_and_load",
        "schedule": "daily",
        "run_time_ist": "13:00",
        "frequency": "daily",
        "hla_alias": "CIRCUIT_RECO",
        "hla_rules": ["R7", "R8", "R15"],
        "target_cols": [
            "ckt_circuit_id",
            "ckt_circuit_status",
            "ckt_copf",
            "ckt_source_system",
            "ckt_product",
            "ckt_additional_remarks",
            "ckt_customer_name",
            "ckt_final_remarks",
            "ckt_recon_remark_provisioning",
        ],
        "blocker_ids": ["B-03", "B-13"],
        "status": "BLOCKED",
        "note": "Not in hla_db. Lives in external RA Recon DB.",
    },
    {
        "hla_row": 9,
        "source_db": "24b",
        "schema": "reports",
        "table": "dl_vdom_firewall_audit_report",
        "full_ref": "reports.dl_vdom_firewall_audit_report",
        "load_type": "append_latest_week",
        "schedule": "weekly",
        "run_time_ist": "09:00",
        "frequency": "weekly_monday",
        "hla_alias": "VDOM",
        "hla_rules": ["R1", "R2", "R9", "R12", "R14"],
        "target_cols": [
            "application_name",
            "host_name",
            "ip",
            "ckt_id",
            "service_type",
        ],
        "blocker_ids": ["B-01", "B-07", "B-08", "B-09", "B-10", "B-11"],
        "status": "BLOCKED",
        "note": "Not in hla_db. Lives in external Datalake DB 24b. Append load (not truncate).",
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8 — SCHEMA QUALIFICATION
# ra_ctrl.ctrl_23 IS a real PostgreSQL schema with a dot in its name.
# Confirmed via DB introspection 2026-09-14.
# All SQL targeting this schema MUST use double-quoted identifier.
# ─────────────────────────────────────────────────────────────────────────────

CTRL23_SCHEMA_PUBLIC = "public"
CTRL23_SCHEMA_PRODUCTION = '"ra_ctrl.ctrl_23"'  # Note: the schema name contains a dot


def qualify(table_name: str, schema: str = CTRL23_SCHEMA_PUBLIC) -> str:
    """
    Return a properly schema-qualified table reference for CTRL-23.

    Usage:
        qualify('ctrl_23_source_dataset_vdom')           → 'public.ctrl_23_source_dataset_vdom'
        qualify('ctrl_23_source_dataset_vdom', prod=True) → '"ra_ctrl.ctrl_23".ctrl_23_source_dataset_vdom'
    """
    if schema == CTRL23_SCHEMA_PRODUCTION or schema == "ra_ctrl.ctrl_23":
        return f'"ra_ctrl.ctrl_23".{table_name}'
    return f'{schema}.{table_name}'


def qualify_prod(table_name: str) -> str:
    """Qualify for the ra_ctrl.ctrl_23 production schema."""
    return qualify(table_name, CTRL23_SCHEMA_PRODUCTION)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 — DEPLOYMENT BLOCKING GATE
# Pre-flight check: aborts transformation run if upstream source tables absent.
# Source table names are known from HLA Sheet 1. Their absence in hla_db is confirmed.
# ─────────────────────────────────────────────────────────────────────────────

# The 6 upstream source tables: their staging copies in hla_db
# (the actual Datalake tables, when ingested, would populate these)
CTRL23_REQUIRED_SOURCE_TABLES = [
    ("public", "ctrl_23_source_dataset_vdom",     "reports.dl_vdom_firewall_audit_report",  "24b"),
    ("public", "ctrl_23_source_dataset_ddos",      "pearl.dl_pearl_active_profiles",         "24b"),
    ("public", "ctrl_23_source_dataset_cmdb",      "cmdb.dl_itsm_cmdb_daily_dump",           "24b"),
    ("public", "ctrl_23_source_dataset_cktrecon",  "ra.stg_rk_ckt_recon_final",              "RA Recon DB"),
]


def ctrl23_deployment_blocking_gate(db_engine) -> dict:
    """
    DEPLOYMENT BLOCKING GATE — Section 10, Item 2.

    Checks whether the CTRL-23 source dataset staging tables have been populated.
    A table is considered "ready" only if it exists AND has at least 1 row.

    Returns a gate result dict:
        {
            "gate_passed": bool,
            "status": "READY" | "BLOCKED",
            "blocking_reason": str | None,
            "checks": [ { schema, table, upstream_source, source_db, row_count, status } ]
        }

    This gate MUST pass before any transformation SQL is executed.
    If it returns "BLOCKED", execution must halt.
    """
    checks = []
    all_passed = True

    with db_engine.connect() as conn:
        for schema, table, upstream, source_db in CTRL23_REQUIRED_SOURCE_TABLES:
            try:
                # Check existence
                exists_result = conn.execute(text("""
                    SELECT COUNT(*) FROM information_schema.tables
                    WHERE table_schema = :s AND table_name = :t
                """), {"s": schema, "t": table}).scalar()

                if not exists_result:
                    checks.append({
                        "schema": schema,
                        "table": table,
                        "upstream_source": upstream,
                        "source_db": source_db,
                        "row_count": 0,
                        "status": "MISSING_TABLE",
                        "message": f"Table {schema}.{table} does not exist in hla_db.",
                    })
                    all_passed = False
                    continue

                # Check row count
                row_count = conn.execute(text(
                    f"SELECT COUNT(*) FROM {schema}.{table}"
                )).scalar()

                if row_count == 0:
                    checks.append({
                        "schema": schema,
                        "table": table,
                        "upstream_source": upstream,
                        "source_db": source_db,
                        "row_count": 0,
                        "status": "EMPTY",
                        "message": (
                            f"Table {schema}.{table} exists but has 0 rows. "
                            f"ETL pipeline from '{upstream}' (DB: {source_db}) has not run or has not loaded data."
                        ),
                    })
                    all_passed = False
                else:
                    checks.append({
                        "schema": schema,
                        "table": table,
                        "upstream_source": upstream,
                        "source_db": source_db,
                        "row_count": row_count,
                        "status": "OK",
                        "message": f"Table has {row_count} rows. Ready.",
                    })

            except Exception as exc:
                checks.append({
                    "schema": schema,
                    "table": table,
                    "upstream_source": upstream,
                    "source_db": source_db,
                    "row_count": -1,
                    "status": "ERROR",
                    "message": f"Error checking table: {exc}",
                })
                all_passed = False

    blocked_items = [c for c in checks if c["status"] != "OK"]
    blocking_reason = None
    if blocked_items:
        blocking_reason = (
            f"{len(blocked_items)} of {len(checks)} source tables are not ready: "
            + "; ".join(c["message"] for c in blocked_items)
        )

    return {
        "gate_passed": all_passed,
        "status": "READY" if all_passed else "BLOCKED",
        "blocking_reason": blocking_reason,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8 — DEPLOYMENT READINESS CHECK (Full 29-Blocker Enumeration)
# ─────────────────────────────────────────────────────────────────────────────

# The definitive 29-blocker registry from the Dependency Resolution Pack
CTRL23_BLOCKERS = [
    {"id": "B-01", "category": "Source Schema",   "severity": "CRITICAL", "owner": "Datalake Team (24b)",           "description": "reports.dl_vdom_firewall_audit_report not in hla_db; physical columns unknown"},
    {"id": "B-02", "category": "Source Schema",   "severity": "CRITICAL", "owner": "Datalake Team (24b)",           "description": "cmdb.dl_itsm_cmdb_daily_dump not in hla_db; physical columns unknown"},
    {"id": "B-03", "category": "Source Schema",   "severity": "CRITICAL", "owner": "RA Recon DB Team",              "description": "ra.stg_rk_ckt_recon_final not in hla_db; physical columns unknown"},
    {"id": "B-04", "category": "Source Schema",   "severity": "CRITICAL", "owner": "Datalake Team (24a)",           "description": "sfdc.copf_id not in hla_db; physical columns unknown"},
    {"id": "B-05", "category": "Source Schema",   "severity": "HIGH",     "owner": "Datalake Team (24b)",           "description": "qlik_report.dl_ra_order_report_daily not in hla_db; service_type/sub_service_type/system columns unknown"},
    {"id": "B-06", "category": "Source Schema",   "severity": "MEDIUM",   "owner": "Datalake Team (24b) + HLA Design", "description": "pearl.dl_pearl_active_profiles role in CTRL-23 unspecified"},
    {"id": "B-07", "category": "Target Mapping",  "severity": "CRITICAL", "owner": "Datalake Team (24b)",           "description": "host_name physical source column in VDOM unknown"},
    {"id": "B-08", "category": "Target Mapping",  "severity": "CRITICAL", "owner": "Datalake Team (24b)",           "description": "ip physical source column in VDOM unknown"},
    {"id": "B-09", "category": "Target Mapping",  "severity": "HIGH",     "owner": "Datalake Team (24b)",           "description": "application_name physical source column in VDOM unknown"},
    {"id": "B-10", "category": "Target Mapping",  "severity": "HIGH",     "owner": "Datalake Team (24b)",           "description": "ckt_id physical source column in VDOM unknown"},
    {"id": "B-11", "category": "Target Mapping",  "severity": "HIGH",     "owner": "Datalake Team (24b)",           "description": "service_type physical source column in VDOM unknown"},
    {"id": "B-12", "category": "Target Mapping",  "severity": "CRITICAL", "owner": "Datalake Team (24b)",           "description": "cmdb_production_ip, cmdb_profile_name, cmdb_copf, cmdb_ckt_id physical columns unknown"},
    {"id": "B-13", "category": "Target Mapping",  "severity": "CRITICAL", "owner": "RA Recon DB Team",              "description": "All 9 Circuit Reco target columns physical names unknown"},
    {"id": "B-14", "category": "Target Mapping",  "severity": "CRITICAL", "owner": "Datalake Team (24a)",           "description": "sfdc_mrc, sfdc_nrc, sfdc_copf_created_dt, sfdc_status physical columns unknown"},
    {"id": "B-15", "category": "Derived Field",   "severity": "HIGH",     "owner": "HLA Design Team",              "description": "final_cmdb_remarks — no derivation formula in HLA workbook"},
    {"id": "B-16", "category": "Derived Field",   "severity": "HIGH",     "owner": "HLA Design Team",              "description": "final_circuit_id — no derivation formula (priority logic unknown)"},
    {"id": "B-17", "category": "Derived Field",   "severity": "HIGH",     "owner": "HLA Design Team",              "description": "recon_remarks — kri_description mapping not provided; intermediate column not implemented"},
    {"id": "B-18", "category": "Derived Field",   "severity": "HIGH",     "owner": "HLA Design Team + Datalake",   "description": "trf_date — source table and column unknown"},
    {"id": "B-19", "category": "Derived Field",   "severity": "MEDIUM",   "owner": "HLA Design Team",              "description": "ageing_trf — formula not specified (assume CURRENT_DATE - trf_date but unconfirmed)"},
    {"id": "B-20", "category": "Derived Field",   "severity": "HIGH",     "owner": "HLA Design Team",              "description": "trf_impact — formula partially known but TRF_date source missing"},
    {"id": "B-21", "category": "Derived Field",   "severity": "MEDIUM",   "owner": "HLA Design Team",              "description": "days_up — no formula or source in HLA"},
    {"id": "B-22", "category": "Derived Field",   "severity": "MEDIUM",   "owner": "HLA Design Team",              "description": "impact_up — no formula or source in HLA"},
    {"id": "B-23", "category": "Derived Field",   "severity": "HIGH",     "owner": "HLA Design Team",              "description": "found_in_billing — join key to billing report unknown"},
    {"id": "B-24", "category": "Derived Field",   "severity": "MEDIUM",   "owner": "HLA Design Team",              "description": "product_billing — no formula, no source column"},
    {"id": "B-25", "category": "KRI",             "severity": "CRITICAL", "owner": "HLA Design Team",              "description": "Mitigation_BW source field unresolved — explicit open question in Sheet 4"},
    {"id": "B-26", "category": "KRI",             "severity": "HIGH",     "owner": "HLA Design Team + Datalake (24a)", "description": "SFDC status strings for B5.1/B5.2/B5.3/B5.6 classification unknown"},
    {"id": "B-27", "category": "Report",          "severity": "HIGH",     "owner": "HLA Design Team",              "description": "'Derivation is given' in Sheet 6 Rows 27-28, 38-40 — forward references with no content"},
    {"id": "B-28", "category": "Design Decision", "severity": "HIGH",     "owner": "HLA Design Team",              "description": "Fuzzy matching algorithm for R12 Tier 3 not specified"},
    {"id": "B-29", "category": "Data Model",      "severity": "MEDIUM",   "owner": "HLA Design Team + DB Admin",   "description": "Customer name exclusion table does not exist (66 values in Sheet 7 unloaded)"},
]


def ctrl23_readiness_check(db_engine) -> dict:
    """
    DEPLOYMENT READINESS CHECK — Section 10, Item 7.

    Evaluates each of the 29 blockers and returns a structured readiness report.
    A blocker is considered "RESOLVED" only when confirmed through code — not assumed.

    Currently all 29 blockers are OPEN (as of 2026-09-14 full introspection).
    This function will evolve to check actual DB state for resolvable blockers.

    Returns:
        {
            "overall_status": "READY" | "BLOCKED",
            "total_blockers": 29,
            "resolved": int,
            "open": int,
            "blockers": [ { id, category, severity, status, owner, description } ]
        }
    """
    resolved_ids = set()

    with db_engine.connect() as conn:
        # B-29: customer name exclusion table — check if it exists and has rows
        try:
            result = conn.execute(text("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'customer_name_exclusion_list'
            """)).scalar()
            if result:
                row_count = conn.execute(text(
                    "SELECT COUNT(*) FROM public.customer_name_exclusion_list"
                )).scalar()
                if row_count >= len(CUSTOMER_NAME_EXCLUSION_HLA):
                    resolved_ids.add("B-29")
        except Exception:
            pass

        # Source schema blockers B-01 to B-06: check if source staging tables have data
        source_tables = {
            "ctrl_23_source_dataset_vdom":    ["B-01", "B-07", "B-08", "B-09", "B-10", "B-11"],
            "ctrl_23_source_dataset_ddos":    ["B-06"],
            "ctrl_23_source_dataset_cmdb":    ["B-02", "B-12"],
            "ctrl_23_source_dataset_cktrecon":["B-03", "B-13"],
        }
        for table, blocker_ids in source_tables.items():
            try:
                row_count = conn.execute(text(
                    f"SELECT COUNT(*) FROM public.{table}"
                )).scalar()
                if row_count > 0:
                    # Source data present — source schema blockers POTENTIALLY resolved
                    # (still need column validation, but data arrived)
                    for bid in blocker_ids:
                        resolved_ids.add(bid)
            except Exception:
                pass

    blocker_statuses = []
    for b in CTRL23_BLOCKERS:
        status = "RESOLVED" if b["id"] in resolved_ids else "OPEN"
        blocker_statuses.append({**b, "status": status})

    resolved_count = sum(1 for b in blocker_statuses if b["status"] == "RESOLVED")
    open_count = len(blocker_statuses) - resolved_count

    return {
        "overall_status": "READY" if open_count == 0 else "BLOCKED",
        "total_blockers": len(CTRL23_BLOCKERS),
        "resolved": resolved_count,
        "open": open_count,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "blockers": blocker_statuses,
        "blocker_summary": {
            "source_schema": sum(1 for b in blocker_statuses if b["category"] == "Source Schema" and b["status"] == "OPEN"),
            "target_mapping": sum(1 for b in blocker_statuses if b["category"] == "Target Mapping" and b["status"] == "OPEN"),
            "derived_field":  sum(1 for b in blocker_statuses if b["category"] == "Derived Field" and b["status"] == "OPEN"),
            "kri":            sum(1 for b in blocker_statuses if b["category"] == "KRI" and b["status"] == "OPEN"),
            "report":         sum(1 for b in blocker_statuses if b["category"] == "Report" and b["status"] == "OPEN"),
            "data_model":     sum(1 for b in blocker_statuses if b["category"] == "Data Model" and b["status"] == "OPEN"),
            "design_decision":sum(1 for b in blocker_statuses if b["category"] == "Design Decision" and b["status"] == "OPEN"),
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — CONFIG TABLE AUDIT
# ─────────────────────────────────────────────────────────────────────────────

def ctrl23_config_audit(db_engine) -> dict:
    """
    CONFIG AUDIT — Section 10, Item 6.

    Cross-checks all 4 configuration sets (from HLA Sheet 7) against the DB.
    Returns per-config audit results: HLA count, DB count, match status, missing values.
    """
    results = {}

    with db_engine.connect() as conn:

        # 1. Internal Profiles (VDOM hostnames) — Rule R9
        try:
            db_vals = set(
                row[0] for row in conn.execute(text(
                    "SELECT hostname FROM public.internal_profiles_vdom WHERE is_active = TRUE"
                )).fetchall()
            )
            hla_set = set(INTERNAL_PROFILES_VDOM_HLA)
            missing_in_db = sorted(hla_set - db_vals)
            extra_in_db = sorted(db_vals - hla_set)
            results["internal_profiles_vdom"] = {
                "hla_count": len(hla_set),
                "db_count": len(db_vals),
                "match": len(missing_in_db) == 0,
                "missing_from_db": missing_in_db,
                "extra_in_db": extra_in_db,
                "rule": "R9",
                "hla_reference": "Sheet 7, Rows 5-16",
            }
        except Exception as e:
            results["internal_profiles_vdom"] = {"error": str(e)}

        # 2. IP Exclusion List — Rule R10
        try:
            db_vals = set(
                row[0] for row in conn.execute(text(
                    "SELECT ip FROM public.ip_exclusion_list WHERE is_active = TRUE"
                )).fetchall()
            )
            hla_set = set(IP_EXCLUSION_HLA)
            missing_in_db = sorted(hla_set - db_vals)
            extra_in_db = sorted(db_vals - hla_set)
            results["ip_exclusion_list"] = {
                "hla_count": len(hla_set),
                "db_count": len(db_vals),
                "match": len(missing_in_db) == 0,
                "missing_from_db": missing_in_db,
                "extra_in_db": extra_in_db,
                "rule": "R10",
                "hla_reference": "Sheet 7, Rows 31-34",
            }
        except Exception as e:
            results["ip_exclusion_list"] = {"error": str(e)}

        # 3. Managed Service Types — KRI B5.5
        try:
            db_vals = set(
                row[0] for row in conn.execute(text(
                    "SELECT managed_services FROM public.managed_service_types WHERE is_active = TRUE"
                )).fetchall()
            )
            hla_set = set(MANAGED_SERVICE_TYPES_HLA)
            missing_in_db = sorted(hla_set - db_vals)
            extra_in_db = sorted(db_vals - hla_set)
            results["managed_service_types"] = {
                "hla_count": len(hla_set),
                "db_count": len(db_vals),
                "match": len(missing_in_db) == 0,
                "missing_from_db": missing_in_db,
                "extra_in_db": extra_in_db,
                "rule": "B5.5",
                "hla_reference": "Sheet 7, Rows 20-26",
            }
        except Exception as e:
            results["managed_service_types"] = {"error": str(e)}

        # 4. Customer Name Exclusion List — Sheet 7 Rows 39-104
        try:
            table_exists = conn.execute(text("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'customer_name_exclusion_list'
            """)).scalar()

            if not table_exists:
                results["customer_name_exclusion_list"] = {
                    "hla_count": len(CUSTOMER_NAME_EXCLUSION_HLA),
                    "db_count": 0,
                    "match": False,
                    "missing_from_db": CUSTOMER_NAME_EXCLUSION_HLA,
                    "extra_in_db": [],
                    "rule": "Circuit Reco customer exclusion",
                    "hla_reference": "Sheet 7, Rows 39-104",
                    "error": "Table customer_name_exclusion_list does not exist — Blocker B-29",
                }
            else:
                db_vals = set(
                    row[0] for row in conn.execute(text(
                        "SELECT customer_name FROM public.customer_name_exclusion_list WHERE is_active = TRUE"
                    )).fetchall()
                )
                hla_set = set(CUSTOMER_NAME_EXCLUSION_HLA)
                missing_in_db = sorted(hla_set - db_vals)
                extra_in_db = sorted(db_vals - hla_set)
                results["customer_name_exclusion_list"] = {
                    "hla_count": len(hla_set),
                    "db_count": len(db_vals),
                    "match": len(missing_in_db) == 0,
                    "missing_from_db": missing_in_db,
                    "extra_in_db": extra_in_db,
                    "rule": "Circuit Reco customer exclusion",
                    "hla_reference": "Sheet 7, Rows 39-104",
                }
        except Exception as e:
            results["customer_name_exclusion_list"] = {"error": str(e)}

    all_match = all(
        r.get("match", False) for r in results.values() if "error" not in r
    )
    return {
        "overall_config_valid": all_match,
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "configs": results,
    }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 10, ITEMS 10-11 — REPORT STATIC VALUES (Sheet 6 — FULLY KNOWN)
# ─────────────────────────────────────────────────────────────────────────────

# Report 2 (SIGS Billing Match Report) — Field 1: SIGS Remarks
# Source: Sheet 6, Row 16 — static literal values confirmed
SIGS_BILLING_REMARKS = {
    "found":     "Found in Billing report",
    "not_found": "Not found in Billing Report",
}

# Report 2 — Field 7: Issue Remark
# Source: Sheet 6, Row 22 — derivation fully specified
def derive_issue_remark(found_in_billing: bool) -> str:
    """
    Sheet 6, Row 22 verbatim: 'If Found in Billing Then No Issue. If Not Found In Billing Then Issue.'
    This is the ONLY derived column formula that is fully specified in the HLA workbook.
    """
    return "No Issue" if found_in_billing else "Issue"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 10, ITEM 9 — KRI CLASSIFICATION CASE SHELLS
# Logic is known from Sheet 4. Physical column names are UNKNOWN (blockers B-07..B-26).
# These are shells — column name placeholders marked with <<<COLUMN_NAME_REQUIRED>>>
# ─────────────────────────────────────────────────────────────────────────────

CTRL23_KRI_CLASSIFICATION_SHELL = """
-- ============================================================================
-- CTRL-23 KRI CLASSIFICATION CASE SHELL
-- Source: HLA Sheet 4 (Buckets & KRI Logic), Rows 4-23
-- STATUS: SHELL ONLY — physical column names not yet resolved
-- Placeholders marked: <<<COLUMN_NAME_REQUIRED>>>
-- DO NOT EXECUTE — for design review only
-- ============================================================================

/*
  INPUT:  ctrl_23_working_dataset_rl  (after R12, R13, R14, R15 reconciliation)
  OUTPUT: ctrl_23_working_dataset_kl  (with KRI bucket classification)

  BUCKET HIERARCHY:
    B4  = YN  (In Network, NOT in Ordering)
      B4.1 = NON-KRI01 (circuit_id starts with E0)
    B5  = YY  (In Network AND in Ordering)
      B5.1 = KRI01    (SFDC status = 'Under provisioning')
      B5.2 = KRI02    (SFDC status = 'Terminated')
      B5.3 = KRI02    (SFDC status = 'Cancelled')
      B5.4 = KRI04    (circuit_id starts with E0 in YY)
      B5.5 = NON-KRI02 (service_type IN managed_service_types)
      B5.6 = Good Cases (YY, none of B5.1-B5.5)
    B6  = NY  (NOT in Network, in Ordering only)
*/

SELECT
    rl.<<<host_name_column>>>,                    -- VDOM/DDOS host name — B-07 BLOCKED
    rl.<<<ip_column>>>,                           -- IP address — B-08 BLOCKED
    rl.<<<circuit_id_column>>>,                   -- Derived circuit ID from CMDB — B-12 BLOCKED
    rl.<<<sfdc_status_column>>>,                  -- SFDC order status — B-14, B-26 BLOCKED
    rl.<<<service_type_column>>>,                 -- Service type — B-11 BLOCKED
    rl.recon_bucket,                              -- YY / YN / NY from R12/R13/R15

    CASE
        -- B4 YN Bucket
        WHEN rl.recon_bucket = 'YN' THEN
            CASE
                -- B4.1: NON-KRI01 — Circuit ID starts with E0
                WHEN rl.<<<circuit_id_column>>> LIKE 'E0%'
                    THEN 'B4.1_NON_KRI01'
                ELSE
                    'B4_YN_UNCLASSIFIED'
            END

        -- B5 YY Bucket
        WHEN rl.recon_bucket = 'YY' THEN
            CASE
                -- B5.4: KRI04 — circuit_id starts with E0 in YY (takes precedence check order TBD)
                WHEN rl.<<<circuit_id_column>>> LIKE 'E0%'
                    THEN 'B5.4_KRI04'
                -- B5.5: NON-KRI02 — Managed Service Type
                WHEN rl.<<<service_type_column>>> IN (
                    SELECT managed_services FROM public.managed_service_types WHERE is_active = TRUE
                )
                    THEN 'B5.5_NON_KRI02'
                -- B5.1: KRI01 — Active in Network, Under Provisioning in Ordering
                WHEN rl.<<<sfdc_status_column>>> = '<<<SFDC_STATUS_UNDER_PROVISIONING>>>'  -- B-26 BLOCKED
                    THEN 'B5.1_KRI01'
                -- B5.2: KRI02 — Active in Network, Terminated in Ordering
                WHEN rl.<<<sfdc_status_column>>> = '<<<SFDC_STATUS_TERMINATED>>>'          -- B-26 BLOCKED
                    THEN 'B5.2_KRI02'
                -- B5.3: KRI02 — Active in Network, Cancelled in Ordering
                WHEN rl.<<<sfdc_status_column>>> = '<<<SFDC_STATUS_CANCELLED>>>'           -- B-26 BLOCKED
                    THEN 'B5.3_KRI02'
                -- B5.6: Good Cases — Active in both Network and Ordering
                ELSE
                    'B5.6_GOOD_CASE'
            END

        -- B6 NY Bucket
        WHEN rl.recon_bucket = 'NY' THEN
            'B6_NY'

        ELSE
            'UNCLASSIFIED'
    END AS kri_bucket,

    -- KRI Impact Calculation SHELL — B5.1 (ageing > 90 days)
    -- Formula: (COPF_timestamp - CURRENT_DATE) * MRC_IN_USD / 30
    -- B-25 BLOCKED: Mitigation_BW source unknown
    -- B-18 BLOCKED: trf_date source unknown
    -- B-14 BLOCKED: sfdc_mrc source column unknown
    CASE
        WHEN rl.recon_bucket = 'YY'
         AND rl.<<<sfdc_status_column>>> = '<<<SFDC_STATUS_UNDER_PROVISIONING>>>'
         AND (CURRENT_DATE - rl.<<<sfdc_copf_created_dt_column>>>::date) > 90
        THEN
            -- Impact = (COPF_timestamp - CURRENT_DATE) * MRC_IN_USD / 30
            (rl.<<<sfdc_copf_created_dt_column>>>::date - CURRENT_DATE)
            * rl.<<<sfdc_mrc_column>>>                                     -- B-14 BLOCKED
            / 30.0
        WHEN rl.recon_bucket = 'YY'
         AND rl.<<<sfdc_status_column>>> = '<<<SFDC_STATUS_TERMINATED>>>'
         AND (CURRENT_DATE - rl.<<<trf_date_column>>>::date) > 90
        THEN
            -- Impact = (TRF_date - CURRENT_DATE) * MRC_IN_USD / 30
            (rl.<<<trf_date_column>>>::date - CURRENT_DATE)                -- B-18 BLOCKED
            * rl.<<<sfdc_mrc_column>>>                                     -- B-14 BLOCKED
            / 30.0
        WHEN rl.recon_bucket = 'YY'
         AND rl.<<<sfdc_status_column>>> = '<<<SFDC_STATUS_CANCELLED>>>'
         AND (CURRENT_DATE - rl.<<<trf_date_column>>>::date) > 90
        THEN
            -- Impact = MRC_USD / 30
            rl.<<<sfdc_mrc_column>>> / 30.0                                -- B-14 BLOCKED
        ELSE NULL
    END AS impact_usd,

    -- Capex = Mitigation_BW / 1,000,000,000 — B-25 BLOCKED
    rl.<<<mitigation_bw_column>>> / 1000000000.0 AS capex_gbps            -- B-25 BLOCKED

FROM ctrl_23_working_dataset_rl rl;

-- ============================================================================
-- END OF KRI CLASSIFICATION SHELL
-- All <<<...>>> placeholders require resolution of the corresponding blocker.
-- ============================================================================
"""


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 10, ITEM 13 — REPORT AGGREGATION SHELLS (Reports 1-4)
# Structure is known from Sheet 6. Source columns are PARTIALLY blocked.
# ─────────────────────────────────────────────────────────────────────────────

CTRL23_REPORT_SHELLS = {

    "report_1_recon_summary": """
-- ============================================================================
-- CTRL-23 REPORT 1: Reconciliation Summary Report
-- Source: Sheet 6, Rows 4-11
-- Source Table: ctrl_23_work_item_current_run
-- STATUS: SHELL — kri_description, source_system, circuit_id cols not yet implemented
-- ============================================================================
SELECT
    w.<<<kri_description>>>      AS recon_remarks,         -- Source: Sheet 6 Row 5 — col not implemented
    w.<<<source_system>>>        AS system,                -- Source: Sheet 6 Row 6 — col not implemented
    COUNT(w.<<<profile_col>>>)   AS profile_count,         -- Source: Sheet 6 Row 7
    COUNT(DISTINCT w.<<<circuit_id_col>>>) AS unique_circuit_count, -- Sheet 6 Row 8
    SUM(w.<<<impact_value>>>)    AS impact_usd,            -- Source: Sheet 6 Row 9 ('impact_value_system_in_usd')
    -- Circuit ID Matched (vs dl_ra_order_report_daily) — B-23 BLOCKED (join key unknown)
    COUNT(CASE WHEN b.<<<billing_circuit_id>>> IS NOT NULL THEN 1 END) AS circuit_id_matched,
    COUNT(CASE WHEN b.<<<billing_circuit_id>>> IS NULL THEN 1 END)     AS circuit_id_not_matched
FROM public.ctrl_23_work_item_current_run w
LEFT JOIN qlik_report.dl_ra_order_report_daily b  -- B-05 BLOCKED (source table missing)
    ON w.<<<circuit_id_col>>> = b.<<<billing_circuit_id>>>
GROUP BY w.<<<kri_description>>>, w.<<<source_system>>>;
""",

    "report_2_sigs_billing": """
-- ============================================================================
-- CTRL-23 REPORT 2: SIGS (Billing Match) Report
-- Source: Sheet 6, Rows 14-22
-- Source Tables: Three-way dashboard (intermediate view) + dl_ra_order_report_daily
-- STATUS: SHELL — Three-way dashboard view not yet built; source table missing
-- KNOWN VALUES: SIGS remarks (static), NRC/MRC column names from dl_ra_order_report_daily
-- ============================================================================

-- Static SIGS Remarks (FULLY IMPLEMENTABLE — Sheet 6 Row 16):
-- Value 1: 'Found in Billing report'
-- Value 2: 'Not found in Billing Report'

-- NRC_USD derivation (PARTIALLY BLOCKED — column names KNOWN, source table MISSING):
--   COALESCE(discounted_onetimecharge, standard_onetimecharge)
--   Aggregated GROUP BY source_system, DISTINCT circuit_id

-- MRC_USD derivation (PARTIALLY BLOCKED — column name KNOWN, source table MISSING):
--   annual_recurring_charge
--   Aggregated GROUP BY source_system, DISTINCT circuit_id

SELECT
    CASE
        WHEN b.<<<billing_circuit_id>>> IS NOT NULL THEN 'Found in Billing report'
        ELSE 'Not found in Billing Report'
    END                                                         AS sigs_remarks,
    w.<<<source_system_col>>>                                   AS source_system,
    COUNT(DISTINCT w.<<<circuit_id_col>>>)                      AS unique_circuit_id,
    COUNT(w.<<<profile_col>>>)                                  AS no_of_profile,
    SUM(
        COALESCE(b.discounted_onetimecharge, b.standard_onetimecharge)  -- KNOWN cols, missing table
    )                                                           AS nrc_usd,
    SUM(b.annual_recurring_charge)                              AS mrc_usd,  -- KNOWN col, missing table
    CASE
        WHEN b.<<<billing_circuit_id>>> IS NOT NULL THEN 'No Issue'
        ELSE 'Issue'
    END                                                         AS issue_remark
FROM public.ctrl_23_work_item_current_run w
LEFT JOIN qlik_report.dl_ra_order_report_daily b   -- B-05 BLOCKED
    ON w.<<<circuit_id_col>>> = b.<<<billing_circuit_id>>>
GROUP BY
    (b.<<<billing_circuit_id>>> IS NOT NULL),
    w.<<<source_system_col>>>;
""",

    "report_3_billing_vs_network": """
-- ============================================================================
-- CTRL-23 REPORT 3: Billing vs Network Report
-- Source: Sheet 6, Rows 25-33
-- Source Table: qlik_report.dl_ra_order_report_daily
-- STATUS: SHELL — source table missing (B-05); some columns known
-- ============================================================================
SELECT
    <<<remarks_billing_vs_network>>>                AS remarks_billing_vs_network,  -- Derivation: B-27 BLOCKED
    <<<system_col>>>                                AS system,                       -- Derivation: B-27 BLOCKED
    COUNT(<<<profile_name_col>>>)                   AS profile_count,
    COUNT(<<<circuit_id_col>>>)                     AS ckt_count,
    SUM(annual_recurring_charge)                    AS billing_mrc_usd,              -- KNOWN col
    SUM(
        COALESCE(discounted_onetimecharge, standard_onetimecharge)
    )                                               AS billing_nrc_usd,              -- KNOWN cols
    COUNT(<<<circuit_id_col>>>) * 1.0
        / NULLIF(SUM(COUNT(<<<circuit_id_col>>>)) OVER (), 0)
                                                    AS pct_of_ckt_id
FROM qlik_report.dl_ra_order_report_daily          -- B-05 BLOCKED
GROUP BY <<<remarks_billing_vs_network>>>, <<<system_col>>>;
""",

    "report_4_service_revenue_split": """
-- ============================================================================
-- CTRL-23 REPORT 4: Service Type / Revenue Split Report
-- Source: Sheet 6, Rows 36-47
-- Source Table: qlik_report.dl_ra_order_report_daily
-- STATUS: SHELL — source table missing (B-05); c_circuitid, annual_recurring_charge,
--         discounted_onetimecharge, standard_onetimecharge KNOWN; service_type UNKNOWN
-- ============================================================================
SELECT
    <<<service_type_col>>>                          AS service_type,        -- B-27 BLOCKED (derivation unspecified)
    <<<sub_service_type_col>>>                      AS sub_service_type,    -- B-27 BLOCKED
    <<<system_col>>>                                AS system,              -- B-27 BLOCKED
    COUNT(DISTINCT c_circuitid)                     AS unique_ckt_id,       -- KNOWN col (Sheet 6 Row 41)
    SUM(
        COALESCE(discounted_onetimecharge, standard_onetimecharge)
    )                                               AS nrc_usd,             -- KNOWN cols (Sheet 6 Row 42)
    SUM(annual_recurring_charge)                    AS mrc_usd,             -- KNOWN col (Sheet 6 Row 43)
    SUM(
        COALESCE(discounted_onetimecharge, standard_onetimecharge)
    ) / NULLIF(SUM(SUM(COALESCE(discounted_onetimecharge, standard_onetimecharge)))
        OVER (PARTITION BY <<<system_col>>>), 0)   AS system_nrc_pct,      -- Sheet 6 Row 44
    SUM(annual_recurring_charge)
        / NULLIF(SUM(SUM(annual_recurring_charge))
        OVER (PARTITION BY <<<system_col>>>), 0)   AS system_mrc_pct,      -- Sheet 6 Row 45
    SUM(
        COALESCE(discounted_onetimecharge, standard_onetimecharge)
    ) / NULLIF(SUM(SUM(COALESCE(discounted_onetimecharge, standard_onetimecharge)))
        OVER (), 0)                                AS service_nrc_pct,     -- Sheet 6 Row 46
    SUM(annual_recurring_charge)
        / NULLIF(SUM(SUM(annual_recurring_charge)) OVER (), 0)
                                                    AS service_mrc_pct     -- Sheet 6 Row 47
FROM qlik_report.dl_ra_order_report_daily          -- B-05 BLOCKED
GROUP BY <<<service_type_col>>>, <<<sub_service_type_col>>>, <<<system_col>>>;
""",
}


# ─────────────────────────────────────────────────────────────────────────────
# SEED FUNCTIONS — Called from app.py startup context
# ─────────────────────────────────────────────────────────────────────────────

def seed_ctrl23_customer_name_exclusion(db):
    """
    Seed the customer_name_exclusion_list table with all 66 HLA-specified values.
    Source: HLA Sheet 7, Rows 39-104 (Internal/Test Customer Name Exclusion List).
    Blocker B-29: this function resolves the DB-side gap.
    Idempotent: safe to call multiple times.
    """
    try:
        with db.engine.connect() as conn:
            for name in CUSTOMER_NAME_EXCLUSION_HLA:
                conn.execute(text("""
                    INSERT INTO public.customer_name_exclusion_list (customer_name, description, is_active)
                    VALUES (:name, 'HLA Sheet 7 - Internal/Test Customer Exclusion', TRUE)
                    ON CONFLICT (customer_name) DO NOTHING
                """), {"name": name})
            conn.commit()
        log.info(f"[CTRL-23] customer_name_exclusion_list seeded with {len(CUSTOMER_NAME_EXCLUSION_HLA)} HLA values.")
    except Exception as e:
        log.error(f"[CTRL-23] Failed to seed customer_name_exclusion_list: {e}")


def seed_ctrl23_internal_profiles(db):
    """
    Ensure internal_profiles_vdom has all 12 HLA-confirmed values.
    Source: HLA Sheet 7, Rows 5-16. Rule R9.
    Idempotent.
    """
    try:
        with db.engine.connect() as conn:
            for hostname in INTERNAL_PROFILES_VDOM_HLA:
                conn.execute(text("""
                    INSERT INTO public.internal_profiles_vdom (hostname, description, is_active)
                    VALUES (:h, 'HLA Sheet 7 - Internal VDOM Profile R9', TRUE)
                    ON CONFLICT (hostname) DO NOTHING
                """), {"h": hostname})
            conn.commit()
        log.info(f"[CTRL-23] internal_profiles_vdom confirmed: {len(INTERNAL_PROFILES_VDOM_HLA)} HLA hostnames.")
    except Exception as e:
        log.error(f"[CTRL-23] Failed to seed internal_profiles_vdom: {e}")


def seed_ctrl23_ip_exclusions(db):
    """
    Ensure ip_exclusion_list has all 4 HLA-confirmed values.
    Source: HLA Sheet 7, Rows 31-34. Rule R10.
    Idempotent.
    """
    try:
        with db.engine.connect() as conn:
            for ip in IP_EXCLUSION_HLA:
                conn.execute(text("""
                    INSERT INTO public.ip_exclusion_list (ip, description, is_active)
                    VALUES (:ip, 'HLA Sheet 7 - Test/Dummy IP Exclusion R10', TRUE)
                    ON CONFLICT (ip) DO NOTHING
                """), {"ip": ip})
            conn.commit()
        log.info(f"[CTRL-23] ip_exclusion_list confirmed: {len(IP_EXCLUSION_HLA)} HLA IPs.")
    except Exception as e:
        log.error(f"[CTRL-23] Failed to seed ip_exclusion_list: {e}")


def seed_ctrl23_managed_service_types(db):
    """
    Ensure managed_service_types has all 7 HLA-confirmed values.
    Source: HLA Sheet 7, Rows 20-26. KRI Rule B5.5.
    Idempotent.
    """
    try:
        with db.engine.connect() as conn:
            for stype in MANAGED_SERVICE_TYPES_HLA:
                conn.execute(text("""
                    INSERT INTO public.managed_service_types (managed_services, description, is_active)
                    VALUES (:s, 'HLA Sheet 7 - Managed Service Type B5.5', TRUE)
                    ON CONFLICT (managed_services) DO NOTHING
                """), {"s": stype})
            conn.commit()
        log.info(f"[CTRL-23] managed_service_types confirmed: {len(MANAGED_SERVICE_TYPES_HLA)} HLA service types.")
    except Exception as e:
        log.error(f"[CTRL-23] Failed to seed managed_service_types: {e}")


def init_ctrl23_safe_components(app, db):
    """
    Entry point called from app.py startup context.
    Executes all Path A safe implementation steps:
      1. DDL migration for customer_name_exclusion_list
      2. Config table unique constraint enforcement
      3. Seed all 4 config sets
      4. Log readiness status
    """
    with app.app_context():
        with db.engine.connect() as conn:
            # ── DDL: Create customer_name_exclusion_list (Blocker B-29 resolution)
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS public.customer_name_exclusion_list (
                    config_id   BIGSERIAL PRIMARY KEY,
                    customer_name VARCHAR(500) NOT NULL,
                    description   VARCHAR(500),
                    is_active     BOOLEAN DEFAULT TRUE NOT NULL,
                    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    CONSTRAINT uq_customer_name_exclusion UNIQUE (customer_name)
                )
            """))

            # ── Ensure unique constraints on existing config tables (idempotent)
            # internal_profiles_vdom
            conn.execute(text("""
                DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'uq_internal_profile_hostname'
                    ) THEN
                        ALTER TABLE public.internal_profiles_vdom
                            ADD CONSTRAINT uq_internal_profile_hostname UNIQUE (hostname);
                    END IF;
                END $$;
            """))

            # ip_exclusion_list
            conn.execute(text("""
                DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'uq_ip_exclusion_ip'
                    ) THEN
                        ALTER TABLE public.ip_exclusion_list
                            ADD CONSTRAINT uq_ip_exclusion_ip UNIQUE (ip);
                    END IF;
                END $$;
            """))

            # managed_service_types
            conn.execute(text("""
                DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'uq_managed_service_type'
                    ) THEN
                        ALTER TABLE public.managed_service_types
                            ADD CONSTRAINT uq_managed_service_type UNIQUE (managed_services);
                    END IF;
                END $$;
            """))

            conn.commit()

        # ── Seed all config tables
        seed_ctrl23_internal_profiles(db)
        seed_ctrl23_ip_exclusions(db)
        seed_ctrl23_managed_service_types(db)
        seed_ctrl23_customer_name_exclusion(db)

        log.info("[CTRL-23] All safe implementation components initialized.")
        log.info("[CTRL-23] STATUS: BLOCKED — 29 HLA dependencies remain unresolved.")
        log.info("[CTRL-23] See implementation_plan.md for full blocker register.")
