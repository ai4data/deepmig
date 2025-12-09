# Push Pattern Implementation Guide

This document details the implementation of the PUSH pattern for on-premises to Databricks migration.

## Architecture Overview

```
                    ON-PREMISES ENVIRONMENT
    ┌──────────────────────────────────────────────────────────┐
    │                                                          │
    │  ┌────────────────┐         ┌────────────────────────┐  │
    │  │                │         │                        │  │
    │  │  SQL Server    │ ODBC    │   DeepMig Agent        │  │
    │  │  ────────────  │────────►│   ──────────────       │  │
    │  │  - NORTHWND    │         │   - Extract (pyodbc)   │  │
    │  │  - NORTHWND_DWH│         │   - Transform (pandas) │  │
    │  │                │         │   - Load (SDK)         │  │
    │  └────────────────┘         │                        │  │
    │                             └───────────┬────────────┘  │
    │                                         │               │
    └─────────────────────────────────────────┼───────────────┘
                                              │
                                              │ HTTPS (443)
                                              │ Outbound Only
                                              ▼
                    AZURE / DATABRICKS
    ┌──────────────────────────────────────────────────────────┐
    │                                                          │
    │  ┌────────────────┐         ┌────────────────────────┐  │
    │  │                │         │                        │  │
    │  │  Databricks    │ REST    │   Unity Catalog        │  │
    │  │  SQL Warehouse │◄────────│   ──────────────       │  │
    │  │                │   API   │   - deepmig (catalog)  │  │
    │  │                │         │   - northwnd_bronze    │  │
    │  └────────────────┘         │   - northwnd_silver    │  │
    │                             │   - northwnd_gold      │  │
    │                             └────────────────────────┘  │
    │                                                          │
    └──────────────────────────────────────────────────────────┘
```

## Components

### 1. On-Premises Components

| Component | Purpose | Technology |
|-----------|---------|------------|
| Source Database | Data origin | SQL Server, Oracle, PostgreSQL |
| ODBC Driver | Local connectivity | ODBC Driver 17 for SQL Server |
| Migration Agent | Extract & Push | Python + pyodbc + databricks-sdk |

### 2. Cloud Components

| Component | Purpose | Technology |
|-----------|---------|------------|
| SQL Warehouse | Execute statements | Databricks SQL |
| Unity Catalog | Data governance | Catalog > Schema > Table |
| Delta Lake | Storage format | Delta tables with ACID |

---

## Data Flow

### Initial Load (Historical Data)

```
┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
│ Extract │───►│Transform│───►│ Batch   │───►│ Upload  │───►│ Verify  │
│ Full    │    │ Types   │    │ Prepare │    │ to DBX  │    │ Counts  │
│ Tables  │    │         │    │         │    │         │    │         │
└─────────┘    └─────────┘    └─────────┘    └─────────┘    └─────────┘
     │                             │              │
     ▼                             ▼              ▼
 SELECT *                    100 rows/batch   INSERT INTO
 FROM table                                   via SQL API
```

### Incremental Load (Daily Sync)

```
┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
│ Get Last│───►│ Extract │───►│ Merge   │───►│ Update  │───►│ Update  │
│ Sync TS │    │ Delta   │    │ Logic   │    │ Tables  │    │ Sync TS │
│         │    │         │    │         │    │         │    │         │
└─────────┘    └─────────┘    └─────────┘    └─────────┘    └─────────┘
     │              │              │              │
     ▼              ▼              ▼              ▼
 SELECT MAX     WHERE          MERGE INTO    Store new
 (modified_at)  modified_at >  ... WHEN      timestamp
 FROM bronze    @last_sync     MATCHED
```

---

## Implementation Code Structure

```
migration_scripts/
├── config/
│   └── migration_config.py      # Connection settings
├── bronze/
│   ├── initial_load.py          # Full historical load
│   └── incremental_load.py      # Daily delta sync
├── silver/
│   └── transform_to_silver.py   # Business transformations
├── gold/
│   └── create_gold_views.py     # Analytics-ready views
└── utils/
    ├── db_utils.py              # Database helpers
    └── databricks_utils.py      # Databricks SDK helpers
```

---

## Code Examples

### Extract from SQL Server (Local)

```python
import pyodbc
import pandas as pd

def extract_table(table_name: str, incremental_col: str = None, last_value=None):
    """Extract table from local SQL Server."""
    conn_str = (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=localhost;"
        "DATABASE=NORTHWND;"
        "Trusted_Connection=yes;"
    )

    conn = pyodbc.connect(conn_str)

    if incremental_col and last_value:
        query = f"""
            SELECT * FROM {table_name}
            WHERE {incremental_col} > ?
        """
        df = pd.read_sql(query, conn, params=[last_value])
    else:
        query = f"SELECT * FROM {table_name}"
        df = pd.read_sql(query, conn)

    conn.close()
    return df
```

### Push to Databricks (REST API)

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

