#!/usr/bin/env python3
"""Upload a file to Databricks DBFS storage.

Usage:
    python upload_to_dbfs.py --local /path/to/file.py --dbfs /path/in/dbfs

Environment Variables Required:
    DATABRICKS_HOST - Databricks workspace URL
    DATABRICKS_TOKEN - Personal access token
"""
import os
import sys
import argparse
import base64
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: 'requests' package not installed. Run: pip install requests")
    sys.exit(1)


def get_databricks_config() -> tuple[str, str]:
    """Get Databricks host and token from environment."""
    host = os.environ.get("DATABRICKS_HOST")
    token = os.environ.get("DATABRICKS_TOKEN")

    if not host:
        print("ERROR: DATABRICKS_HOST environment variable not set")
        sys.exit(1)
    if not token:
        print("ERROR: DATABRICKS_TOKEN environment variable not set")
        sys.exit(1)

    return host.rstrip("/"), token


def upload_file(host: str, token: str, local_path: str, dbfs_path: str, overwrite: bool = True) -> bool:
    """Upload a local file to DBFS using streaming for large files."""
    local_file = Path(local_path)

    if not local_file.exists():
        print(f"ERROR: Local file not found: {local_path}")
        return False

    file_size = local_file.stat().st_size
    print(f"Uploading {local_path} ({file_size:,} bytes) to dbfs:{dbfs_path}")

    # For small files (< 1MB), use simple put
    if file_size < 1_000_000:
        with open(local_path, "rb") as f:
            content = base64.b64encode(f.read()).decode("utf-8")

        response = requests.post(
            f"{host}/api/2.0/dbfs/put",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "path": dbfs_path,
                "contents": content,
                "overwrite": overwrite
            }
        )

        if response.status_code != 200:
            print(f"ERROR: Upload failed: {response.text}")
            return False

        print(f"Successfully uploaded to dbfs:{dbfs_path}")
        return True

    # For larger files, use streaming upload
    print("Using streaming upload for large file...")

    # Create handle
    response = requests.post(
        f"{host}/api/2.0/dbfs/create",
        headers={"Authorization": f"Bearer {token}"},
        json={"path": dbfs_path, "overwrite": overwrite}
    )

    if response.status_code != 200:
        print(f"ERROR: Failed to create upload handle: {response.text}")
        return False

    handle = response.json().get("handle")

    # Upload in 1MB chunks
    chunk_size = 1_000_000
    with open(local_path, "rb") as f:
        chunk_num = 0
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break

            chunk_num += 1
            print(f"  Uploading chunk {chunk_num}...")

            response = requests.post(
                f"{host}/api/2.0/dbfs/add-block",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "handle": handle,
                    "data": base64.b64encode(chunk).decode("utf-8")
                }
            )

            if response.status_code != 200:
                print(f"ERROR: Failed to upload chunk: {response.text}")
                return False

    # Close handle
    response = requests.post(
        f"{host}/api/2.0/dbfs/close",
        headers={"Authorization": f"Bearer {token}"},
        json={"handle": handle}
    )

    if response.status_code != 200:
        print(f"ERROR: Failed to close upload: {response.text}")
        return False

    print(f"Successfully uploaded to dbfs:{dbfs_path}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Upload file to Databricks DBFS")
    parser.add_argument("--local", required=True, help="Path to local file")
    parser.add_argument("--dbfs", required=True, help="Target path in DBFS (e.g., /mnt/data/file.py)")
    parser.add_argument("--no-overwrite", action="store_true", help="Don't overwrite if exists")
    args = parser.parse_args()

    host, token = get_databricks_config()

    success = upload_file(
        host, token,
        args.local,
        args.dbfs,
        overwrite=not args.no_overwrite
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
