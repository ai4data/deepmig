#!/usr/bin/env python3
"""Submit a Python script to Databricks Jobs API for execution.

This script uploads a local Python file to DBFS and submits it as a
one-time job run on an existing Databricks cluster.

Usage:
    python submit_job.py --script /path/to/script.py --cluster-id <cluster_id>

Environment Variables Required:
    DATABRICKS_HOST - Databricks workspace URL
    DATABRICKS_TOKEN - Personal access token
"""
import os
import sys
import argparse
import base64
import time
import json
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

    # Remove trailing slash from host
    host = host.rstrip("/")
    return host, token


def upload_to_dbfs(host: str, token: str, local_path: str, dbfs_path: str) -> bool:
    """Upload a local file to DBFS."""
    print(f"Uploading {local_path} to dbfs:{dbfs_path}...")

    with open(local_path, "rb") as f:
        content = base64.b64encode(f.read()).decode("utf-8")

    response = requests.post(
        f"{host}/api/2.0/dbfs/put",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "path": dbfs_path,
            "contents": content,
            "overwrite": True
        }
    )

    if response.status_code != 200:
        print(f"ERROR: Failed to upload file: {response.text}")
        return False

    print(f"Successfully uploaded to dbfs:{dbfs_path}")
    return True


def submit_job(host: str, token: str, dbfs_script_path: str, cluster_id: str, job_name: str) -> dict:
    """Submit a one-time job run to Databricks."""
    print(f"Submitting job '{job_name}' to cluster {cluster_id}...")

    response = requests.post(
        f"{host}/api/2.1/jobs/runs/submit",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "run_name": job_name,
            "existing_cluster_id": cluster_id,
            "spark_python_task": {
                "python_file": f"dbfs:{dbfs_script_path}"
            }
        }
    )

    if response.status_code != 200:
        print(f"ERROR: Failed to submit job: {response.text}")
        return {"error": response.text}

    return response.json()


def get_run_status(host: str, token: str, run_id: int) -> dict:
    """Get the status of a job run."""
    response = requests.get(
        f"{host}/api/2.1/jobs/runs/get",
        headers={"Authorization": f"Bearer {token}"},
        params={"run_id": run_id}
    )
    return response.json()


def wait_for_completion(host: str, token: str, run_id: int, timeout: int = 600) -> dict:
    """Wait for job to complete with timeout."""
    print(f"Waiting for job {run_id} to complete (timeout: {timeout}s)...")

    start_time = time.time()
    terminal_states = {"TERMINATED", "SKIPPED", "INTERNAL_ERROR"}

    while time.time() - start_time < timeout:
        status = get_run_status(host, token, run_id)
        state = status.get("state", {})
        life_cycle_state = state.get("life_cycle_state", "UNKNOWN")

        print(f"  Status: {life_cycle_state}")

        if life_cycle_state in terminal_states:
            result_state = state.get("result_state", "UNKNOWN")
            print(f"  Result: {result_state}")
            return status

        time.sleep(10)

    print("ERROR: Timeout waiting for job completion")
    return {"error": "timeout"}


def main():
    parser = argparse.ArgumentParser(description="Submit Python script to Databricks")
    parser.add_argument("--script", required=True, help="Path to local Python script")
    parser.add_argument("--cluster-id", required=True, help="Databricks cluster ID")
    parser.add_argument("--wait", action="store_true", help="Wait for job completion")
    parser.add_argument("--timeout", type=int, default=600, help="Timeout in seconds (default: 600)")
    args = parser.parse_args()

    # Validate script exists
    script_path = Path(args.script)
    if not script_path.exists():
        print(f"ERROR: Script not found: {args.script}")
        sys.exit(1)

    # Get Databricks config
    host, token = get_databricks_config()

    # Upload script to DBFS
    timestamp = int(time.time())
    dbfs_path = f"/tmp/deepmig/{timestamp}_{script_path.name}"

    if not upload_to_dbfs(host, token, str(script_path), dbfs_path):
        sys.exit(1)

    # Submit job
    job_name = f"deepmig-{script_path.stem}-{timestamp}"
    result = submit_job(host, token, dbfs_path, args.cluster_id, job_name)

    if "error" in result:
        sys.exit(1)

    run_id = result.get("run_id")
    print(f"\nJob submitted successfully!")
    print(f"  Run ID: {run_id}")
    print(f"  Job Name: {job_name}")
    print(f"  View at: {host}/#job/{result.get('run_id', '')}")

    # Optionally wait for completion
    if args.wait:
        final_status = wait_for_completion(host, token, run_id, args.timeout)
        result_state = final_status.get("state", {}).get("result_state", "UNKNOWN")

        if result_state == "SUCCESS":
            print("\nJob completed successfully!")
            sys.exit(0)
        else:
            print(f"\nJob failed with state: {result_state}")
            if "error" in final_status.get("state", {}):
                print(f"Error: {final_status['state']['error']}")
            sys.exit(1)

    # Output JSON for programmatic use
    print(f"\nJSON output:")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
