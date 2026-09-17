# 8-Stage Canonical Pipeline Specification

## Stage 1: ETL Acquisition
- **Pattern**: `CTRL_{control_id}_SOURCE_DATASET_{ENTITY}`
- **Purpose**: Raw extract from verified external source tables as-is + platform envelope.
- **Rules**: No reconciliation, no KRI calculation, no report logic.

## Stage 2: Pre-Execution Filtering
- **Pattern**: `CTRL_{control_id}_FILTERED_DATASET_{ENTITY}` and `CTRL_{control_id}_FILTER_SUMMARY`
- **Purpose**: Applies deduplication, null-key filtering, and exclusions.

## Stage 3: Balance
- **Pattern**: `CTRL_{control_id}_BALANCE_DATASET_{ENTITY}`
- **Purpose**: Prepares balanced data sets for cross-system reconciliation.

## Stage 4: Reconciliation (Working Dataset RL)
- **Pattern**: `CTRL_{control_id}_WORKING_DATASET_RL`
- **Purpose**: Executes `FULL OUTER JOIN` on resolved matching keys (`KEY_VALUE`).
- **Tagging**: Sets `balance_type` to `YY` (both), `YN` (primary only), `NY` (secondary only).

## Stage 5: KRI / Non-KRI (Working Dataset KL)
- **Pattern**: `CTRL_{control_id}_WORKING_DATASET_KL`
- **Purpose**: Applies KRI rules and assigns KRI breach status.

## Stage 6: Current Run Work Items
- **Pattern**: `CTRL_{control_id}_WORK_ITEM_CURRENT_RUN`
- **Purpose**: Isolated tracking of exceptions from the active cycle.

## Stage 7: Historical Work Items
- **Pattern**: `CTRL_{control_id}_WORK_ITEM`
- **Purpose**: Long-term persistent archive of all work items.

## Stage 8: Reports & Target Outputs
- **Pattern**: `CTRL_{control_id}_NON_KRI_SUMMARY`, `CTRL_{control_id}_NON_KRI_DETAILS`, `CTRL_{control_id}_KRI_SUMMARY`, `CTRL_{control_id}_CASE_SUMMARY`
- **Purpose**: Executive and operational management summaries derived from downstream datasets.
