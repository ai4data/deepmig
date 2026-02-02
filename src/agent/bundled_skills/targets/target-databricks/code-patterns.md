# Databricks Code Patterns

This file contains code patterns for migration scripts targeting Databricks.

---

## Pattern Selection Guide

**CRITICAL:** Before generating any code, you MUST determine the connectivity model from the migration config.

### Step 1: Detect Connectivity from Config

Read `/memories/input/config/migration_config.json` and check these fields:

```json
{
  "source": {
    "host": "...",           // Check this value
    "connectivity": "..."    // If present, use this explicitly
  }
}
```

**Connectivity Detection Rules:**

| Config Value | Connectivity | Execution Mode |
|--------------|--------------|----------------|
| `source.connectivity = "local"` | Local | **Section B** (Local Execution) |
| `source.connectivity = "direct"` | Direct JDBC | **Section A** (Cluster Execution) |
| `source.connectivity = "vpn"` or `"private_link"` | VPN/Private Link | **Section A** (Cluster Execution) |
| `source.host` = `"localhost"` or `"127.0.0.1"` or `"."` | Local (inferred) | **Section B** (Local Execution) |
| `source.host` = private IP (10.x, 172.16-31.x, 192.168.x) | Likely local/on-prem | **Section B** (unless VPN configured) |
| `source.host` = public hostname/IP | Likely direct | **Section A** (verify network access) |

### Step 2: Choose Execution Pattern

```
┌─────────────────────────────────────────────────────────────────┐
│           CONNECTIVITY DETECTION DECISION TREE                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Check: source.connectivity in config                           │
│  ├── "local" ──────────────────► LOCAL EXECUTION (Section B)   │
│  ├── "direct" / "vpn" / "private_link" ──► CLUSTER (Section A) │
│  └── not specified ──► Check source.host:                       │
│       ├── localhost/127.0.0.1/. ──► LOCAL EXECUTION (Section B)│
│       ├── private IP range ──────► LOCAL EXECUTION (Section B) │
│       └── public/cloud hostname ─► CLUSTER EXECUTION (Section A)│
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  LAYER-SPECIFIC RULES:                                          │
│  • Bronze ingestion: Use detected connectivity pattern          │
│  • Silver/Gold transforms: ALWAYS use Cluster (Section A)       │
│    (data is already in Databricks at this stage)                │
└─────────────────────────────────────────────────────────────────┘
```

### Step 3: Select Specific Pattern

**For LOCAL EXECUTION (Section B):**
- Small/medium tables (<500K rows): **Pattern B1** (INSERT batches)
- Large tables (>500K rows): **Pattern B2** (Volume upload)

**For CLUSTER EXECUTION (Section A):**
- Full load: **Pattern A1**
- Incremental load: **Pattern A2**

**For Silver/Gold (always cluster):**
- Cleansing: **Pattern A3**
- Joins: **Pattern A4**
- Dimensions: **Pattern A5/A6**
- Facts: **Pattern A7**

---

## Config File Paths

**CRITICAL:** Scripts must read config from the correct location based on where they execute.

### Config Path by Execution Mode

| Execution Mode | Config Path | Why |
|----------------|-------------|-----|
| **Local Execution** (Section B) | `/memories/input/config/migration_config.json` | `/memories/` is DeepMig's local virtual filesystem |
| **Cluster Execution** (Section A) | `/Workspace/Shared/{agent_name}/config/migration_config.json` | Config uploaded to Databricks workspace during `deepmig init` |

### How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                    deepmig init --input <path>                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. Copies input/ → ~/.deepagents/{agent}/memories/input/       │
│     └── Scripts running LOCALLY read from /memories/...        │
│                                                                 │
│  2. Uploads config to Databricks workspace:                     │
│     └── /Workspace/Shared/{agent_name}/config/migration_config.json
│     └── Scripts running ON CLUSTER read from /Workspace/...    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Cluster Script Config Pattern

**ALWAYS use this pattern for scripts that run on Databricks cluster (Section A patterns):**

