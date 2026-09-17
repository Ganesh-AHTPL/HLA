# Source Resolution & Pre-Flight Validation

## 1. Resolution Chain
For every attribute defined in the HLA specification:
```
Logical Attribute
      ↓
Logical Source Stream
      ↓
Physical Source Table
      ↓
PostgreSQL Schema Introspection
      ↓
Actual Physical Column
      ↓
Validated SQL Expression
```

## 2. Pre-Flight Quality Gates
Before any DDL or transformation SQL is generated or executed, `DependencyResolver` validates:
- External source tables must exist in PostgreSQL. Missing tables trigger `SOURCE_DEPENDENCY_MISSING`.
- External source columns must exist in PostgreSQL metadata. Missing columns trigger `SOURCE_COLUMN_DEPENDENCY_MISSING`.
- Mappings must resolve cleanly. Missing mappings trigger `HLA_MAPPING_MISSING`.
- Unresolved derived formulas trigger `DERIVATION_DEPENDENCY_MISSING`.

Under no circumstances is `NULL` used as a silent fallback.
