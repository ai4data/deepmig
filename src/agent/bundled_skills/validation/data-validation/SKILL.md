---
name: data-validation
description: Validate migration results by comparing row counts and data quality between source expected values and Databricks target. Use after running migration scripts to verify data integrity before sign-off.
allowed-tools: Read, run_sql
---

# Data Validation Skill

## CRITICAL: Config-Driven Validation

**ALL validation queries MUST use values from the migration config. NEVER hardcode database, catalog, schema, or table names.**

### Step 1: Read Config First (MANDATORY)

Before ANY validation, read the config:
```
read_file("/memories/input/config/migration_config.json")
```

Extract these values:
```json
{
  "target": {
    "catalog": {
      "name": "{catalog}",           // e.g., "northwind_migration"
      "schemas": {
        "bronze": "{bronze_schema}", // e.g., "northwnd_bronze"
        "silver": "{silver_schema}", // e.g., "northwnd_silver"
        "gold": "{gold_schema}"      // e.g., "northwnd_gold"
      }
    }
  },
  "migration": {
    "bronze_tables": [
      {"target_table": "{table}", "expected_row_count": {N}},
      ...
    ]
  }
}
```

### Step 2: Build Dynamic Queries

Use the extracted values to build queries:
```sql
SELECT COUNT(*) as cnt FROM {catalog}.{bronze_schema}.{table_name}
```

**Example with config values:**
- Config: `catalog.name = "my_catalog"`, `schemas.bronze = "bronze_layer"`, table = `"customers"`
- Query: `SELECT COUNT(*) as cnt FROM my_catalog.bronze_layer.customers`

---

## CRITICAL: Databricks Query Patterns

