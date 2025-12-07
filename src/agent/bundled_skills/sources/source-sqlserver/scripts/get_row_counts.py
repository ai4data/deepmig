#!/usr/bin/env python3
"""Get row counts for all tables in SQL Server database.

Usage:
    python get_row_counts.py
    python get_row_counts.py --database NORTHWND

Environment Variables Required:
    SQL_SERVER_HOST, SQL_SERVER_PORT, SQL_SERVER_USER,
    SQL_SERVER_PASSWORD, SQL_SERVER_DATABASE_OLTP
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


def get_connection_string(database: str | None = None) -> str:
    """Build SQL Server connection string from environment variables."""
    host = os.environ.get("SQL_SERVER_HOST")
    port = os.environ.get("SQL_SERVER_PORT", "1433")
    user = os.environ.get("SQL_SERVER_USER")
    password = os.environ.get("SQL_SERVER_PASSWORD")
    db = database or os.environ.get("SQL_SERVER_DATABASE_OLTP")

    missing = []
    if not host:
        missing.append("SQL_SERVER_HOST")
    if not user:
        missing.append("SQL_SERVER_USER")
    if not password:
        missing.append("SQL_SERVER_PASSWORD")
    if not db:
        missing.append("SQL_SERVER_DATABASE_OLTP")

    if missing:
        print(f"ERROR: Missing environment variables: {', '.join(missing)}")
        sys.exit(1)

    return (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={host},{port};"
        f"DATABASE={db};"
        f"UID={user};"
        f"PWD={password};"
        f"TrustServerCertificate=yes;"
    )


def get_all_row_counts(database: str | None = None) -> list[dict]:
    """Get row counts for all tables using sys.dm_db_partition_stats (fast method)."""
    conn = pyodbc.connect(get_connection_string(database), timeout=30)
    cursor = conn.cursor()

    # Use partition stats for fast row counts (avoids full table scans)
    cursor.execute("""
        SELECT
            s.name AS schema_name,
            t.name AS table_name,
            SUM(p.rows) AS row_count
        FROM sys.tables t
        INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
        INNER JOIN sys.partitions p ON t.object_id = p.object_id
        WHERE p.index_id IN (0, 1)  -- heap or clustered index
        GROUP BY s.name, t.name
        ORDER BY SUM(p.rows) DESC
    """)

    results = []
    total_rows = 0

    for row in cursor.fetchall():
        count = row[2]
        results.append({
            "schema": row[0],
            "table": row[1],
            "full_name": f"{row[0]}.{row[1]}",
            "row_count": count
        })
        total_rows += count

    cursor.close()
    conn.close()

    return results, total_rows


def main():
    parser = argparse.ArgumentParser(description="Get row counts for all SQL Server tables")
    parser.add_argument("--database", help="Database name (overrides default)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--output", help="Export to CSV file")
    args = parser.parse_args()

    try:
        print("Fetching row counts...")
        results, total = get_all_row_counts(args.database)

        if args.output:
            import csv
            with open(args.output, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["schema", "table", "full_name", "row_count"])
                writer.writeheader()
                writer.writerows(results)
            print(f"Exported to {args.output}")
            return

        if args.json:
            print(json.dumps({"tables": results, "total_rows": total}, indent=2))
            return

        # Table format
        print(f"\n{'Table':<40} {'Row Count':>15}")
        print("-" * 56)

        for r in results:
            print(f"{r['full_name']:<40} {r['row_count']:>15,}")

        print("-" * 56)
        print(f"{'TOTAL':<40} {total:>15,}")
        print(f"\n{len(results)} tables found")

    except pyodbc.Error as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
