#!/usr/bin/env python3
"""Get the status of a Databricks job run.

Usage:
    python get_run_status.py --run-id <run_id>

Environment Variables Required:
    DATABRICKS_HOST - Databricks workspace URL
    DATABRICKS_TOKEN - Personal access token
"""
import os
import sys
import argparse
import json

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


def get_run_status(host: str, token: str, run_id: int) -> dict:
    """Get the status of a job run."""
    response = requests.get(
        f"{host}/api/2.1/jobs/runs/get",
        headers={"Authorization": f"Bearer {token}"},
        params={"run_id": run_id}
    )

    if response.status_code != 200:
        return {"error": response.text, "status_code": response.status_code}

    return response.json()


def get_run_output(host: str, token: str, run_id: int) -> dict:
    """Get the output of a job run."""
    response = requests.get(
        f"{host}/api/2.1/jobs/runs/get-output",
        headers={"Authorization": f"Bearer {token}"},
        params={"run_id": run_id}
    )

    if response.status_code != 200:
        return {"error": response.text}

    return response.json()


def main():
    parser = argparse.ArgumentParser(description="Get Databricks job run status")
    parser.add_argument("--run-id", required=True, type=int, help="Job run ID")
    parser.add_argument("--output", action="store_true", help="Also fetch run output/logs")
    args = parser.parse_args()

    host, token = get_databricks_config()

    # Get run status
    status = get_run_status(host, token, args.run_id)

    if "error" in status:
        print(f"ERROR: {status['error']}")
        sys.exit(1)

    # Extract key information
    state = status.get("state", {})
    life_cycle_state = state.get("life_cycle_state", "UNKNOWN")
    result_state = state.get("result_state")

    print(f"Run ID: {args.run_id}")
    print(f"Run Name: {status.get('run_name', 'N/A')}")
    print(f"State: {life_cycle_state}")

    if result_state:
        print(f"Result: {result_state}")

    if state.get("state_message"):
        print(f"Message: {state['state_message']}")

    # Timing info
    start_time = status.get("start_time")
    end_time = status.get("end_time")
    if start_time and end_time:
        duration_ms = end_time - start_time
        print(f"Duration: {duration_ms / 1000:.1f} seconds")

    # Cluster info
    cluster_instance = status.get("cluster_instance", {})
    if cluster_instance.get("cluster_id"):
        print(f"Cluster: {cluster_instance['cluster_id']}")

    # View URL
    print(f"View: {host}/#job/{status.get('job_id', '')}/run/{args.run_id}")

    # Optionally get output
    if args.output and life_cycle_state == "TERMINATED":
        print("\n--- Run Output ---")
        output = get_run_output(host, token, args.run_id)
        if "error" not in output:
            logs = output.get("logs", "")
            if logs:
                print(logs[:2000])  # Truncate long output
            else:
                print("(No output captured)")
        else:
            print(f"Could not fetch output: {output['error']}")

    # Full JSON output
    print("\n--- Full Status JSON ---")
    print(json.dumps(status, indent=2))


if __name__ == "__main__":
    main()