```python
"""Wave N: {description}

EXECUTION: Databricks Cluster (PySpark)
"""
import json
from pyspark.sql import SparkSession

# Agent name must match the --agent used in deepmig init
AGENT_NAME = "{agent_name}"  # e.g., "northwind-migration"
CONFIG_PATH = f"/Workspace/Shared/{AGENT_NAME}/config/migration_config.json"


def load_config() -> dict:
    """Load config from Databricks workspace (for cluster execution)."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    spark = SparkSession.builder.getOrCreate()
    config = load_config()

    # Extract values from config
    catalog = config["target"]["catalog"]["name"]
    bronze_schema = config["target"]["catalog"]["schemas"]["bronze"]
    gold_schema = config["target"]["catalog"]["schemas"]["gold"]

    # ... rest of script
```

### Local Script Config Pattern

**Use this pattern for scripts that run locally (Section B patterns):**

```python
"""Wave 0: Bronze Ingestion

EXECUTION: Local machine (NOT Databricks cluster)
"""
import json

# Local execution reads from DeepMig's virtual filesystem
CONFIG_PATH = "/memories/input/config/migration_config.json"


def load_config(path: str = CONFIG_PATH) -> dict:
    """Load config from local DeepMig memories."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
```

**Note:** Local execution scripts can also accept `--config` argument to override the default path, useful for testing.

---

## Section A: Cluster Execution Patterns

These patterns run **ON a Databricks cluster** using PySpark.

**Prerequisites:**
- Databricks cluster can reach source via network (JDBC)
- SQL Server JDBC driver available on cluster
- Secrets configured in Databricks secret scope

---

### Pattern A1: JDBC Ingestion (Full Load) - Cluster

```python
"""Bronze ingestion: {source_table} -> {target_table}

EXECUTION: Databricks Cluster (NOT local)
Source: {source_database}.{source_schema}.{source_table}
Target: {catalog}.{bronze_schema}.{target_table}
Load Strategy: Full
"""
from pyspark.sql import SparkSession
from pyspark.sql.functions import current_timestamp, lit

spark = SparkSession.builder.getOrCreate()

# JDBC connection properties
jdbc_url = "jdbc:sqlserver://{host}:{port};databaseName={database}"
connection_properties = {
    "user": dbutils.secrets.get(scope="{secret_scope}", key="sql-user"),
    "password": dbutils.secrets.get(scope="{secret_scope}", key="sql-password"),
    "driver": "com.microsoft.sqlserver.jdbc.SQLServerDriver"
}

# Read from source
df = spark.read.jdbc(
    url=jdbc_url,
    table="{source_schema}.{source_table}",
    properties=connection_properties
)

# Add metadata columns
df_with_metadata = df \
    .withColumn("_ingested_at", current_timestamp()) \
    .withColumn("_source_system", lit("{source_system}"))

# Write to bronze (full overwrite)
df_with_metadata.write \
    .mode("overwrite") \
    .format("delta") \
    .option("overwriteSchema", "true") \
    .saveAsTable("{catalog}.{bronze_schema}.{target_table}")

print(f"Ingested {df_with_metadata.count()} rows to {catalog}.{bronze_schema}.{target_table}")
```

---

### Pattern A2: JDBC Ingestion (Incremental) - Cluster

```python
"""Bronze ingestion: {source_table} -> {target_table}

EXECUTION: Databricks Cluster (NOT local)
Source: {source_database}.{source_schema}.{source_table}
Target: {catalog}.{bronze_schema}.{target_table}
Load Strategy: Incremental (watermark: {watermark_column})
"""
from pyspark.sql import SparkSession
from pyspark.sql.functions import current_timestamp, lit, max as spark_max

spark = SparkSession.builder.getOrCreate()

# Get high watermark from target
try:
    last_watermark = spark.table("{catalog}.{bronze_schema}.{target_table}") \
        .agg(spark_max("{watermark_column}").alias("max_wm")) \
        .collect()[0]["max_wm"]
except:
    last_watermark = None

# Build query with watermark filter
if last_watermark:
    query = f"(SELECT * FROM {source_schema}.{source_table} WHERE {watermark_column} > '{last_watermark}') AS subq"
else:
    query = f"{source_schema}.{source_table}"

# Read incremental data
df = spark.read.jdbc(
    url=jdbc_url,
    table=query,
    properties=connection_properties
)

# Add metadata
df_with_metadata = df \
    .withColumn("_ingested_at", current_timestamp()) \
    .withColumn("_source_system", lit("{source_system}"))

# Append to bronze
df_with_metadata.write \
    .mode("append") \
    .format("delta") \
    .saveAsTable("{catalog}.{bronze_schema}.{target_table}")

print(f"Ingested {df_with_metadata.count()} incremental rows")
```

---