**DO NOT use these patterns (they don't work in Databricks):**
```sql
-- WRONG: ROW_COUNT doesn't exist in Databricks information_schema
SELECT TABLE_NAME, ROW_COUNT FROM information_schema.tables  -- FAILS!

-- WRONG: source_metadata doesn't exist
SELECT * FROM source_metadata.tables  -- FAILS!

-- WRONG: Trying to get row counts from metadata
SELECT * FROM {catalog}.information_schema.tables WHERE ...  -- No ROW_COUNT column!
```

**ALWAYS use direct COUNT queries:**
```sql
-- CORRECT: Direct COUNT query on each table
SELECT COUNT(*) as cnt FROM {catalog}.{schema}.{table}
```

---

## When to Use
- After bronze layer ingestion to verify row counts match expected values
- After silver/gold transformations to check data quality
- Before signing off on a migration wave
- When debugging data discrepancies

---

## Validation Workflow

### Bronze Layer Validation (Wave 0)

1. **Read config:**
   ```
   config = read_file("/memories/input/config/migration_config.json")
   ```

2. **Extract values:**
   ```
   catalog = config.target.catalog.name
   bronze_schema = config.target.catalog.schemas.bronze
   tables = config.migration.bronze_tables
   ```

3. **For each table, run validation query:**
   ```
   for table in tables:
       query = f"SELECT COUNT(*) as cnt FROM {catalog}.{bronze_schema}.{table.target_table}"
       result = run_sql(query)
       actual = result[0]["cnt"]
       expected = table.expected_row_count
       status = "PASS" if actual == expected else "FAIL"
   ```

4. **Generate report** with results

### Gold Layer Validation (Wave 1+)

1. **Read config:**
   ```
   config = read_file("/memories/input/config/migration_config.json")
   ```

2. **Extract values:**
   ```
   catalog = config.target.catalog.name
   gold_schema = config.target.catalog.schemas.gold
   transformations = config.migration.transformation_waves.wave1.transformations
   ```

3. **For each transformation, run validation query:**
   ```
   for t in transformations:
       query = f"SELECT COUNT(*) as cnt FROM {catalog}.{gold_schema}.{t.name}"
       result = run_sql(query)
       actual = result[0]["cnt"]
       expected = t.expected_row_count
       status = "PASS" if actual == expected else "FAIL"
   ```

---

## Validation Query Templates

### Row Count Validation
```sql
SELECT COUNT(*) as cnt FROM {catalog}.{schema}.{table}
```

### Null Key Check
```sql
SELECT COUNT(*) as null_count
FROM {catalog}.{schema}.{table}
WHERE {primary_key} IS NULL
```

### Duplicate Key Check
```sql
SELECT {primary_key}, COUNT(*) as dup_count
FROM {catalog}.{schema}.{table}
GROUP BY {primary_key}
HAVING COUNT(*) > 1
```

### Batch Validation (All Tables at Once)

Build this query dynamically from config:
```sql
SELECT '{table1}' as table_name, {expected1} as expected, COUNT(*) as actual FROM {catalog}.{schema}.{table1}
UNION ALL SELECT '{table2}', {expected2}, COUNT(*) FROM {catalog}.{schema}.{table2}
UNION ALL SELECT '{table3}', {expected3}, COUNT(*) FROM {catalog}.{schema}.{table3}
-- ... continue for all tables from config
```

---

## Data Quality Rules (from Config)

Read quality rules from `config.validation.data_quality_rules`:
```json
{
  "validation": {
    "data_quality_rules": [
      {"table": "orders_fact", "rule": "unit_price > 0", "description": "Unit price must be positive"},
      {"table": "orders_fact", "rule": "quantity > 0", "description": "Quantity must be positive"}
    ]
  }
}
```

Build validation queries:
```sql
-- Check rule violations
SELECT COUNT(*) as violations
FROM {catalog}.{gold_schema}.{table}
WHERE NOT ({rule})
```

---

## Validation Report Format

Generate a markdown report:

```markdown
# Validation Report - {wave_name}

## Configuration
- **Catalog:** {from config.target.catalog.name}
- **Schema:** {from config.target.catalog.schemas.*}
- **Tables Validated:** {count}

## Summary
- **Status:** PASSED / FAILED
- **Tables Passed:** X/Y

## Row Count Validation

| Table | Expected | Actual | Status |
|-------|----------|--------|--------|
| {table1} | {expected} | {actual} | PASS/FAIL |
| {table2} | {expected} | {actual} | PASS/FAIL |

## Data Quality Checks

| Rule | Table | Violations | Status |
|------|-------|------------|--------|
| {rule_description} | {table} | {count} | PASS/FAIL |

## Verdict
**{APPROVED / REJECTED}**
- Reason: {if rejected}
```

---

## Example: Complete Validation Session

```
# 1. Read config
config = read_file("/memories/input/config/migration_config.json")

# 2. Extract values from config
catalog = "northwind_migration"           # from config.target.catalog.name
bronze_schema = "northwnd_bronze"         # from config.target.catalog.schemas.bronze
bronze_tables = [                         # from config.migration.bronze_tables
    {"target_table": "customers", "expected_row_count": 91},
    {"target_table": "employees", "expected_row_count": 9},
    ...
]

# 3. Validate each table
run_sql("SELECT COUNT(*) as cnt FROM northwind_migration.northwnd_bronze.customers")
# Returns: [{"cnt": "91"}]
# Expected: 91, Actual: 91 → PASS

run_sql("SELECT COUNT(*) as cnt FROM northwind_migration.northwnd_bronze.employees")
# Returns: [{"cnt": "9"}]
# Expected: 9, Actual: 9 → PASS

# ... repeat for all tables

# 4. Generate report
# All tables passed → Wave 0 APPROVED
```

---

## Key Principles

1. **NEVER hardcode** database, catalog, schema, or table names
2. **ALWAYS read config first** to get all values
3. **Use simple COUNT(*) queries** - information_schema doesn't have row counts in Databricks
4. **Compare against expected values** from config
5. **Report with evidence** - show expected vs actual for every table