def push_to_databricks(df: pd.DataFrame, target_table: str, warehouse_id: str):
    """Push DataFrame to Databricks via SQL Statement Execution API."""

    client = WorkspaceClient(
        host="https://adb-xxx.azuredatabricks.net",
        token="dapi..."
    )

    # Create table if not exists
    columns_ddl = ", ".join([
        f"`{col}` STRING" for col in df.columns
    ])

    create_sql = f"""
        CREATE TABLE IF NOT EXISTS {target_table}
        ({columns_ddl})
        USING DELTA
    """

    client.statement_execution.execute_statement(
        warehouse_id=warehouse_id,
        statement=create_sql,
        wait_timeout="30s"
    )

    # Insert in batches
    batch_size = 100
    for i in range(0, len(df), batch_size):
        batch = df.iloc[i:i+batch_size]
        values = batch_to_sql_values(batch)

        insert_sql = f"INSERT INTO {target_table} VALUES {values}"

        response = client.statement_execution.execute_statement(
            warehouse_id=warehouse_id,
            statement=insert_sql,
            wait_timeout="60s"
        )

        if response.status.state != StatementState.SUCCEEDED:
            raise Exception(f"Insert failed: {response.status}")
```

### Incremental Sync Pattern

```python
def sync_table_incremental(
    table_name: str,
    target_table: str,
    timestamp_col: str,
    warehouse_id: str
):
    """Sync only new/changed records."""

    client = WorkspaceClient(...)

    # 1. Get last sync timestamp from Databricks
    result = client.statement_execution.execute_statement(
        warehouse_id=warehouse_id,
        statement=f"SELECT MAX({timestamp_col}) FROM {target_table}",
        wait_timeout="30s"
    )
    last_sync = parse_result(result)

    # 2. Extract delta from source
    df = extract_table(table_name, timestamp_col, last_sync)

    if df.empty:
        print(f"No new records for {table_name}")
        return

    # 3. Merge into target (upsert)
    # For simplicity, using DELETE + INSERT; production would use MERGE
    push_to_databricks(df, target_table, warehouse_id)

    print(f"Synced {len(df)} records to {target_table}")
```

---

## Scheduling Options

### Demo/POC: Manual or Simple Scheduler

```bash
# Windows Task Scheduler
python migrate_northwind_to_bronze.py

# Linux cron (WSL)
0 2 * * * cd /path/to/scripts && python migrate_northwind_to_bronze.py
```

### Production: Orchestrated

| Option | Complexity | Features |
|--------|------------|----------|
| Windows Task Scheduler | Low | Basic scheduling |
| Apache Airflow (on-prem) | Medium | DAGs, monitoring, retries |
| Azure Data Factory | Medium | Managed, triggers, monitoring |
| Databricks Workflows | Medium | Native, but needs network access |
| Prefect/Dagster | Medium | Modern orchestration |

---

## Security Considerations

### Credentials Management

```python
# DON'T: Hardcode credentials
token = "dapi123..."  # Bad!

# DO: Use environment variables
import os
token = os.environ.get("DATABRICKS_TOKEN")

# DO: Use secret managers
from azure.keyvault.secrets import SecretClient
client = SecretClient(vault_url="https://myvault.vault.azure.net")
token = client.get_secret("databricks-token").value
```

### Network Security

- **Outbound only**: Push pattern requires only HTTPS outbound (port 443)
- **No inbound**: No need to expose SQL Server to internet
- **Firewall friendly**: Works with standard corporate firewalls
- **Token-based auth**: Databricks Personal Access Token or Service Principal

---

## Error Handling & Resilience

```python
import time
from functools import wraps

def retry_with_backoff(max_retries=3, backoff_factor=2):
    """Decorator for retry logic with exponential backoff."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    wait = backoff_factor ** attempt
                    print(f"Attempt {attempt + 1} failed: {e}. Retrying in {wait}s...")
                    time.sleep(wait)
        return wrapper
    return decorator

@retry_with_backoff(max_retries=3)
def push_batch(client, warehouse_id, sql):
    """Push with automatic retry."""
    return client.statement_execution.execute_statement(
        warehouse_id=warehouse_id,
        statement=sql,
        wait_timeout="60s"
    )
```

---

## Monitoring & Observability

### Logging

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('migration.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def migrate_table(table_name):
    logger.info(f"Starting migration: {table_name}")
    try:
        df = extract_table(table_name)
        logger.info(f"Extracted {len(df)} rows from {table_name}")
        push_to_databricks(df, f"bronze.{table_name}")
        logger.info(f"Successfully migrated {table_name}")
    except Exception as e:
        logger.error(f"Migration failed for {table_name}: {e}")
        raise
```

### Metrics to Track

| Metric | Description |
|--------|-------------|
| `rows_extracted` | Records read from source |
| `rows_loaded` | Records written to Databricks |
| `sync_duration_seconds` | Time for full sync |
| `last_sync_timestamp` | When last sync completed |
| `errors_count` | Number of failed operations |

---

## Next Steps for DeepMig

1. **Update prompts** to generate push-pattern scripts for on-prem sources
2. **Add incremental sync** templates with CDC/timestamp support
3. **Generate scheduling** configurations (cron, Task Scheduler, Airflow DAGs)
4. **Include monitoring** setup in generated scripts