### Pattern A3: Silver Transformation (Cleansing) - Cluster

```python
"""Silver transformation: {bronze_table} -> {silver_table}

EXECUTION: Databricks Cluster
Source: {catalog}.{bronze_schema}.{bronze_table}
Target: {catalog}.{silver_schema}.{silver_table}
Transformations: Data cleansing, type casting, null handling
"""
from pyspark.sql import SparkSession
from pyspark.sql.functions import *

spark = SparkSession.builder.getOrCreate()

# Read from bronze
df_bronze = spark.table("{catalog}.{bronze_schema}.{bronze_table}")

# Apply transformations
df_silver = df_bronze \
    .withColumn("{column1}", trim(col("{column1}"))) \
    .withColumn("{column2}", coalesce(col("{column2}"), lit({default_value}))) \
    .withColumn("{date_column}", to_timestamp(col("{date_column}"), "{date_format}")) \
    .filter(col("{filter_column}").isNotNull()) \
    .dropDuplicates(["{key_column}"])

# Write to silver
df_silver.write \
    .mode("overwrite") \
    .format("delta") \
    .saveAsTable("{catalog}.{silver_schema}.{silver_table}")
```

---

### Pattern A4: Silver Join (Denormalization) - Cluster

```python
"""Silver transformation: Join multiple bronze tables

EXECUTION: Databricks Cluster
Sources: {bronze_tables}
Target: {catalog}.{silver_schema}.{silver_table}
"""
from pyspark.sql import SparkSession
from pyspark.sql.functions import broadcast

spark = SparkSession.builder.getOrCreate()

# Read source tables
df_main = spark.table("{catalog}.{bronze_schema}.{main_table}")
df_lookup = spark.table("{catalog}.{bronze_schema}.{lookup_table}")

# Join with broadcast for small tables (<100K rows)
df_joined = df_main.join(
    broadcast(df_lookup),
    df_main["{join_key}"] == df_lookup["{lookup_key}"],
    "left"
).select(
    df_main["*"],
    df_lookup["{lookup_column1}"],
    df_lookup["{lookup_column2}"]
)

# Write to silver
df_joined.write \
    .mode("overwrite") \
    .format("delta") \
    .saveAsTable("{catalog}.{silver_schema}.{silver_table}")
```

---

### Pattern A5: Gold Dimension (SCD Type 1) - Cluster

```python
"""Gold dimension: SCD Type 1 (overwrite)

EXECUTION: Databricks Cluster
Source: {catalog}.{silver_schema}.{source_table}
Target: {catalog}.{gold_schema}.{dim_table}
SCD Type: 1 (no history)
"""
from pyspark.sql import SparkSession
from pyspark.sql.functions import *

spark = SparkSession.builder.getOrCreate()

# Read silver source
df_source = spark.table("{catalog}.{silver_schema}.{source_table}")

# Generate surrogate key
df_dim = df_source \
    .withColumn("{dim_key}", monotonically_increasing_id()) \
    .select(
        col("{dim_key}"),
        col("{business_key}"),
        col("{attribute1}"),
        col("{attribute2}"),
        current_timestamp().alias("_updated_at")
    )

# Full overwrite (SCD Type 1)
df_dim.write \
    .mode("overwrite") \
    .format("delta") \
    .saveAsTable("{catalog}.{gold_schema}.{dim_table}")
```

---

### Pattern A6: Gold Dimension (SCD Type 2) - Cluster

```python
"""Gold dimension: SCD Type 2 (history tracking)

EXECUTION: Databricks Cluster
Source: {catalog}.{silver_schema}.{source_table}
Target: {catalog}.{gold_schema}.{dim_table}
SCD Type: 2 (maintains history)
"""
from pyspark.sql import SparkSession
from pyspark.sql.functions import *
from delta.tables import DeltaTable

spark = SparkSession.builder.getOrCreate()

# Read new data
df_new = spark.table("{catalog}.{silver_schema}.{source_table}")

# Check if target exists
if spark.catalog.tableExists("{catalog}.{gold_schema}.{dim_table}"):
    target = DeltaTable.forName(spark, "{catalog}.{gold_schema}.{dim_table}")

    # MERGE for SCD Type 2
    target.alias("target").merge(
        df_new.alias("source"),
        "target.{business_key} = source.{business_key} AND target._is_current = true"
    ).whenMatchedUpdate(
        condition="target.{hash_columns} != source.{hash_columns}",
        set={
            "_is_current": "false",
            "_end_date": "current_timestamp()"
        }
    ).whenNotMatchedInsert(
        values={
            "{business_key}": "source.{business_key}",
            "{attribute1}": "source.{attribute1}",
            "{attribute2}": "source.{attribute2}",
            "_is_current": "true",
            "_start_date": "current_timestamp()",
            "_end_date": "null"
        }
    ).execute()
else:
    # Initial load
    df_initial = df_new \
        .withColumn("_is_current", lit(True)) \
        .withColumn("_start_date", current_timestamp()) \
        .withColumn("_end_date", lit(None).cast("timestamp"))

    df_initial.write \
        .format("delta") \
        .saveAsTable("{catalog}.{gold_schema}.{dim_table}")
```

