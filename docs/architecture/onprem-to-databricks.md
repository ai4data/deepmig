# On-Premises to Databricks Migration Architecture

This document describes the architectural approaches for migrating data from on-premises databases to Databricks, covering both demo/POC and enterprise-ready solutions.

## The Core Challenge

When migrating from on-premises databases to Databricks (running in Azure/AWS/GCP), the primary challenge is **network connectivity**:

```
┌─────────────────────┐                        ┌─────────────────────┐
│   ON-PREMISES       │         ???            │      CLOUD          │
│   ─────────────     │                        │   ─────────────     │
│   SQL Server        │  ◄── No direct path ──►│   Databricks        │
│   Oracle            │                        │   (Azure/AWS/GCP)   │
│   PostgreSQL        │                        │                     │
└─────────────────────┘                        └─────────────────────┘
```

**Key insight:** Databricks clusters cannot reach `localhost` or private on-prem IPs without explicit network configuration.

---

## Two Architectural Patterns

### Pattern 1: PULL (Databricks pulls from source)

```
┌─────────────────────┐                        ┌─────────────────────┐
│   ON-PREMISES       │                        │      CLOUD          │
│                     │                        │                     │
│   ┌─────────────┐   │    JDBC/Network        │   ┌─────────────┐   │
│   │ SQL Server  │◄──┼────────────────────────┼───│ Databricks  │   │
│   └─────────────┘   │                        │   │ Cluster     │   │
│                     │                        │   └─────────────┘   │
└─────────────────────┘                        └─────────────────────┘

Requires: VPN, ExpressRoute, or public exposure
```

**Pros:**
- Databricks manages the extraction
- Can leverage Spark's distributed reading
- Native JDBC connector support

**Cons:**
- Requires network infrastructure (VPN/ExpressRoute)
- Security concerns with exposing databases
- Complex firewall configuration

---

### Pattern 2: PUSH (On-prem pushes to Databricks) ✅ Recommended

```
┌─────────────────────────────────────────────┐
│   ON-PREMISES                               │
│                                             │
│   ┌─────────────┐    ┌─────────────────┐   │      ┌─────────────────┐
│   │ SQL Server  │───►│ Migration Agent │───┼─────►│   Databricks    │
│   └─────────────┘    │ (runs locally)  │   │      │   (REST API)    │
│                      └─────────────────┘   │      └─────────────────┘
│                                             │
└─────────────────────────────────────────────┘

Requires: Only outbound HTTPS (443) - usually allowed
```

**Pros:**
- No inbound network access needed
- Works behind firewalls immediately
- Simpler security model (outbound only)
- Agent runs where data lives

**Cons:**
- Requires local compute resources
- Need to manage/schedule the agent

---

## Implementation Approaches

### Demo/POC: Local Python Script

For demos and proof-of-concept, use a simple Python script that:
1. Connects to local SQL Server via ODBC
2. Extracts data to pandas DataFrames
3. Pushes to Databricks via SDK/REST API

```
┌────────────────────────────────────────────────────────────────┐
│  Developer Machine / On-Prem Server                            │
│                                                                │
│  ┌──────────────┐    ┌──────────────────────────────────────┐ │
│  │ SQL Server   │    │  migrate_to_bronze.py                │ │
│  │ (localhost)  │───►│                                      │ │
│  │              │    │  1. pyodbc.connect(localhost)        │ │
│  └──────────────┘    │  2. pd.read_sql(query)               │──┼──► Databricks
│                      │  3. databricks.sdk.WorkspaceClient   │ │    (REST API)
│                      │  4. statement_execution.execute()    │ │
│                      └──────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────┘
```

**Components:**
- `pyodbc` - Local SQL Server connection
- `pandas` - Data extraction and transformation
- `databricks-sdk` - Push data via Databricks SQL Statement Execution API

**Example flow:**
```python
# 1. Extract locally
conn = pyodbc.connect("DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost;...")
df = pd.read_sql("SELECT * FROM Customers", conn)

# 2. Push to Databricks
client = WorkspaceClient(host="https://xxx.azuredatabricks.net", token="...")
client.statement_execution.execute_statement(
    warehouse_id="...",
    statement=f"INSERT INTO catalog.schema.customers VALUES ..."
)
```

**Best for:**
- Demos and POCs
- Small to medium datasets (< 1M rows per table)
- Quick validation of migration logic

---

### Enterprise: Azure Data Factory + Self-Hosted Integration Runtime

For production workloads, use Azure Data Factory with a Self-Hosted Integration Runtime:

```
┌─────────────────────────────────────────────┐      ┌─────────────────────────┐
│   ON-PREMISES NETWORK                       │      │   AZURE                 │
│                                             │      │                         │
│   ┌─────────────┐    ┌─────────────────┐   │      │   ┌─────────────────┐   │
│   │ SQL Server  │───►│ Self-Hosted IR  │───┼──────┼──►│ Azure Data      │   │
│   │             │    │ (Windows VM)    │   │      │   │ Factory         │   │
│   └─────────────┘    └─────────────────┘   │      │   └────────┬────────┘   │
│                                             │      │            │            │
│   ┌─────────────┐                          │      │            ▼            │
│   │ Oracle      │───────────────────────────┼──────┼──► ┌─────────────────┐ │
│   └─────────────┘                          │      │    │ Databricks      │ │
│                                             │      │    │ (Delta Lake)    │ │
└─────────────────────────────────────────────┘      │    └─────────────────┘ │
                                                     └─────────────────────────┘
```

**Components:**
- **Self-Hosted Integration Runtime**: Windows service running on-prem
- **Azure Data Factory**: Orchestration and scheduling
- **Copy Activity**: Moves data from source to sink
- **Databricks Linked Service**: Connection to Databricks workspace

**Benefits:**
- Enterprise security (managed identity, key vault)
- Built-in monitoring and alerting
- Scalable parallelism
- Change Data Capture (CDC) support
- Incremental loading patterns

**Setup steps:**
1. Install Self-Hosted IR on an on-prem Windows machine
2. Register IR with Azure Data Factory
3. Create linked services for SQL Server (via IR) and Databricks
4. Build pipelines with Copy activities
5. Schedule with triggers (daily, hourly, event-based)

---

### Enterprise: Databricks + On-Prem Agent

Alternative pattern using Databricks-native tooling:

```
┌─────────────────────────────────────────────┐      ┌─────────────────────────┐
│   ON-PREMISES                               │      │   AZURE                 │
│                                             │      │                         │
│   ┌─────────────┐    ┌─────────────────┐   │      │   ┌─────────────────┐   │
│   │ SQL Server  │───►│ Databricks      │───┼──────┼──►│ Unity Catalog   │   │
│   │             │    │ Connect Agent   │   │      │   │ Volumes         │   │
│   └─────────────┘    │ (Spark local)   │   │      │   └────────┬────────┘   │
│                      └─────────────────┘   │      │            │            │
│                                             │      │            ▼            │
│                                             │      │   ┌─────────────────┐   │
│                                             │      │   │ Delta Tables    │   │
│                                             │      │   │ (Bronze/Silver) │   │
│                                             │      │   └─────────────────┘   │
└─────────────────────────────────────────────┘      └─────────────────────────┘
```

**Components:**
- **Databricks Connect**: Run Spark locally, execute on cluster
- **Unity Catalog Volumes**: Land files in cloud storage
- **Auto Loader**: Incrementally process landed files

---

### Enterprise: Partner Solutions

Managed ETL/ELT platforms with built-in on-prem connectors:

| Solution | On-Prem Agent | Databricks Integration |
|----------|---------------|------------------------|
| **Fivetran** | HVR/On-prem connector | Native Databricks destination |
| **Airbyte** | Self-hosted or agent | Databricks destination |
| **Matillion** | Agent-based | Native Databricks support |
| **Informatica** | Secure Agent | PowerCenter/IDMC |
| **Talend** | Remote Engine | Databricks components |

---

## Incremental/CDC Patterns

For daily syncs after initial migration:

### Pattern A: Timestamp-based incremental

```sql
-- Track last sync
SELECT MAX(ModifiedDate) FROM bronze.customers

-- Extract only new/changed records
SELECT * FROM Customers WHERE ModifiedDate > @last_sync
```

### Pattern B: Change Data Capture (CDC)

```sql
-- Enable CDC on source
EXEC sys.sp_cdc_enable_table @source_schema = 'dbo', @source_name = 'Customers'

-- Read changes
SELECT * FROM cdc.dbo_Customers_CT WHERE __$start_lsn > @last_lsn
```

### Pattern C: Change Tracking

```sql
-- Enable change tracking
ALTER DATABASE NORTHWND SET CHANGE_TRACKING = ON

-- Get changes since last sync
SELECT * FROM CHANGETABLE(CHANGES Customers, @last_version) AS CT
JOIN Customers C ON CT.CustomerID = C.CustomerID
```

---

## Recommendation Summary

| Scenario | Recommended Approach |
|----------|---------------------|
| **Demo/POC** | Local Python script with databricks-sdk |
| **Small business** | Python script + Windows Task Scheduler |
| **Mid-size enterprise** | Azure Data Factory + Self-Hosted IR |
| **Large enterprise** | ADF + CDC + Delta Live Tables |
| **Multi-cloud** | Partner solution (Fivetran, Airbyte) |

---

## DeepMig Implementation

DeepMig generates migration scripts using the **PUSH pattern** for on-prem sources:

1. **Detection**: Identifies `localhost` or private IPs as on-prem sources
2. **Script Generation**: Creates Python scripts that run locally
3. **SDK Usage**: Uses `databricks-sdk` for cloud communication
4. **Incremental Support**: Generates CDC/timestamp-based sync logic

This ensures generated scripts work immediately without requiring network infrastructure changes.
