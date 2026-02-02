---
name: source-sqlserver
description: SQL Server source system analysis and extraction. Use when config.source.type is "sqlserver". Provides metadata extraction, schema analysis, data profiling, and query execution capabilities.
allowed-tools: Read, Bash
---

# SQL Server Source Skill

## When to Use

Load this skill when the migration config specifies:
```json
{
  "source": {
    "type": "sqlserver"
  }
}
```

## Capabilities

### 1. Schema Extraction
Extract complete table schemas including columns, types, constraints, and relationships.

```bash
python "{skill_dir}/scripts/get_schema.py" --table "dbo.Customers"
python "{skill_dir}/scripts/get_schema.py" --list-tables
```

### 2. Data Profiling
Profile table data quality: row counts, null percentages, distinct values.

```bash
python "{skill_dir}/scripts/profile_table.py" --table "dbo.Orders"
```

### 3. Query Execution
Run arbitrary SQL queries for validation or sampling.

```bash
python "{skill_dir}/scripts/execute_query.py" --query "SELECT TOP 10 * FROM dbo.Customers"
```

### 4. Row Counts
Get row counts for all tables in the database.

```bash
python "{skill_dir}/scripts/get_row_counts.py"
```

## Environment Variables Required

| Variable | Description |
|----------|-------------|
| `SQL_SERVER_HOST` | Server hostname or IP |
| `SQL_SERVER_PORT` | Port (default: 1433) |
| `SQL_SERVER_USER` | Username |
| `SQL_SERVER_PASSWORD` | Password |
| `SQL_SERVER_DATABASE_OLTP` | Source database name |

## Type System Reference

When mapping SQL Server types to target platforms, use the target skill's `type-mappings.json`. Common SQL Server types:

| SQL Server Type | Notes |
|-----------------|-------|
| `INT`, `BIGINT`, `SMALLINT`, `TINYINT` | Integer types |
| `VARCHAR(n)`, `NVARCHAR(n)` | Variable-length strings |
| `CHAR(n)`, `NCHAR(n)` | Fixed-length strings |
| `DECIMAL(p,s)`, `NUMERIC(p,s)` | Exact numeric |
| `MONEY`, `SMALLMONEY` | Currency types |
| `DATETIME`, `DATETIME2`, `DATE`, `TIME` | Temporal types |
| `BIT` | Boolean |
| `UNIQUEIDENTIFIER` | UUID/GUID |
| `VARBINARY`, `IMAGE` | Binary data |

## Workflow Integration

### During Planning Phase
1. Agent reads config -> source.type = "sqlserver"
2. Agent loads this skill
3. Agent runs `get_schema.py` to extract metadata
4. Agent uses schema in migration plan

### During Validation Phase
1. Agent runs `get_row_counts.py` for baseline counts
2. Agent compares with target counts after migration
3. Agent runs `execute_query.py` for spot checks

## Scripts Location

All scripts are in the `scripts/` subdirectory:
- `get_schema.py` - Extract table schema
- `get_row_counts.py` - Get all table row counts
- `execute_query.py` - Run arbitrary SQL
- `profile_table.py` - Data quality profiling

## Example Workflow

```
User: "Start migration planning"

Agent:
1. Read config: source.type = "sqlserver", target.platform = "databricks"
2. Load source-sqlserver skill (this skill)
3. Run: python scripts/get_row_counts.py
4. Run: python scripts/get_schema.py --list-tables
5. Use results in planningAgent invocation
```