---

### Pattern A7: Gold Fact Table - Cluster

```python
"""Gold fact table: {fact_table}

EXECUTION: Databricks Cluster
Sources: {source_tables}
Target: {catalog}.{gold_schema}.{fact_table}
Grain: {grain_description}
"""
from pyspark.sql import SparkSession
from pyspark.sql.functions import *

spark = SparkSession.builder.getOrCreate()

# Read transaction data
df_transactions = spark.table("{catalog}.{silver_schema}.{transaction_table}")

# Read dimensions for surrogate keys
df_dim1 = spark.table("{catalog}.{gold_schema}.{dim1_table}") \
    .select("{dim1_key}", "{dim1_business_key}")
df_dim2 = spark.table("{catalog}.{gold_schema}.{dim2_table}") \
    .select("{dim2_key}", "{dim2_business_key}")

# Join to get surrogate keys
df_fact = df_transactions \
    .join(broadcast(df_dim1),
          df_transactions["{dim1_fk}"] == df_dim1["{dim1_business_key}"],
          "left") \
    .join(broadcast(df_dim2),
          df_transactions["{dim2_fk}"] == df_dim2["{dim2_business_key}"],
          "left") \
    .select(
        df_dim1["{dim1_key}"],
        df_dim2["{dim2_key}"],
        df_transactions["{measure1}"],
        df_transactions["{measure2}"],
        df_transactions["{date_key}"]
    )

# Write fact table
df_fact.write \
    .mode("overwrite") \
    .format("delta") \
    .partitionBy("{date_key}") \
    .saveAsTable("{catalog}.{gold_schema}.{fact_table}")
```

---

## Section B: Local Execution Patterns

These patterns run **ON THE USER'S LOCAL MACHINE** (not Databricks).

**Use when:**
- Source database is on localhost (e.g., local SQL Server)
- Source is behind firewall with no VPN/Private Link to Databricks
- No network path from Databricks cluster to source

**Prerequisites:**
- Python environment with: `pandas`, `pyodbc`, `databricks-sdk`
- ODBC driver installed (e.g., "ODBC Driver 17 for SQL Server")
- Databricks Personal Access Token (PAT)
- SQL Warehouse running in Databricks

**IMPORTANT - Library Constraints:**
```
┌─────────────────────────────────────────────────────────────────┐
│ databricks-sql-connector  │  Does NOT support file uploads     │
│                           │  No PUT command, no COPY INTO      │
│                           │  Only SQL queries                  │
├───────────────────────────┼─────────────────────────────────────┤
│ databricks-sdk            │  Full API access                   │
│ (WorkspaceClient)         │  Statement Execution API works     │
│                           │  USE THIS for local execution      │
└─────────────────────────────────────────────────────────────────┘
```

---

### Pattern B1: Local Bronze Ingestion (Full Load) - INSERT Batches

**Best for:** Small to medium tables (<500K rows)

