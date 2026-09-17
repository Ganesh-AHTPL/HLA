"""
HLA Entity Parser.
Determines required staged pipeline entities from parsed HLA metadata (RULE 12).
Only generates entities actually required by the active HLA.
"""

from typing import Dict, List, Tuple
from backend.hla.hla_model import HLAControl, HLAEntityDef
from backend.core.constants import (
    STAGE_1_ACQUISITION,
    STAGE_2_FILTERING,
    STAGE_3_BALANCE,
    STAGE_4_RECONCILIATION,
    STAGE_5_KRI_NON_KRI,
    STAGE_6_CURRENT_RUN_WORK_ITEM,
    STAGE_7_HISTORICAL_WORK_ITEM,
    STAGE_8_REPORTING,
    PATTERN_ACQUISITION_TABLE,
    PATTERN_FILTERED_TABLE,
    PATTERN_FILTER_SUMMARY,
    PATTERN_BALANCE_TABLE,
    PATTERN_WORKING_RL,
    PATTERN_WORKING_KL,
    PATTERN_WORK_ITEM_CURRENT_RUN,
    PATTERN_WORK_ITEM_HISTORICAL,
    PATTERN_NON_KRI_SUMMARY,
    PATTERN_NON_KRI_DETAILS,
    PATTERN_KRI_SUMMARY,
    PATTERN_CASE_SUMMARY
)


class EntityParser:
    """
    Constructs the target entity dictionary for the staged pipeline.
    """

    @classmethod
    def plan_entities_for_control(cls, hla: HLAControl) -> Dict[str, HLAEntityDef]:
        entities: Dict[str, HLAEntityDef] = {}

        # 1. Stage 1 Entities: One acquisition entity per distinct external source stream
        for stream_name, stream_def in hla.source_streams.items():
            clean_stream = stream_name.upper().replace("/", "_").replace(" ", "_")
            ent_key = f"SOURCE_{clean_stream}"
            entities[ent_key] = HLAEntityDef(
                entity_name=ent_key,
                stage=STAGE_1_ACQUISITION,
                table_pattern=PATTERN_ACQUISITION_TABLE,
                source_streams=[stream_name],
                description=f"Raw acquisition dataset for stream {stream_name}"
            )

        # 2. Stage 2 Entities: Filtered datasets
        for stream_name in hla.source_streams.keys():
            clean_stream = stream_name.upper().replace("/", "_").replace(" ", "_")
            ent_key = f"FILTERED_{clean_stream}"
            entities[ent_key] = HLAEntityDef(
                entity_name=ent_key,
                stage=STAGE_2_FILTERING,
                table_pattern=PATTERN_FILTERED_TABLE,
                source_streams=[stream_name],
                description=f"Filtered dataset for stream {stream_name}"
            )

        # Stage 2 Filter Summary
        entities["FILTER_SUMMARY"] = HLAEntityDef(
            entity_name="FILTER_SUMMARY",
            stage=STAGE_2_FILTERING,
            table_pattern=PATTERN_FILTER_SUMMARY,
            description="Pre-execution filter audit summary"
        )

        # 3. Stage 3 Entities: Balance datasets
        for stream_name in hla.source_streams.keys():
            clean_stream = stream_name.upper().replace("/", "_").replace(" ", "_")
            ent_key = f"BALANCE_{clean_stream}"
            entities[ent_key] = HLAEntityDef(
                entity_name=ent_key,
                stage=STAGE_3_BALANCE,
                table_pattern=PATTERN_BALANCE_TABLE,
                source_streams=[stream_name],
                description=f"Balance dataset for stream {stream_name}"
            )

        # 4. Stage 4 Entity: Reconciliation Working Dataset RL
        entities["WORKING_RL"] = HLAEntityDef(
            entity_name="WORKING_RL",
            stage=STAGE_4_RECONCILIATION,
            table_pattern=PATTERN_WORKING_RL,
            description="Reconciliation dataset with match classification (YY, YN, NY)"
        )

        # 5. Stage 5 Entity: KRI Working Dataset KL
        entities["WORKING_KL"] = HLAEntityDef(
            entity_name="WORKING_KL",
            stage=STAGE_5_KRI_NON_KRI,
            table_pattern=PATTERN_WORKING_KL,
            description="KRI and non-KRI evaluated working dataset"
        )

        # 6. Stage 6 Entity: Current Run Work Items
        entities["WORK_ITEM_CURRENT_RUN"] = HLAEntityDef(
            entity_name="WORK_ITEM_CURRENT_RUN",
            stage=STAGE_6_CURRENT_RUN_WORK_ITEM,
            table_pattern=PATTERN_WORK_ITEM_CURRENT_RUN,
            description="Current execution cycle work items"
        )

        # 7. Stage 7 Entity: Historical Work Items
        entities["WORK_ITEM_HISTORICAL"] = HLAEntityDef(
            entity_name="WORK_ITEM_HISTORICAL",
            stage=STAGE_7_HISTORICAL_WORK_ITEM,
            table_pattern=PATTERN_WORK_ITEM_HISTORICAL,
            description="Persistent historical work items archive"
        )

        # 8. Stage 8 Entities: Report & Summary datasets
        entities["NON_KRI_SUMMARY"] = HLAEntityDef(
            entity_name="NON_KRI_SUMMARY",
            stage=STAGE_8_REPORTING,
            table_pattern=PATTERN_NON_KRI_SUMMARY,
            description="Management summary of non-KRI exceptions"
        )
        entities["NON_KRI_DETAILS"] = HLAEntityDef(
            entity_name="NON_KRI_DETAILS",
            stage=STAGE_8_REPORTING,
            table_pattern=PATTERN_NON_KRI_DETAILS,
            description="Detailed itemized non-KRI exceptions"
        )
        entities["KRI_SUMMARY"] = HLAEntityDef(
            entity_name="KRI_SUMMARY",
            stage=STAGE_8_REPORTING,
            table_pattern=PATTERN_KRI_SUMMARY,
            description="Executive summary of KRI metrics"
        )
        entities["CASE_SUMMARY"] = HLAEntityDef(
            entity_name="CASE_SUMMARY",
            stage=STAGE_8_REPORTING,
            table_pattern=PATTERN_CASE_SUMMARY,
            description="Aggregated case resolution summary"
        )

        return entities
