#!/usr/bin/env python3
"""Compare row counts between SQL Server source and Databricks target.

Usage:
    python compare_row_counts.py --source-table "dbo.Customers" --target-table "northwnd_bronze.customers"

Environment Variables Required:
    SQL Server:
        SQL_SERVER_HOST, SQL_SERVER_USER, SQL_SERVER_PASSWORD, SQL_SERVER_DATABASE_OLTP
    Databricks:
        DATABRICKS_HOST, DATABRICKS_TOKEN, DATABRICKS_WAREHOUSE_ID
"""
import os
import sys
import argparse

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


def get_source_count(config: dict, table_name: str) -> int:
    """Get row count from SQL Server source table."""
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
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        print(f"ERROR: Failed to query SQL Server: {e}")
        sys.exit(1)


def get_target_count(config: dict, table_name: str) -> int:
    """Get row count from Databricks target table."""
    # Submit SQL query via Databricks SQL Statement API
    response = requests.post(
        f"{config['host']}/api/2.0/sql/statements",
        headers={"Authorization": f"Bearer {config['token']}"},
        json={
            "warehouse_id": config["warehouse_id"],
            "statement": f"SELECT COUNT(*) FROM {table_name}",
            "wait_timeout": "30s"
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

    # Extract count from result
    data = result.get("result", {}).get("data_array", [[0]])
    return int(data[0][0])


def main():
    parser = argparse.ArgumentParser(description="Compare row counts between source and target")
    parser.add_argument("--source-table", required=True, help="Source table name (e.g., dbo.Customers)")
    parser.add_argument("--target-table", required=True, help="Target table name (e.g., northwnd_bronze.customers)")
    args = parser.parse_args()

    print(f"Comparing row counts...")
    print(f"  Source: {args.source_table}")
    print(f"  Target: {args.target_table}")
    print()

    # Get configs
    sql_config = get_sql_server_config()
    dbx_config = get_databricks_config()

    # Get counts
    source_count = get_source_count(sql_config, args.source_table)
    target_count = get_target_count(dbx_config, args.target_table)

    # Compare
    diff = source_count - target_count
    match = diff == 0

    print(f"Results:")
    print(f"  Source (SQL Server): {source_count:,} rows")
    print(f"  Target (Databricks): {target_count:,} rows")
    print()

    if match:
        print("Status: PASS - Row counts match")
        sys.exit(0)
    else:
        print(f"Status: FAIL - Difference: {abs(diff):,} rows")
        if diff > 0:
            print(f"  ({diff:,} rows missing in target)")
        else:
            print(f"  ({abs(diff):,} extra rows in target)")
        sys.exit(1)


if __name__ == "__main__":
    main()
