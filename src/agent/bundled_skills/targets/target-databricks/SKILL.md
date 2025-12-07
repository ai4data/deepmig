---
name: target-databricks
description: Databricks target platform patterns and code generation. Use when config.target.platform is "databricks". Provides PySpark code patterns, Delta Lake operations, Unity Catalog conventions, and type mappings.
allowed-tools: Read, Bash
---

# Databricks Target Skill

## When to Use

Load this skill when the migration config specifies:
```json
{
  "target": {
    "platform": "databricks"
  }
}
```

## Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | This file - overview and usage |
| `code-patterns.md` | PySpark code templates and patterns |
| `type-mappings.json` | Source-to-Databricks type mappings |
| `scripts/` | Execution scripts (use databricks-execution skill) |

## Quick Reference

### Table Naming Convention
```
{catalog}.{schema}.{table}
```
Example: `northwind_migration.northwnd_bronze.customers`

### Medallion Architecture
```
Bronze  -> Raw ingestion (1:1 with source)
Silver  -> Cleaned, conformed (business keys)
Gold    -> Aggregated, dimensional (star schema)
```

### Code Template Structure
```python
from pyspark.sql import SparkSession
from pyspark.sql.functions import *

spark = SparkSession.builder.getOrCreate()

# Read source
df = spark.read.format("jdbc").options(...).load()

# Transform
df_transformed = df.withColumn(...)

# Write to Delta
df_transformed.write.mode("overwrite").format("delta").saveAsTable("catalog.schema.table")
```

## Code Patterns

See `code-patterns.md` for complete templates:
- Bronze ingestion patterns
- Silver transformation patterns
- Gold aggregation patterns
- SCD Type 1 and Type 2 patterns
- Join optimization (broadcast hints)

## Type Mappings

See `type-mappings.json` for source-to-Databricks mappings.

Example (SQL Server -> Databricks):
```json
{
  "VARCHAR": "STRING",
  "MONEY": "DECIMAL(19,4)",
  "DATETIME": "TIMESTAMP",
  "BIT": "BOOLEAN"
}
```

## Execution

For running scripts on Databricks, use the scripts in this skill's `scripts/` directory:

```bash
python "{skill_dir}/scripts/submit_job.py" \
  --script "/path/to/script.py" \
  --cluster-id "$DATABRICKS_CLUSTER_ID"
```

### Available Execution Scripts

| Script | Description |
|--------|-------------|
| `submit_job.py` | Submit a Python script to Databricks Jobs API |
| `get_run_status.py` | Check the status of a running job |
| `upload_to_dbfs.py` | Upload a file to DBFS storage |

## Environment Variables Required

| Variable | Description |
|----------|-------------|
| `DATABRICKS_HOST` | Workspace URL |
| `DATABRICKS_TOKEN` | Personal access token |
| `DATABRICKS_CLUSTER_ID` | Cluster for job execution |
| `DATABRICKS_WAREHOUSE_ID` | SQL warehouse for queries |

## Best Practices

### 1. Delta Lake Operations
- Always use `MERGE` for upserts (not DELETE + INSERT)
- Enable auto-optimize: `delta.autoOptimize.optimizeWrite = true`
- Use Z-ORDER on frequently filtered columns

### 2. Performance
- Broadcast small dimension tables (<100K rows)
- Use `coalesce()` for small output files
- Avoid UDFs when built-in functions exist

### 3. Data Quality
- Use Delta Lake constraints for data validation
- Implement CHECK constraints on important columns
- Use NOT NULL where business rules require

## Workflow Integration

### During Code Generation
1. Agent reads config -> target.platform = "databricks"
2. Agent loads this skill
3. Agent reads `code-patterns.md` for templates
4. Agent reads `type-mappings.json` for type conversion
5. Agent generates PySpark code using patterns

### During Validation
1. Agent uses this skill's `scripts/submit_job.py` to submit jobs
2. Agent uses `validation/data-validation` skill to compare counts
