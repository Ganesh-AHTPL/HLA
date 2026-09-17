# Safe Table Migration & Rebuilding Engine

## 1. Migration Overview
When existing PostgreSQL tables deviate from the generic 4-prefix and 4-suffix envelope or require column reordering, `MigrationEngine` executes a safe, atomic table rebuild without data loss.

## 2. 10-Step Table Rebuild Flow
1. **Dry Run**: Preview current columns vs canonical target columns.
2. **Create Temporary Table**: `CREATE TABLE "{schema}"."{table}_rebuild_tmp" (...)` with exact canonical column ordering.
3. **Copy Common Columns**: `INSERT INTO tmp (cols) SELECT (cols) FROM original;`
4. **Recreate Defaults**: Preserves default column values and sequences.
5. **Validate Row Counts**: Verifies `count(original) == count(tmp)`. If mismatch, rolls back immediately.
6. **Swap Tables Safely**: `DROP TABLE original CASCADE; ALTER TABLE tmp RENAME TO original;`
7. **Recreate Constraints**: Primary keys and foreign keys rebuilt.
8. **Recreate Indexes**: Rebuilds performance and envelope indexes.
9. **Post-Migration Validation**: Introspects table structure to confirm envelope order.
10. **Clean Up**: Ensures no temporary tables remain.
