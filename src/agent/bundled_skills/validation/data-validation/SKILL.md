---
name: data-validation
description: Validate migration results by comparing row counts and data quality between SQL Server source and Databricks target. Use after running migration scripts to verify data integrity before sign-off.
allowed-tools: Read, Bash
---

# Data Validation Skill

## When to Use
- After bronze layer ingestion to verify row counts match
- After silver/gold transformations to check data quality
- Before signing off on a migration wave
- When debugging data discrepancies

## How to Use

### Compare Row Counts

```bash
python "{skill_dir}/scripts/compare_row_counts.py" \
  --source-table "dbo.Customers" \
  --target-table "northwnd_bronze.customers"
```

### Validate All Tables in a Wave

```bash
python "{skill_dir}/scripts/validate_wave.py" \
  --config "/memories/validation/wave0_mapping.json"
```

### Sample Data Comparison

```bash
python "{skill_dir}/scripts/sample_compare.py" \
  --source-table "dbo.Orders" \
  --target-table "northwnd_bronze.orders" \
  --key-column "OrderID" \
  --sample-size 100
```

## Environment Variables Required

### SQL Server (Source)
- `SQL_SERVER_HOST`
- `SQL_SERVER_USER`
- `SQL_SERVER_PASSWORD`
- `SQL_SERVER_DATABASE_OLTP`

### Databricks (Target)
- `DATABRICKS_HOST`
- `DATABRICKS_TOKEN`
- `DATABRICKS_WAREHOUSE_ID` (for SQL queries)

## Scripts Available

| Script | Description |
|--------|-------------|
| `compare_row_counts.py` | Compare row count between source and target table |
| `validate_wave.py` | Validate all tables in a migration wave |
| `sample_compare.py` | Compare sample records between source and target |

## Validation Report Format

The scripts generate validation reports like:

```
VALIDATION REPORT - Wave 0 Bronze Layer
========================================
Table: Customers
  Source (SQL Server): 91 rows
  Target (Databricks): 91 rows
  Status: PASS

Table: Orders
  Source (SQL Server): 830 rows
  Target (Databricks): 828 rows
  Status: FAIL (2 rows missing)

Summary: 5/6 tables passed
```

## Wave Mapping File Format

Create a JSON file with source-to-target mappings:

```json
{
  "wave": "wave0",
  "layer": "bronze",
  "mappings": [
    {"source": "dbo.Customers", "target": "northwnd_bronze.customers"},
    {"source": "dbo.Orders", "target": "northwnd_bronze.orders"},
    {"source": "dbo.Products", "target": "northwnd_bronze.products"}
  ]
}
```