```python
"""Bronze ingestion: Local SQL Server -> Databricks

EXECUTION: Local machine (NOT Databricks cluster)
Source: {source_database}.{source_schema}.{source_table} (localhost)
Target: {catalog}.{bronze_schema}.{target_table}
Load Strategy: Full (CREATE OR REPLACE + INSERT batches)

Prerequisites:
    pip install pandas pyodbc databricks-sdk

Usage:
    python {script_name}.py --config path/to/migration_config.json
"""
import argparse
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List

import pandas as pd
import pyodbc
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

# Configuration
DEFAULT_BATCH_SIZE = 500
STATEMENT_TIMEOUT = "300s"  # 5 minutes per statement


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# PULL: SQL Server -> pandas DataFrame
# ---------------------------------------------------------------------------

def get_sqlserver_connection(config: Dict[str, Any]) -> pyodbc.Connection:
    """Create SQL Server connection using Windows Auth or SQL Auth."""
    sql_creds = config["credentials"]["sqlserver"]
    source = config["source"]

    driver = sql_creds.get("odbc_driver", "ODBC Driver 17 for SQL Server")
    server = source.get("host", "localhost")
    database = source["databases"]["oltp"]["name"]
    auth_mode = sql_creds.get("auth_mode", "windows").lower()

    if auth_mode == "windows":
        conn_str = (
            f"DRIVER={{{driver}}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            "Trusted_Connection=yes;"
        )
    else:
        # SQL Server authentication
        username = os.environ.get("SQLSERVER_USER", sql_creds.get("username"))
        password = os.environ.get("SQLSERVER_PASSWORD", sql_creds.get("password"))
        conn_str = (
            f"DRIVER={{{driver}}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"UID={username};"
            f"PWD={password};"
        )

    logging.info("Connecting to SQL Server: %s.%s", server, database)
    return pyodbc.connect(conn_str)


def extract_table(conn: pyodbc.Connection, table_name: str) -> pd.DataFrame:
    """PULL: Extract full table from SQL Server."""
    # Handle table names with spaces
    if " " in table_name and "[" not in table_name:
        parts = table_name.split(".")
        if len(parts) == 2:
            schema, tbl = parts
            table_name = f"{schema}.[{tbl}]"
        else:
            table_name = f"[{table_name}]"

    query = f"SELECT * FROM {table_name}"
    logging.info("Extracting: %s", query)
    df = pd.read_sql(query, conn)
    logging.info("Extracted %d rows from %s", len(df), table_name)
    return df


# ---------------------------------------------------------------------------
# TRANSFORM: Add ingestion metadata
# ---------------------------------------------------------------------------

def add_ingestion_metadata(
    df: pd.DataFrame,
    source_system: str = "SQLSERVER"
) -> pd.DataFrame:
    """TRANSFORM: Add technical metadata columns."""
    df = df.copy()
    df["_ingested_at"] = datetime.utcnow().isoformat(timespec="seconds")
    df["_source_system"] = source_system
    return df


# ---------------------------------------------------------------------------
# PUSH: pandas DataFrame -> Databricks via INSERT statements
# ---------------------------------------------------------------------------

def get_databricks_client(config: Dict[str, Any]) -> WorkspaceClient:
    """Create Databricks WorkspaceClient."""
    workspace_url = config["target"]["workspace_url"]
    token = os.environ.get(
        "DATABRICKS_TOKEN",
        config["credentials"]["databricks"].get("personal_access_token")
    )
    return WorkspaceClient(host=workspace_url, token=token)


def execute_sql(
    client: WorkspaceClient,
    warehouse_id: str,
    sql: str,
    timeout: str = STATEMENT_TIMEOUT
) -> None:
    """Execute SQL statement and wait for completion."""
    stmt = client.statement_execution.execute_statement(
        warehouse_id=warehouse_id,
        statement=sql,
        wait_timeout="0s",  # Don't wait inline, poll instead
    )

    # Poll for completion
    while True:
        status = client.statement_execution.get_statement(stmt.statement_id)
        state = status.status.state

        if state == StatementState.SUCCEEDED:
            return
        elif state in (StatementState.FAILED, StatementState.CANCELED):
            error = getattr(status.status, "error", "Unknown error")
            raise RuntimeError(f"SQL failed ({state}): {error}\nSQL: {sql[:500]}")
        # Still running, continue polling


def to_sql_literal(value: Any) -> str:
    """Convert Python value to SQL literal."""
    import base64

    if value is None or pd.isna(value):
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        if pd.isna(value):  # Handle numpy nan
            return "NULL"
        return str(value)
    if isinstance(value, bytes):
        # Binary data as base64 (will be STRING in Databricks)
        return f"'{base64.b64encode(value).decode('ascii')}'"
    if hasattr(value, "isoformat"):
        return f"'{value.isoformat()}'"

    # String value - escape single quotes
    str_val = str(value)
    if str_val == "NaT":
        return "NULL"
    return f"'{str_val.replace(chr(39), chr(39)+chr(39))}'"


def get_databricks_type(dtype) -> str:
    """Map pandas dtype to Databricks SQL type."""
    dtype_str = str(dtype)
    mapping = {
        "int64": "BIGINT",
        "int32": "INT",
        "int16": "SMALLINT",
        "int8": "TINYINT",
        "float64": "DOUBLE",
        "float32": "FLOAT",
        "bool": "BOOLEAN",
        "datetime64[ns]": "TIMESTAMP",
        "object": "STRING",
    }
    return mapping.get(dtype_str, "STRING")


def generate_create_table_sql(
    full_table_name: str,
    df: pd.DataFrame,
    replace: bool = True
) -> str:
    """Generate CREATE TABLE statement from DataFrame schema."""
    column_defs = [
        f"`{col}` {get_databricks_type(dtype)}"
        for col, dtype in df.dtypes.items()
    ]
    columns_sql = ",\n    ".join(column_defs)

    create_type = "CREATE OR REPLACE TABLE" if replace else "CREATE TABLE IF NOT EXISTS"
    return f"{create_type} {full_table_name} (\n    {columns_sql}\n)"


def chunk_dataframe(df: pd.DataFrame, batch_size: int) -> Iterator[pd.DataFrame]:
    """Yield DataFrame chunks of specified size."""
    for start in range(0, len(df), batch_size):
        yield df.iloc[start:start + batch_size]


def push_to_databricks(
    client: WorkspaceClient,
    warehouse_id: str,
    df: pd.DataFrame,
    full_table_name: str,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> None:
    """PUSH: Load DataFrame to Databricks using INSERT batches."""
    if df.empty:
        logging.warning("DataFrame is empty, skipping %s", full_table_name)
        return

    # Create or replace table
    create_sql = generate_create_table_sql(full_table_name, df, replace=True)
    logging.info("Creating table: %s", full_table_name)
    execute_sql(client, warehouse_id, create_sql)

    # Insert data in batches
    columns_sql = ", ".join([f"`{col}`" for col in df.columns])
    total_rows = len(df)
    inserted = 0

    for batch_num, batch_df in enumerate(chunk_dataframe(df, batch_size), 1):
        # Build VALUES clause
        rows = []
        for _, row in batch_df.iterrows():
            values = [to_sql_literal(row[col]) for col in df.columns]
            rows.append(f"({', '.join(values)})")

        values_clause = ",\n".join(rows)
        insert_sql = f"INSERT INTO {full_table_name} ({columns_sql}) VALUES\n{values_clause}"

        logging.info(
            "Inserting batch %d (%d rows) into %s",
            batch_num, len(batch_df), full_table_name
        )
        execute_sql(client, warehouse_id, insert_sql)
        inserted += len(batch_df)

    logging.info("Loaded %d rows into %s", inserted, full_table_name)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_bronze_ingestion(config: Dict[str, Any], batch_size: int) -> None:
    """Run full bronze ingestion for all configured tables."""
    catalog = config["target"]["catalog"]["name"]
    bronze_schema = config["target"]["catalog"]["schemas"]["bronze"]
    warehouse_id = config["target"].get("warehouse_id")
    bronze_tables = config["migration"]["bronze_tables"]
    source_system = config["source"].get("name", "SQLSERVER")

    client = get_databricks_client(config)

    logging.info("Starting bronze ingestion for %d tables", len(bronze_tables))

    with get_sqlserver_connection(config) as conn:
        for table_cfg in bronze_tables:
            source_table = table_cfg["source_table"]
            target_table = table_cfg["target_table"]
            full_table_name = f"`{catalog}`.`{bronze_schema}`.`{target_table}`"

            try:
                # PULL
                df = extract_table(conn, source_table)

                # Validate row count if expected
                expected = table_cfg.get("expected_row_count")
                if expected and len(df) != expected:
                    logging.warning(
                        "Row count mismatch for %s: expected %d, got %d",
                        source_table, expected, len(df)
                    )

                # TRANSFORM
                df = add_ingestion_metadata(df, source_system)

                # PUSH
                push_to_databricks(client, warehouse_id, df, full_table_name, batch_size)

                logging.info("Completed: %s -> %s", source_table, full_table_name)

            except Exception as e:
                logging.error("Failed to ingest %s: %s", source_table, e)
                raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Local Bronze Ingestion: SQL Server -> Databricks"
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to migration_config.json",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Rows per INSERT batch (default: {DEFAULT_BATCH_SIZE})",
    )
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    config = load_config(args.config)

    # Validate config
    if config["source"]["type"] != "sqlserver":
        raise ValueError(f"Expected source.type='sqlserver', got {config['source']['type']}")
    if config["target"]["platform"] != "databricks":
        raise ValueError(f"Expected target.platform='databricks', got {config['target']['platform']}")

    run_bronze_ingestion(config, args.batch_size)
    logging.info("Bronze ingestion completed successfully")


if __name__ == "__main__":
    main()
```

