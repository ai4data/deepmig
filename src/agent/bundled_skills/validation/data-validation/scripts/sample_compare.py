#!/usr/bin/env python3
"""Compare sample records between SQL Server source and Databricks target.

Usage:
    python sample_compare.py --source-table "dbo.Orders" --target-table "northwnd_bronze.orders" --key-column "OrderID" --sample-size 100

Environment Variables Required:
    SQL Server:
        SQL_SERVER_HOST, SQL_SERVER_USER, SQL_SERVER_PASSWORD, SQL_SERVER_DATABASE_OLTP
    Databricks:
        DATABRICKS_HOST, DATABRICKS_TOKEN, DATABRICKS_WAREHOUSE_ID
"""
import os
import sys
import argparse
import json

try:
    import pyodbc
except ImportError:
    print("ERROR: 'pyodbc' package not installed. Run: pip install pyodbc")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("ERROR: 'requests' package not installed. Run: pip install requests")
    sys.exit(1)


def get_sql_server_config() -> dict:
    """Get SQL Server connection config from environment."""
    config = {
        "host": os.environ.get("SQL_SERVER_HOST"),
        "user": os.environ.get("SQL_SERVER_USER"),
        "password": os.environ.get("SQL_SERVER_PASSWORD"),
        "database": os.environ.get("SQL_SERVER_DATABASE_OLTP"),
    }

    missing = [k for k, v in config.items() if not v]
    if missing:
        print(f"ERROR: Missing SQL Server environment variables: {missing}")
        sys.exit(1)

    return config


def get_databricks_config() -> dict:
    """Get Databricks connection config from environment."""
    config = {
        "host": os.environ.get("DATABRICKS_HOST"),
        "token": os.environ.get("DATABRICKS_TOKEN"),
        "warehouse_id": os.environ.get("DATABRICKS_WAREHOUSE_ID"),
    }

    missing = [k for k, v in config.items() if not v]
    if missing:
        print(f"ERROR: Missing Databricks environment variables: {missing}")
        sys.exit(1)

    config["host"] = config["host"].rstrip("/")
    return config


def get_source_sample(config: dict, table_name: str, key_column: str, sample_size: int) -> list:
    """Get sample records from SQL Server source table."""
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={config['host']};"
        f"DATABASE={config['database']};"
        f"UID={config['user']};"
        f"PWD={config['password']}"
    )

    try:
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        # Get column names
        cursor.execute(f"SELECT TOP 1 * FROM {table_name}")
        columns = [desc[0] for desc in cursor.description]

        # Get sample records
        cursor.execute(f"SELECT TOP {sample_size} * FROM {table_name} ORDER BY {key_column}")
        rows = cursor.fetchall()
        conn.close()

        # Convert to list of dicts
        return [dict(zip(columns, [str(v) if v is not None else None for v in row])) for row in rows]

    except Exception as e:
        print(f"ERROR: Failed to query SQL Server: {e}")
        sys.exit(1)


def get_target_sample(config: dict, table_name: str, key_column: str, sample_size: int) -> list:
    """Get sample records from Databricks target table."""
    response = requests.post(
        f"{config['host']}/api/2.0/sql/statements",
        headers={"Authorization": f"Bearer {config['token']}"},
        json={
            "warehouse_id": config["warehouse_id"],
            "statement": f"SELECT * FROM {table_name} ORDER BY {key_column} LIMIT {sample_size}",
            "wait_timeout": "60s"
        }
    )

    if response.status_code != 200:
        print(f"ERROR: Failed to query Databricks: {response.text}")
        sys.exit(1)

    result = response.json()
    status = result.get("status", {}).get("state")

    if status != "SUCCEEDED":
        print(f"ERROR: Query failed with status: {status}")
        if "error" in result.get("status", {}):
            print(f"  Error: {result['status']['error']['message']}")
        sys.exit(1)

    # Extract data
    schema = result.get("manifest", {}).get("schema", {}).get("columns", [])
    columns = [col["name"] for col in schema]
    data = result.get("result", {}).get("data_array", [])

    return [dict(zip(columns, row)) for row in data]


