#!/usr/bin/env python3
"""Profile a SQL Server table for data quality analysis.

Usage:
    python profile_table.py --table "dbo.Customers"

Outputs:
- Row count
- Column statistics (nulls, distinct values, min/max)
- Data quality indicators
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


def get_connection():
    """Get SQL Server connection."""
    host = os.environ.get("SQL_SERVER_HOST")
    port = os.environ.get("SQL_SERVER_PORT", "1433")
    user = os.environ.get("SQL_SERVER_USER")
    password = os.environ.get("SQL_SERVER_PASSWORD")
    db = os.environ.get("SQL_SERVER_DATABASE_OLTP")

    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={host},{port};"
        f"DATABASE={db};"
        f"UID={user};"
        f"PWD={password};"
        f"TrustServerCertificate=yes;"
    )
    return pyodbc.connect(conn_str, timeout=30)


def profile_table(table_name: str) -> dict:
    """Profile a table and return statistics."""
    # Parse schema.table
    if "." in table_name:
        schema, table = table_name.split(".", 1)
    else:
        schema, table = "dbo", table_name

    conn = get_connection()
    cursor = conn.cursor()

    # Get row count
    cursor.execute(f"SELECT COUNT(*) FROM [{schema}].[{table}]")
    row_count = cursor.fetchone()[0]

    # Get columns
    cursor.execute("""
        SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, CHARACTER_MAXIMUM_LENGTH
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
        ORDER BY ORDINAL_POSITION
    """, schema, table)

    columns = []
    for row in cursor.fetchall():
        col_name = row[0]
        data_type = row[1]
        is_nullable = row[2] == "YES"
        max_length = row[3]

        # Get null count and distinct count
        cursor.execute(f"""
            SELECT
                SUM(CASE WHEN [{col_name}] IS NULL THEN 1 ELSE 0 END) as null_count,
                COUNT(DISTINCT [{col_name}]) as distinct_count
            FROM [{schema}].[{table}]
        """)
        stats = cursor.fetchone()
        null_count = stats[0] or 0
        distinct_count = stats[1] or 0

        null_pct = (null_count / row_count * 100) if row_count > 0 else 0

        col_profile = {
            "name": col_name,
            "type": data_type,
            "nullable": is_nullable,
            "null_count": null_count,
            "null_percentage": round(null_pct, 2),
            "distinct_count": distinct_count,
            "uniqueness": round(distinct_count / row_count * 100, 2) if row_count > 0 else 0
        }

        if max_length:
            col_profile["max_length"] = max_length

        # Get min/max for numeric and date types
        if data_type in ("int", "bigint", "smallint", "decimal", "numeric", "money", "float"):
            try:
                cursor.execute(f"SELECT MIN([{col_name}]), MAX([{col_name}]) FROM [{schema}].[{table}]")
                min_max = cursor.fetchone()
                col_profile["min"] = float(min_max[0]) if min_max[0] is not None else None
                col_profile["max"] = float(min_max[1]) if min_max[1] is not None else None
            except:
                pass

        columns.append(col_profile)

    cursor.close()
    conn.close()

    return {
        "table": f"{schema}.{table}",
        "row_count": row_count,
        "column_count": len(columns),
        "columns": columns
    }


def main():
    parser = argparse.ArgumentParser(description="Profile SQL Server table")
    parser.add_argument("--table", required=True, help="Table name (e.g., dbo.Customers)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    try:
        profile = profile_table(args.table)

        if args.json:
            print(json.dumps(profile, indent=2))
        else:
            print(f"\nTable Profile: {profile['table']}")
            print("=" * 60)
            print(f"Row Count: {profile['row_count']:,}")
            print(f"Columns: {profile['column_count']}")
            print()

            print(f"{'Column':<25} {'Type':<15} {'Nulls %':<10} {'Distinct':<10}")
            print("-" * 60)

            for col in profile['columns']:
                print(f"{col['name']:<25} {col['type']:<15} {col['null_percentage']:<10.1f} {col['distinct_count']:<10}")

            # Quality indicators
            print()
            print("Data Quality Indicators:")
            high_null_cols = [c['name'] for c in profile['columns'] if c['null_percentage'] > 50]
            if high_null_cols:
                print(f"  [!] High null columns (>50%): {', '.join(high_null_cols)}")

            unique_cols = [c['name'] for c in profile['columns'] if c['uniqueness'] == 100 and c['distinct_count'] > 1]
            if unique_cols:
                print(f"  [+] Potential key columns (100% unique): {', '.join(unique_cols)}")

    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
