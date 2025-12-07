#!/usr/bin/env python3
"""Get table schema information from SQL Server.

Usage:
    python get_schema.py --table "dbo.Customers"
    python get_schema.py --list-tables

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


def get_connection(database: str | None = None):
    """Get database connection."""
    return pyodbc.connect(get_connection_string(database), timeout=30)


def list_tables(database: str | None = None) -> list[dict]:
    """List all tables in the database."""
    conn = get_connection(database)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            TABLE_SCHEMA,
            TABLE_NAME,
            TABLE_TYPE
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE = 'BASE TABLE'
        ORDER BY TABLE_SCHEMA, TABLE_NAME
    """)

    tables = []
    for row in cursor.fetchall():
        tables.append({
            "schema": row[0],
            "name": row[1],
            "full_name": f"{row[0]}.{row[1]}"
        })

    cursor.close()
    conn.close()

    return tables


def get_table_schema(table_name: str, database: str | None = None) -> dict:
    """Get detailed schema for a specific table."""
    # Parse schema.table format
    if "." in table_name:
        schema, table = table_name.split(".", 1)
    else:
        schema, table = "dbo", table_name

    conn = get_connection(database)
    cursor = conn.cursor()

    # Get columns
    cursor.execute("""
        SELECT
            c.COLUMN_NAME,
            c.DATA_TYPE,
            c.CHARACTER_MAXIMUM_LENGTH,
            c.NUMERIC_PRECISION,
            c.NUMERIC_SCALE,
            c.IS_NULLABLE,
            c.COLUMN_DEFAULT,
            c.ORDINAL_POSITION
        FROM INFORMATION_SCHEMA.COLUMNS c
        WHERE c.TABLE_SCHEMA = ? AND c.TABLE_NAME = ?
        ORDER BY c.ORDINAL_POSITION
    """, schema, table)

    columns = []
    for row in cursor.fetchall():
        col = {
            "name": row[0],
            "type": row[1],
            "nullable": row[5] == "YES",
            "position": row[7]
        }
        if row[2]:
            col["max_length"] = row[2]
        if row[3]:
            col["precision"] = row[3]
            col["scale"] = row[4]
        if row[6]:
            col["default"] = row[6]
        columns.append(col)

    # Get primary key
    cursor.execute("""
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
        WHERE OBJECTPROPERTY(OBJECT_ID(CONSTRAINT_SCHEMA + '.' + QUOTENAME(CONSTRAINT_NAME)), 'IsPrimaryKey') = 1
        AND TABLE_SCHEMA = ? AND TABLE_NAME = ?
        ORDER BY ORDINAL_POSITION
    """, schema, table)
    primary_key = [row[0] for row in cursor.fetchall()]

    # Get foreign keys
    cursor.execute("""
        SELECT
            fk.name AS fk_name,
            COL_NAME(fkc.parent_object_id, fkc.parent_column_id) AS column_name,
            OBJECT_SCHEMA_NAME(fkc.referenced_object_id) AS ref_schema,
            OBJECT_NAME(fkc.referenced_object_id) AS ref_table,
            COL_NAME(fkc.referenced_object_id, fkc.referenced_column_id) AS ref_column
        FROM sys.foreign_keys fk
        JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
        WHERE OBJECT_SCHEMA_NAME(fk.parent_object_id) = ?
        AND OBJECT_NAME(fk.parent_object_id) = ?
    """, schema, table)

    foreign_keys = []
    for row in cursor.fetchall():
        foreign_keys.append({
            "name": row[0],
            "column": row[1],
            "references": f"{row[2]}.{row[3]}.{row[4]}"
        })

    # Get row count
    cursor.execute(f"SELECT COUNT(*) FROM [{schema}].[{table}]")
    row_count = cursor.fetchone()[0]

    cursor.close()
    conn.close()

    return {
        "schema": schema,
        "table": table,
        "full_name": f"{schema}.{table}",
        "columns": columns,
        "primary_key": primary_key,
        "foreign_keys": foreign_keys,
        "row_count": row_count
    }


def main():
    parser = argparse.ArgumentParser(description="Get SQL Server table schema")
    parser.add_argument("--table", help="Table name (e.g., dbo.Customers)")
    parser.add_argument("--database", help="Database name (overrides default)")
    parser.add_argument("--list-tables", action="store_true", help="List all tables")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    try:
        if args.list_tables:
            tables = list_tables(args.database)
            print(f"Found {len(tables)} tables:\n")

            if args.json:
                print(json.dumps(tables, indent=2))
            else:
                for t in tables:
                    print(f"  {t['full_name']}")

        elif args.table:
            schema_info = get_table_schema(args.table, args.database)

            if args.json:
                print(json.dumps(schema_info, indent=2))
            else:
                print(f"Table: {schema_info['full_name']}")
                print(f"Row Count: {schema_info['row_count']:,}")
                print()

                print("Columns:")
                for col in schema_info['columns']:
                    nullable = "NULL" if col['nullable'] else "NOT NULL"
                    type_info = col['type']
                    if col.get('max_length'):
                        type_info += f"({col['max_length']})"
                    elif col.get('precision'):
                        type_info += f"({col['precision']},{col['scale']})"
                    print(f"  {col['name']}: {type_info} {nullable}")

                if schema_info['primary_key']:
                    print(f"\nPrimary Key: {', '.join(schema_info['primary_key'])}")

                if schema_info['foreign_keys']:
                    print("\nForeign Keys:")
                    for fk in schema_info['foreign_keys']:
                        print(f"  {fk['column']} -> {fk['references']}")

        else:
            parser.print_help()

    except pyodbc.Error as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