def compare_records(source_records: list, target_records: list, key_column: str) -> dict:
    """Compare records and return differences."""
    # Index by key
    source_by_key = {r.get(key_column) or r.get(key_column.lower()): r for r in source_records}
    target_by_key = {r.get(key_column) or r.get(key_column.lower()): r for r in target_records}

    source_keys = set(source_by_key.keys())
    target_keys = set(target_by_key.keys())

    missing_in_target = source_keys - target_keys
    extra_in_target = target_keys - source_keys
    common_keys = source_keys & target_keys

    # Compare common records
    mismatches = []
    for key in common_keys:
        source_rec = source_by_key[key]
        target_rec = target_by_key[key]

        # Normalize keys to lowercase for comparison
        source_norm = {k.lower(): v for k, v in source_rec.items()}
        target_norm = {k.lower(): v for k, v in target_rec.items()}

        # Compare each field
        diffs = []
        all_keys = set(source_norm.keys()) | set(target_norm.keys())

        for field in all_keys:
            # Skip metadata columns
            if field in ("_rescued_data", "ingested_at", "source_file"):
                continue

            source_val = str(source_norm.get(field, "")) if source_norm.get(field) is not None else None
            target_val = str(target_norm.get(field, "")) if target_norm.get(field) is not None else None

            if source_val != target_val:
                diffs.append({
                    "field": field,
                    "source": source_val,
                    "target": target_val
                })

        if diffs:
            mismatches.append({"key": key, "differences": diffs})

    return {
        "missing_in_target": list(missing_in_target),
        "extra_in_target": list(extra_in_target),
        "mismatches": mismatches,
        "matched": len(common_keys) - len(mismatches)
    }


def main():
    parser = argparse.ArgumentParser(description="Compare sample records between source and target")
    parser.add_argument("--source-table", required=True, help="Source table name (e.g., dbo.Orders)")
    parser.add_argument("--target-table", required=True, help="Target table name (e.g., northwnd_bronze.orders)")
    parser.add_argument("--key-column", required=True, help="Primary key column for matching records")
    parser.add_argument("--sample-size", type=int, default=100, help="Number of records to compare (default: 100)")
    args = parser.parse_args()

    print(f"Comparing sample records...")
    print(f"  Source: {args.source_table}")
    print(f"  Target: {args.target_table}")
    print(f"  Key: {args.key_column}")
    print(f"  Sample size: {args.sample_size}")
    print()

    # Get configs
    sql_config = get_sql_server_config()
    dbx_config = get_databricks_config()

    # Get samples
    print("Fetching source records...")
    source_records = get_source_sample(sql_config, args.source_table, args.key_column, args.sample_size)
    print(f"  Retrieved {len(source_records)} source records")

    print("Fetching target records...")
    target_records = get_target_sample(dbx_config, args.target_table, args.key_column, args.sample_size)
    print(f"  Retrieved {len(target_records)} target records")
    print()

    # Compare
    result = compare_records(source_records, target_records, args.key_column)

    # Report
    print("=" * 50)
    print("SAMPLE COMPARISON RESULTS")
    print("=" * 50)
    print()

    print(f"Records matched: {result['matched']}")

    if result["missing_in_target"]:
        print(f"\nMissing in target ({len(result['missing_in_target'])}):")
        for key in result["missing_in_target"][:10]:
            print(f"  - {args.key_column}={key}")
        if len(result["missing_in_target"]) > 10:
            print(f"  ... and {len(result['missing_in_target']) - 10} more")

    if result["extra_in_target"]:
        print(f"\nExtra in target ({len(result['extra_in_target'])}):")
        for key in result["extra_in_target"][:10]:
            print(f"  - {args.key_column}={key}")
        if len(result["extra_in_target"]) > 10:
            print(f"  ... and {len(result['extra_in_target']) - 10} more")

    if result["mismatches"]:
        print(f"\nField mismatches ({len(result['mismatches'])} records):")
        for mismatch in result["mismatches"][:5]:
            print(f"\n  {args.key_column}={mismatch['key']}:")
            for diff in mismatch["differences"][:3]:
                print(f"    {diff['field']}: '{diff['source']}' -> '{diff['target']}'")
            if len(mismatch["differences"]) > 3:
                print(f"    ... and {len(mismatch['differences']) - 3} more fields")
        if len(result["mismatches"]) > 5:
            print(f"\n  ... and {len(result['mismatches']) - 5} more records with mismatches")

    # Summary
    print()
    print("-" * 50)
    total_issues = len(result["missing_in_target"]) + len(result["extra_in_target"]) + len(result["mismatches"])

    if total_issues == 0:
        print("Status: PASS - All sampled records match")
        sys.exit(0)
    else:
        print(f"Status: FAIL - {total_issues} issues found")
        sys.exit(1)


if __name__ == "__main__":
    main()
