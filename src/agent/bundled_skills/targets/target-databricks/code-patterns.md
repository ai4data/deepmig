# Databricks Code Patterns

This file contains PySpark code templates for migration scripts.

## Bronze Layer Patterns

### Pattern 1: JDBC Ingestion (Full Load)

```python
"""Bronze ingestion: {source_table} -> {target_table}

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

### Pattern 2: JDBC Ingestion (Incremental)

```python
"""Bronze ingestion: {source_table} -> {target_table}

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

## Silver Layer Patterns

### Pattern 3: Silver Transformation (Cleansing)

```python
"""Silver transformation: {bronze_table} -> {silver_table}

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

### Pattern 4: Silver Join (Denormalization)

```python
"""Silver transformation: Join multiple bronze tables

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

## Gold Layer Patterns

### Pattern 5: Dimension Table (SCD Type 1)

```python
"""Gold dimension: SCD Type 1 (overwrite)

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

### Pattern 6: Dimension Table (SCD Type 2)

```python
"""Gold dimension: SCD Type 2 (history tracking)

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

    # Insert new versions for changed records
    # (Additional insert logic for changed records)
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

### Pattern 7: Fact Table

```python
"""Gold fact table: {fact_table}

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

## Utility Patterns

### Pattern 8: Data Quality Check

```python
"""Data quality validation

Table: {catalog}.{schema}.{table}
"""
from pyspark.sql import SparkSession
from pyspark.sql.functions import *

spark = SparkSession.builder.getOrCreate()

df = spark.table("{catalog}.{schema}.{table}")

# Row count
row_count = df.count()
print(f"Row count: {row_count}")

# Null check on key columns
null_keys = df.filter(col("{key_column}").isNull()).count()
print(f"Null keys: {null_keys}")

# Duplicate check
duplicate_count = df.groupBy("{key_column}").count().filter(col("count") > 1).count()
print(f"Duplicate keys: {duplicate_count}")

# Assert quality
assert null_keys == 0, f"Found {null_keys} null keys"
assert duplicate_count == 0, f"Found {duplicate_count} duplicate keys"
```

### Pattern 9: MERGE Upsert

```python
"""MERGE upsert pattern

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