---

### Pattern B2: Local Bronze Ingestion (Full Load) - Volume Upload

**Best for:** Large tables (>500K rows) where INSERT batches would be too slow.

```python
"""Bronze ingestion: Local SQL Server -> Databricks via Unity Catalog Volume

EXECUTION: Local machine (NOT Databricks cluster)
Source: {source_database}.{source_schema}.{source_table} (localhost)
Target: {catalog}.{bronze_schema}.{target_table}
Load Strategy: Full (Upload Parquet to Volume, then COPY INTO)

Prerequisites:
    pip install pandas pyodbc databricks-sdk pyarrow

This pattern:
1. Extracts data to local Parquet file
2. Uploads Parquet to Unity Catalog Volume
3. Uses COPY INTO to load into Delta table

Note: Requires Unity Catalog Volume to be pre-created:
    CREATE VOLUME IF EXISTS {catalog}.{schema}.{volume_name}
"""
import os
import tempfile
from pathlib import Path

import pandas as pd
from databricks.sdk import WorkspaceClient


def upload_to_volume_and_load(
    client: WorkspaceClient,
    warehouse_id: str,
    df: pd.DataFrame,
    catalog: str,
    schema: str,
    table_name: str,
    volume_name: str = "staging",
) -> None:
    """Upload DataFrame to Volume and load via COPY INTO."""

    # 1. Save to local Parquet
    with tempfile.TemporaryDirectory() as tmp_dir:
        local_path = Path(tmp_dir) / f"{table_name}.parquet"
        df.to_parquet(local_path, index=False)

        # 2. Upload to Unity Catalog Volume
        volume_path = f"/Volumes/{catalog}/{schema}/{volume_name}/{table_name}.parquet"

        with open(local_path, "rb") as f:
            client.files.upload(volume_path, f, overwrite=True)

        logging.info("Uploaded %s to %s", local_path.name, volume_path)

    # 3. Create table and COPY INTO
    full_table = f"`{catalog}`.`{schema}`.`{table_name}`"

    # Drop and recreate for full load
    execute_sql(client, warehouse_id, f"DROP TABLE IF EXISTS {full_table}")

    copy_sql = f"""
    CREATE TABLE {full_table}
    AS SELECT * FROM read_files(
        '{volume_path}',
        format => 'parquet'
    )
    """
    execute_sql(client, warehouse_id, copy_sql)

    logging.info("Loaded %s from Volume", full_table)


# Usage in main orchestration:
# upload_to_volume_and_load(client, warehouse_id, df, catalog, bronze_schema, target_table)
```

