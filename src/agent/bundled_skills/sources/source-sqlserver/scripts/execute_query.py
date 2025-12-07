#!/usr/bin/env python3
"""Execute SQL queries against SQL Server.

Usage:
    python execute_query.py --query "SELECT COUNT(*) FROM dbo.Customers"
    python execute_query.py --query "SELECT * FROM dbo.Orders" --output results.csv

Environment Variables Required:
    SQL_SERVER_HOST - SQL Server hostname
    SQL_SERVER_PORT - Port (default: 1433)
    SQL_SERVER_USER - Database username
    SQL_SERVER_PASSWORD - Database password
    SQL_SERVER_DATABASE_OLTP - Default database
"""
import os
import sys
import argparse
import csv
from pathlib import Path

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

    # Build connection string for SQL Server
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={host},{port};"
        f"DATABASE={db};"
        f"UID={user};"
        f"PWD={password};"
        f"TrustServerCertificate=yes;"
    )
    return conn_str


def execute_query(query: str, database: str | None = None) -> tuple[list[str], list[tuple]]:
    """Execute a SQL query and return column names and rows."""
    conn_str = get_connection_string(database)

    try:
        conn = pyodbc.connect(conn_str, timeout=30)
        cursor = conn.cursor()

        print(f"Executing query...")
        cursor.execute(query)

        # Get column names
        columns = [column[0] for column in cursor.description] if cursor.description else []

        # Fetch all rows
        rows = cursor.fetchall()

        cursor.close()
        conn.close()

        return columns, rows

    except pyodbc.Error as e:
        print(f"ERROR: SQL Server error: {e}")
        sys.exit(1)


def format_table(columns: list[str], rows: list[tuple], max_width: int = 50) -> str:
    """Format results as an ASCII table."""
    if not columns:
        return "(No results)"

    # Calculate column widths
    widths = [len(col) for col in columns]
    for row in rows[:100]:  # Sample first 100 rows for width calculation
        for i, val in enumerate(row):
            str_val = str(val) if val is not None else "NULL"
            widths[i] = min(max_width, max(widths[i], len(str_val)))

    # Build table
    lines = []

    # Header
    header = " | ".join(col[:widths[i]].ljust(widths[i]) for i, col in enumerate(columns))
    separator = "-+-".join("-" * w for w in widths)
    lines.append(header)
    lines.append(separator)

    # Rows (limit to 100 for display)
    for row in rows[:100]:
        row_str = " | ".join(
            (str(val) if val is not None else "NULL")[:widths[i]].ljust(widths[i])
            for i, val in enumerate(row)
        )
        lines.append(row_str)

    if len(rows) > 100:
        lines.append(f"... ({len(rows) - 100} more rows)")

    return "\n".join(lines)


def export_csv(columns: list[str], rows: list[tuple], output_path: str):
    """Export results to CSV file."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for row in rows:
            writer.writerow(row)

    print(f"Exported {len(rows)} rows to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Execute SQL Server queries")
    parser.add_argument("--query", required=True, help="SQL query to execute")
    parser.add_argument("--database", help="Database name (overrides default)")
    parser.add_argument("--output", help="Export results to CSV file")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    # Execute query
    columns, rows = execute_query(args.query, args.database)

    print(f"\nQuery returned {len(rows)} row(s)")
    print()

    # Export to CSV if requested
    if args.output:
        export_csv(columns, rows, args.output)
        return

    # Output as JSON if requested
    if args.json:
        import json
        result = [dict(zip(columns, row)) for row in rows]
        print(json.dumps(result, indent=2, default=str))
        return

    # Display as table
    print(format_table(columns, rows))


if __name__ == "__main__":
    main()
