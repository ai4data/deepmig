---
name: target-databricks
description: Databricks target platform patterns and code generation. Use when config.target.platform is "databricks". Provides PySpark code patterns, Delta Lake operations, Unity Catalog conventions, and type mappings.
allowed-tools: Read, local_execute, local_shell, submit_job, run_sql
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

## Execution Tools

This skill provides access to these execution tools:

| Tool | Purpose | Runs On |
|------|---------|---------|
| `local_execute` | Run Python scripts locally | Local machine |
| `local_shell` | Run shell commands locally | Local machine |
| `submit_job` | Submit PySpark scripts to cluster | Databricks cluster |
| `run_sql` | Execute SQL queries | Databricks SQL Warehouse |

### Tool Selection Criteria

**Choose the right tool based on these criteria:**

#### Use `local_execute` when:
- The source system is **not reachable from Databricks cluster** (e.g., localhost, firewalled on-prem server without VPN/Private Link)
- The script needs **local filesystem access** (reading local files, credentials)
- The script uses **non-Spark libraries** to connect to source (pyodbc, cx_Oracle, etc.)

```
local_execute(
    script_path="/path/to/script.py",
    script_args="--config /path/to/config.json"
)
```

#### Use `submit_job` when:
- The script is **PySpark code** that runs on the cluster
- The data is **already in Databricks** (transforming bronze→silver→gold)
- The source is **reachable from cluster** (cloud database, on-prem with VPN/Private Link)
- The script uses **Spark DataFrame operations**

```
submit_job(
    script_path="/memories/scripts/transform.py",
    wait_for_completion=True
)
```

#### Use `run_sql` when:
- Running **validation queries** (row counts, data quality checks)
- Executing **DDL statements** (CREATE TABLE, ALTER TABLE)
- Running **ad-hoc SQL** queries against Databricks tables

```
run_sql("SELECT COUNT(*) as cnt FROM catalog.schema.table")
```

### Decision Flow

```
What does the script need to do?
│
├─► Read from source system
│   │
│   ├─► Source reachable from Databricks cluster?
│   │   ├─► YES → submit_job (PySpark JDBC)
│   │   └─► NO  → local_execute (local connectivity)
│   │
├─► Transform data already in Databricks
│   └─► submit_job (PySpark on cluster)
│
├─► Validate/query Databricks tables
│   └─► run_sql (SQL Warehouse)
│
└─► Run shell commands (pip, file ops)
    └─► local_shell (local machine)
```

### Tool Response Formats

**`local_execute` returns:**
```json
{
  "success": true,
  "exit_code": 0,
  "stdout": "...",
  "stderr": "",
  "message": "Script completed successfully"
}
```

**`submit_job` returns:**
```json
{
  "run_id": 12345,
  "status": "TERMINATED",
  "result_state": "SUCCESS",
  "message": "Job completed successfully"
}
```

**`run_sql` returns:**
```json
[{"column_name": "value", ...}]
```

## Quick Reference

### Table Naming Convention
```
{catalog}.{schema}.{table}
```

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

## Configuration

All credentials are read from `/memories/input/config/migration_config.json`:

```json
{
  "target": {
    "workspace_url": "https://adb-xxx.azuredatabricks.net",
    "cluster_id": "cluster-id",
    "warehouse_id": "warehouse-id"
  },
  "credentials": {
    "databricks": {
      "personal_access_token": "dapi..."
    }
  }
}
```

No environment variables needed - everything is in the config file.

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
1. Agent determines correct tool based on script requirements
2. Agent executes script using appropriate tool
3. Agent uses `run_sql` to validate results
4. Agent compares results against expected values from config
