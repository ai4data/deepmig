---
name: target-snowflake
description: Snowflake target platform patterns and code generation. Use when config.target.platform is "snowflake". Provides Snowpark Python patterns, SQL patterns, warehouse conventions, and type mappings.
allowed-tools: Read, Bash
---

# Snowflake Target Skill

## Status: PLACEHOLDER

This skill is planned but not yet fully implemented. The structure below describes the intended capabilities.

## When to Use

Load this skill when the migration config specifies:
```json
{
  "target": {
    "platform": "snowflake"
  }
}
```

## Planned Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | This file - overview and usage |
| `code-patterns.md` | Snowpark/SQL code templates |
| `type-mappings.json` | Source-to-Snowflake type mappings |
| `scripts/` | Execution scripts |

## Table Naming Convention

```
{database}.{schema}.{table}
```
Example: `MIGRATION_DB.BRONZE.CUSTOMERS`

## Medallion Architecture

```
RAW     -> Raw ingestion (staging)
BRONZE  -> Cleansed, typed
SILVER  -> Conformed, business rules
GOLD    -> Aggregated, dimensional
```

## Planned Code Patterns

### Snowpark Python Pattern

```python
from snowflake.snowpark import Session
from snowflake.snowpark.functions import col, lit, when

# Connection
connection_parameters = {
    "account": "xy12345.us-east-1",
    "user": "migration_user",
    "password": "...",
    "warehouse": "COMPUTE_WH",
    "database": "MIGRATION_DB",
    "schema": "BRONZE",
    "role": "TRANSFORMER"
}

session = Session.builder.configs(connection_parameters).create()

# Read
df = session.table("source_table")

# Transform
df_transformed = df.with_column("new_col", col("old_col") * 2)

# Write
df_transformed.write.mode("overwrite").save_as_table("target_table")
```

### SQL Pattern

```sql
-- Merge pattern (upsert)
MERGE INTO target_table t
USING source_table s
ON t.id = s.id
WHEN MATCHED THEN UPDATE SET t.col1 = s.col1
WHEN NOT MATCHED THEN INSERT (id, col1) VALUES (s.id, s.col1);
```

## Planned Type Mappings

| SQL Server | Snowflake |
|------------|-----------|
| `INT` | `INTEGER` |
| `BIGINT` | `BIGINT` |
| `VARCHAR(n)` | `VARCHAR(n)` |
| `MONEY` | `NUMBER(19,4)` |
| `DATETIME` | `TIMESTAMP_NTZ` |
| `BIT` | `BOOLEAN` |

## Environment Variables (Planned)

| Variable | Description |
|----------|-------------|
| `SNOWFLAKE_ACCOUNT` | Account identifier |
| `SNOWFLAKE_USER` | Username |
| `SNOWFLAKE_PASSWORD` | Password |
| `SNOWFLAKE_WAREHOUSE` | Compute warehouse |
| `SNOWFLAKE_DATABASE` | Default database |
| `SNOWFLAKE_SCHEMA` | Default schema |
| `SNOWFLAKE_ROLE` | Role to use |

## Contributing

To implement this skill:
1. Create `code-patterns.md` with Snowpark and SQL templates
2. Create `type-mappings.json` for source systems
3. Create execution scripts (submit_query.py, etc.)
4. Test with sample migrations