---

## Section C: Utility Patterns

These patterns can be used in both local and cluster execution contexts.

---

### Pattern C1: Data Quality Validation

```python
"""Data quality validation for loaded tables.

Can be executed:
- On cluster via PySpark
- Locally via databricks-sdk (SQL queries)
"""

# Cluster version (PySpark)
def validate_table_cluster(spark, full_table_name: str, expected_count: int = None):
    df = spark.table(full_table_name)

    row_count = df.count()
    print(f"Row count: {row_count}")

    if expected_count and row_count != expected_count:
        raise AssertionError(f"Expected {expected_count} rows, got {row_count}")

    # Check for nulls in key columns
    # null_count = df.filter(col("key_column").isNull()).count()

    return row_count


# Local version (databricks-sdk)
def validate_table_local(
    client: WorkspaceClient,
    warehouse_id: str,
    full_table_name: str,
    expected_count: int = None
) -> int:
    """Validate table row count via SQL."""
    stmt = client.statement_execution.execute_statement(
        warehouse_id=warehouse_id,
        statement=f"SELECT COUNT(*) as cnt FROM {full_table_name}",
        wait_timeout="30s",
    )

    # Get result
    if stmt.result and stmt.result.data_array:
        row_count = int(stmt.result.data_array[0][0])
    else:
        raise RuntimeError("Failed to get row count")

    if expected_count and row_count != expected_count:
        raise AssertionError(f"Expected {expected_count} rows, got {row_count}")

    return row_count
```

