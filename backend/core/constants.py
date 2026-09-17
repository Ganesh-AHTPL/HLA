"""
Core platform constants and standards for HLA Studio.
Defines canonical envelopes, stage identifiers, and error categories.
"""

# Platform Envelope Standards (RULE 19, 39, 58)
PLATFORM_HEADER_COLUMNS = [
    ("ctrl_id", "INTEGER"),
    ("exec_seq", "INTEGER"),
    ("execution_date", "DATE"),
    ("execution_schedule", "VARCHAR(50)")
]

PLATFORM_HEADER_NAMES = [col[0] for col in PLATFORM_HEADER_COLUMNS]

PLATFORM_FOOTER_COLUMNS = [
    ("create_dtm", "TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP"),
    ("update_dtm", "TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP"),
    ("updated_by", "VARCHAR(100) DEFAULT CURRENT_USER"),
    ("processing_date", "DATE DEFAULT CURRENT_DATE")
]

PLATFORM_FOOTER_NAMES = [col[0] for col in PLATFORM_FOOTER_COLUMNS]

ALL_PLATFORM_COLUMNS = PLATFORM_HEADER_NAMES + PLATFORM_FOOTER_NAMES

# Columns forbidden from being auto-injected (RULE 19, 20, 38)
FORBIDDEN_AUTO_COLUMNS = {
    "id",
    "batch_id",
    "record_status",
    "source_reference",
    "kri_flag"
}

# Synthetic source column prefixes that must NEVER be generated (RULE 24, 38)
FORBIDDEN_SYNTHETIC_COLUMN_PREFIXES = {
    "b.vutm_doos",
    "b.cmdb",
    "b.circuit_reco",
    "b.sfdc",
    "b.billing"
}

# 8-Stage Canonical Pipeline Definitions (RULE 10, 56)
STAGE_1_ACQUISITION = "STAGE_1_ACQUISITION"
STAGE_2_FILTERING = "STAGE_2_FILTERING"
STAGE_3_BALANCE = "STAGE_3_BALANCE"
STAGE_4_RECONCILIATION = "STAGE_4_RECONCILIATION"
STAGE_5_KRI_NON_KRI = "STAGE_5_KRI_NON_KRI"
STAGE_6_CURRENT_RUN_WORK_ITEM = "STAGE_6_CURRENT_RUN_WORK_ITEM"
STAGE_7_HISTORICAL_WORK_ITEM = "STAGE_7_HISTORICAL_WORK_ITEM"
STAGE_8_REPORTING = "STAGE_8_REPORTING"

CANONICAL_STAGES = [
    STAGE_1_ACQUISITION,
    STAGE_2_FILTERING,
    STAGE_3_BALANCE,
    STAGE_4_RECONCILIATION,
    STAGE_5_KRI_NON_KRI,
    STAGE_6_CURRENT_RUN_WORK_ITEM,
    STAGE_7_HISTORICAL_WORK_ITEM,
    STAGE_8_REPORTING
]

# Canonical Table Naming Patterns
PATTERN_ACQUISITION_TABLE = "CTRL_{control_id}_SOURCE_DATASET_{entity}"
PATTERN_FILTERED_TABLE = "CTRL_{control_id}_FILTERED_DATASET_{entity}"
PATTERN_FILTER_SUMMARY = "CTRL_{control_id}_FILTER_SUMMARY"
PATTERN_BALANCE_TABLE = "CTRL_{control_id}_BALANCE_DATASET_{entity}"
PATTERN_BALANCE_SUMMARY = "CTRL_{control_id}_BALANCE_SUMMARY"
PATTERN_WORKING_RL = "CTRL_{control_id}_WORKING_DATASET_RL"
PATTERN_WORKING_KL = "CTRL_{control_id}_WORKING_DATASET_KL"
PATTERN_WORK_ITEM_CURRENT_RUN = "CTRL_{control_id}_WORK_ITEM_CURRENT_RUN"
PATTERN_WORK_ITEM_HISTORICAL = "CTRL_{control_id}_WORK_ITEM"

# Report patterns
PATTERN_NON_KRI_SUMMARY = "CTRL_{control_id}_NON_KRI_SUMMARY"
PATTERN_NON_KRI_DETAILS = "CTRL_{control_id}_NON_KRI_DETAILS"
PATTERN_KRI_SUMMARY = "CTRL_{control_id}_KRI_SUMMARY"
PATTERN_CASE_SUMMARY = "CTRL_{control_id}_CASE_SUMMARY"

# Reconciliation Match Types
RECON_MATCH_TYPE_YY = "YY"  # Matched in both Primary and Secondary
RECON_MATCH_TYPE_YN = "YN"  # Present in Primary only
RECON_MATCH_TYPE_NY = "NY"  # Present in Secondary only
