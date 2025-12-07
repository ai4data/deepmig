---
name: target-fabric
description: Microsoft Fabric target platform patterns and code generation. Use when config.target.platform is "fabric". Provides Lakehouse/Warehouse patterns, Spark notebooks, T-SQL patterns, and type mappings.
allowed-tools: Read, Bash
---

# Microsoft Fabric Target Skill

## Status: PLACEHOLDER

This skill is planned but not yet fully implemented. The structure below describes the intended capabilities.

## When to Use

Load this skill when the migration config specifies:
```json
{
  "target": {
    "platform": "fabric"
  }
}
```

## Fabric Architecture

Microsoft Fabric offers two primary data storage options:

### 1. Lakehouse (Apache Spark + Delta Lake)
- Best for: Large-scale data processing, ETL, data science
- Language: PySpark, Spark SQL
- Storage: Delta Lake tables

### 2. Warehouse (T-SQL)
- Best for: Traditional SQL workloads, BI reporting
- Language: T-SQL
- Storage: Managed tables

## Planned Skill Contents

| File | Purpose |
|------|---------|
| `SKILL.md` | This file - overview and usage |
| `lakehouse-patterns.md` | PySpark/Spark SQL patterns for Lakehouse |
| `warehouse-patterns.md` | T-SQL patterns for Warehouse |
| `type-mappings.json` | Source-to-Fabric type mappings |
| `scripts/` | Execution scripts |

## Table Naming Convention

### Lakehouse
```
{workspace}.{lakehouse}.{schema}.{table}
```
Example: `migration_workspace.migration_lakehouse.bronze.customers`

### Warehouse
```
{workspace}.{warehouse}.{schema}.{table}
```
Example: `migration_workspace.migration_warehouse.dbo.customers`

## Planned Code Patterns

### Lakehouse Pattern (PySpark)

```python
from pyspark.sql import SparkSession
from pyspark.sql.functions import *

spark = SparkSession.builder.getOrCreate()

# Read from source
df = spark.read.format("jdbc").options(
    url="jdbc:sqlserver://...",
    dbtable="dbo.customers",
    user=mssparkutils.credentials.getSecret("keyvault", "sql-user"),
    password=mssparkutils.credentials.getSecret("keyvault", "sql-password")
).load()

# Transform
df_transformed = df.withColumn("ingested_at", current_timestamp())

# Write to Lakehouse table
df_transformed.write \
    .mode("overwrite") \
    .format("delta") \
    .saveAsTable("bronze.customers")
```

### Warehouse Pattern (T-SQL)

```sql
-- Copy into pattern
COPY INTO bronze.customers
FROM 'https://storage.blob.core.windows.net/data/customers.parquet'
WITH (
    FILE_TYPE = 'PARQUET',
    CREDENTIAL = (IDENTITY = 'Managed Identity')
);

-- Merge pattern
MERGE INTO silver.customers AS target
USING bronze.customers AS source
ON target.customer_id = source.customer_id
WHEN MATCHED THEN UPDATE SET
    target.name = source.name,
    target.updated_at = GETDATE()
WHEN NOT MATCHED THEN INSERT (customer_id, name, updated_at)
VALUES (source.customer_id, source.name, GETDATE());
```

## Medallion Architecture

```
Bronze  -> Raw ingestion (1:1 with source)
Silver  -> Cleaned, conformed
Gold    -> Aggregated, dimensional (star schema)
```

## Planned Type Mappings

| SQL Server | Fabric Lakehouse | Fabric Warehouse |
|------------|------------------|------------------|
| `INT` | `INT` | `INT` |
| `BIGINT` | `BIGINT` | `BIGINT` |
| `VARCHAR(n)` | `STRING` | `VARCHAR(n)` |
| `MONEY` | `DECIMAL(19,4)` | `DECIMAL(19,4)` |
| `DATETIME` | `TIMESTAMP` | `DATETIME2` |
| `BIT` | `BOOLEAN` | `BIT` |

## Environment Variables (Planned)

| Variable | Description |
|----------|-------------|
| `FABRIC_WORKSPACE_ID` | Workspace GUID |
| `FABRIC_LAKEHOUSE_NAME` | Lakehouse name |
| `FABRIC_WAREHOUSE_NAME` | Warehouse name |
| `FABRIC_TENANT_ID` | Azure AD tenant |

## Contributing

To implement this skill:
1. Create `lakehouse-patterns.md` with PySpark templates
2. Create `warehouse-patterns.md` with T-SQL templates
3. Create `type-mappings.json` for source systems
4. Create execution scripts using Fabric APIs
5. Test with sample migrations
