#!/usr/bin/env python3
"""Validate all tables in a migration wave.

Usage:
    python validate_wave.py --config /path/to/wave0_mapping.json

Environment Variables Required:
    SQL Server:
        SQL_SERVER_HOST, SQL_SERVER_USER, SQL_SERVER_PASSWORD, SQL_SERVER_DATABASE_OLTP
    Databricks:
        DATABRICKS_HOST, DATABRICKS_TOKEN, DATABRICKS_WAREHOUSE_ID

Wave Mapping File Format:
    {
      "wave": "wave0",
      "layer": "bronze",
      "mappings": [
        {"source": "dbo.Customers", "target": "northwnd_bronze.customers"},
        {"source": "dbo.Orders", "target": "northwnd_bronze.orders"}
      ]
    }
"""
import os
import sys
import argparse
import json
from pathlib import Path

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


def get_source_count(conn, table_name: str) -> int:
    """Get row count from SQL Server source table."""
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    return cursor.fetchone()[0]


def get_target_count(config: dict, table_name: str) -> int:
    """Get row count from Databricks target table."""
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
        return -1  # Error indicator

    result = response.json()
    if result.get("status", {}).get("state") != "SUCCEEDED":
        return -1

    data = result.get("result", {}).get("data_array", [[0]])
    return int(data[0][0])


def main():
    parser = argparse.ArgumentParser(description="Validate all tables in a migration wave")
    parser.add_argument("--config", required=True, help="Path to wave mapping JSON file")
    args = parser.parse_args()

    # Load mapping config
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"ERROR: Config file not found: {args.config}")
        sys.exit(1)

    with open(config_path) as f:
        wave_config = json.load(f)

    wave_name = wave_config.get("wave", "unknown")
    layer = wave_config.get("layer", "unknown")
    mappings = wave_config.get("mappings", [])

    if not mappings:
        print("ERROR: No table mappings found in config")
        sys.exit(1)

    print("=" * 50)
    print(f"VALIDATION REPORT - {wave_name} {layer.title()} Layer")
    print("=" * 50)
    print()

    # Get configs
    sql_config = get_sql_server_config()
    dbx_config = get_databricks_config()

    # Connect to SQL Server
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={sql_config['host']};"
        f"DATABASE={sql_config['database']};"
        f"UID={sql_config['user']};"
        f"PWD={sql_config['password']}"
    )

    try:
        sql_conn = pyodbc.connect(conn_str)
    except Exception as e:
        print(f"ERROR: Failed to connect to SQL Server: {e}")
        sys.exit(1)

    # Validate each table
    results = []
    passed = 0
    failed = 0

    for mapping in mappings:
        source_table = mapping["source"]
        target_table = mapping["target"]

        # Get table name for display
        display_name = source_table.split(".")[-1] if "." in source_table else source_table

        try:
            source_count = get_source_count(sql_conn, source_table)
            target_count = get_target_count(dbx_config, target_table)

            if target_count == -1:
                status = "ERROR"
                message = "Failed to query target"
                failed += 1
            elif source_count == target_count:
                status = "PASS"
                message = ""
                passed += 1
            else:
                status = "FAIL"
                diff = source_count - target_count
                if diff > 0:
                    message = f"({diff:,} rows missing)"
                else:
                    message = f"({abs(diff):,} extra rows)"
                failed += 1

            results.append({
                "table": display_name,
                "source_count": source_count,
                "target_count": target_count,
                "status": status,
                "message": message
            })

        except Exception as e:
            results.append({
                "table": display_name,
                "source_count": "N/A",
                "target_count": "N/A",
                "status": "ERROR",
                "message": str(e)
            })
            failed += 1

    sql_conn.close()

    # Print results
    for r in results:
        print(f"Table: {r['table']}")
        print(f"  Source (SQL Server): {r['source_count']:,} rows" if isinstance(r['source_count'], int) else f"  Source (SQL Server): {r['source_count']}")
        print(f"  Target (Databricks): {r['target_count']:,} rows" if isinstance(r['target_count'], int) else f"  Target (Databricks): {r['target_count']}")
        print(f"  Status: {r['status']} {r['message']}")
        print()

    # Summary
    total = len(results)
    print("-" * 50)
    print(f"Summary: {passed}/{total} tables passed")

    if failed > 0:
        print(f"         {failed}/{total} tables failed")
        sys.exit(1)
    else:
        print("All validations passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()