---

### Pattern C2: MERGE Upsert

```python
"""MERGE upsert pattern for incremental loads.

EXECUTION: Databricks Cluster
Target: {catalog}.{schema}.{table}
"""
from delta.tables import DeltaTable
from pyspark.sql import SparkSession

spark = SparkSession.builder.getOrCreate()

target = DeltaTable.forName(spark, "{catalog}.{schema}.{table}")

target.alias("target").merge(
    df_source.alias("source"),
    "target.{key_column} = source.{key_column}"
).whenMatchedUpdateAll() \
 .whenNotMatchedInsertAll() \
 .execute()
```

---

## Section D: Future Patterns (Placeholders)

These patterns will be added as new migration scenarios are encountered.

---

### Pattern D1: On-Premises with VPN/Private Link

**Status:** Placeholder

**Use when:** Source is on-premises but Databricks has network connectivity via VPN or Azure Private Link.

```python
# TODO: Add pattern when this scenario is encountered
# Similar to Pattern A1/A2 but with specific networking considerations:
# - Private endpoint configuration
# - Firewall rules
# - DNS resolution
```

---

### Pattern D2: Cloud-to-Cloud (AWS RDS / Azure SQL)

**Status:** Placeholder

**Use when:** Source is a cloud database (AWS RDS, Azure SQL, GCP Cloud SQL) and Databricks can reach it.

```python
# TODO: Add patterns for:
# - AWS RDS PostgreSQL -> Databricks
# - Azure SQL Database -> Databricks
# - GCP Cloud SQL -> Databricks
#
# Key differences from on-prem:
# - Connection string formats
# - Authentication (IAM roles, Managed Identity)
# - Network peering requirements
```

---

### Pattern D3: REST API Sources

**Status:** Placeholder

**Use when:** Source data comes from REST APIs (SaaS applications, internal services).

```python
# TODO: Add patterns for:
# - Paginated API extraction
# - Rate limiting handling
# - OAuth authentication
# - Incremental extraction via timestamps
#
# Example sources: Salesforce, HubSpot, internal microservices
```

---

### Pattern D4: File-Based Sources (CSV, Excel, JSON)

**Status:** Placeholder

**Use when:** Source data is in flat files.

```python
# TODO: Add patterns for:
# - Local CSV/Excel -> Databricks
# - SFTP file extraction
# - S3/ADLS file ingestion
# - Schema inference vs explicit schema
```

---

### Pattern D5: Streaming / CDC

**Status:** Placeholder

**Use when:** Real-time or near-real-time data ingestion is required.

```python
# TODO: Add patterns for:
# - Kafka -> Delta Live Tables
# - Debezium CDC -> Databricks
# - SQL Server Change Tracking
# - Event Hub / Kinesis ingestion
```

---

### Pattern D6: NoSQL Sources

**Status:** Placeholder

**Use when:** Source is a NoSQL database.

```python
# TODO: Add patterns for:
# - MongoDB -> Databricks (Spark connector)
# - Cosmos DB -> Databricks
# - DynamoDB -> Databricks
# - Handling nested/document structures
```

---

## Appendix: Common Issues and Solutions

### Issue: "PUT command not found"

**Cause:** Using `databricks-sql-connector` which only supports SQL queries, not file operations.

**Solution:** Use `databricks-sdk` with `WorkspaceClient` instead. See Pattern B1.

### Issue: "Cannot create external table from /tmp path"

**Cause:** Unity Catalog doesn't support arbitrary paths for external tables.

**Solution:** Use Unity Catalog Volumes for staging files. See Pattern B2.

### Issue: "Connection timeout to SQL Server"

**Cause:** Databricks cluster cannot reach on-premises SQL Server.

**Solution:** Use Local Execution patterns (Section B) to run from a machine that can reach the source.

### Issue: "ODBC Driver not found"

**Cause:** ODBC driver not installed on local machine.

**Solution:**
- Windows: Download and install "ODBC Driver 17 for SQL Server" from Microsoft
- Linux: `sudo apt-get install msodbcsql17` (Debian/Ubuntu)
- WSL: Same as Linux

### Issue: "INSERT batch too large"

**Cause:** Batch size too high, SQL statement exceeds limits.

**Solution:** Reduce `--batch-size` to 200-500 rows, or use Volume upload pattern (B2).
