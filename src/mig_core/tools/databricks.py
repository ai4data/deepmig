"""Databricks tools for executing scripts and queries on Databricks.

This module provides two core tools for any Databricks-based workflow:
1. databricks_submit_job - Submit PySpark scripts to Databricks cluster
2. databricks_run_sql - Execute SQL queries on Databricks SQL Warehouse

These tools read credentials from the project's config file (migration_config.json),
not environment variables. They work with any catalog, schema, and table names.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import (
    RunLifeCycleState,
    RunResultState,
    SparkPythonTask,
    SubmitTask,
)
from databricks.sdk.service.sql import StatementState
from langchain_core.tools import BaseTool, tool

# Path to migration config (relative to agent's /memories/ filesystem)
CONFIG_PATH = "/memories/input/config/migration_config.json"

# Polling interval for job status checks
JOB_POLL_INTERVAL_SECONDS = 10

# Maximum wait time for job completion (30 minutes)
JOB_MAX_WAIT_SECONDS = 1800


def _ensure_str(value: Any) -> str | None:
    """Convert bytes to string if needed, for JSON serialization safety."""
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _sanitize_for_json(obj: Any) -> Any:
    """Recursively sanitize an object for JSON serialization.

    Converts bytes to strings and handles nested structures.
    """
    if obj is None:
        return None
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(item) for item in obj]
    if isinstance(obj, (str, int, float, bool)):
        return obj
    # For other objects, try to convert to string
    try:
        return str(obj)
    except Exception:
        return repr(obj)


def _to_str(value: Any) -> str | None:
    """Convert a value to string, handling bytes and None."""
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


class DatabricksConfig:
    """Holds Databricks configuration loaded from migration_config.json."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.target = config.get("target", {})
        self.credentials = config.get("credentials", {}).get("databricks", {})

        # Connection settings - ensure all are strings (not bytes)
        self.workspace_url = _to_str(self.target.get("workspace_url"))
        self.cluster_id = _to_str(self.target.get("cluster_id"))
        self.warehouse_id = _to_str(
            self.target.get("warehouse_id") or self.credentials.get("sql_warehouse_id")
        )
        self.token = _to_str(self.credentials.get("personal_access_token"))

        # Catalog info
        catalog_config = self.target.get("catalog", {})
        self.catalog = _to_str(catalog_config.get("name"))
        self.schemas = catalog_config.get("schemas", {})

    def validate(self) -> None:
        """Validate required configuration is present."""
        missing = []
        if not self.workspace_url:
            missing.append("target.workspace_url")
        if not self.token:
            missing.append("credentials.databricks.personal_access_token")
        if not self.cluster_id:
            missing.append("target.cluster_id")
        if not self.warehouse_id:
            missing.append("target.warehouse_id")

        if missing:
            raise ValueError(
                f"Missing required Databricks configuration: {', '.join(missing)}"
            )

    def get_client(self) -> WorkspaceClient:
        """Create a Databricks WorkspaceClient."""
        self.validate()
        return WorkspaceClient(host=self.workspace_url, token=self.token)


def _strip_line_numbers(content: str) -> str:
    """Strip line numbers from backend output if present.

    Backend.read() returns content in different formats:
    - "    1→content" (arrow format)
    - "1\tcontent" or "     1\tcontent" (tab format)

    This function extracts just the content after the separator.
    """
    import re
    lines = []
    # Pattern matches: optional spaces, digits, then arrow or tab
    line_number_pattern = re.compile(r'^\s*\d+[\t→]')

    for line in content.split("\n"):
        # Check for arrow format
        if "→" in line:
            parts = line.split("→", 1)
            if len(parts) > 1:
                lines.append(parts[1])
                continue

        # Check for tab format (line_number\tcontent)
        if "\t" in line:
            match = line_number_pattern.match(line)
            if match:
                # Remove the line number prefix
                lines.append(line[match.end():])
                continue

        # No line number prefix found, keep line as-is
        lines.append(line)

    return "\n".join(lines)


def _load_config_from_backend(backend: Any) -> dict[str, Any]:
    """Load migration config from the agent's backend filesystem."""
    content = backend.read(CONFIG_PATH)

    # Handle None or empty content
    if not content:
        raise ValueError(f"Config file at {CONFIG_PATH} is empty or could not be read")

    # Ensure content is a string (backend might return bytes)
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")

    # Remove BOM if present (UTF-8 BOM is \ufeff)
    if content.startswith('\ufeff'):
        content = content[1:]

    # Strip whitespace
    content = content.strip()

    # Try to parse as raw JSON first (backend might return clean content)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Try stripping line numbers (format: "    1→content")
    stripped_content = _strip_line_numbers(content).strip()

    try:
        return json.loads(stripped_content)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in content (skip any prefix)
    json_start = content.find('{')
    if json_start >= 0:
        try:
            return json.loads(content[json_start:])
        except json.JSONDecodeError:
            pass

    # All attempts failed - provide helpful error
    raise ValueError(
        f"Failed to parse migration config at {CONFIG_PATH}.\n"
        f"Content type: {type(content).__name__}, length: {len(content)}\n"
        f"First 300 chars: {content[:300]!r}\n"
        f"Please ensure the file contains valid JSON."
    )


def _create_databricks_submit_job(backend: Any) -> BaseTool:
    """Create the submit_job tool with backend access."""

    @tool
    def submit_job(
        script_path: str,
        wait_for_completion: bool = True,
    ) -> dict[str, Any]:
        """Submit a PySpark script to run on the target platform cluster (e.g., Databricks).

        USE THIS TOOL WHEN:
        - Transforming data ALREADY IN the target platform (bronze → silver → gold)
        - Running PySpark/Spark SQL scripts on cluster
        - The script path starts with /memories/ (virtual filesystem)

        DO NOT USE when the script needs to connect to localhost or on-prem sources
        that the cluster cannot reach - use local_execute instead.

        Args:
            script_path: Path to the script in /memories/ (e.g., "/memories/scripts/wave1_dimensions.py")
            wait_for_completion: If True, wait for job to complete and return results.

        Returns:
            Dict with run_id, status, result_state, and message.

        Example:
            submit_job("/memories/scripts/wave1_dimensions.py")
        """
        try:
            return _submit_job_impl(backend, script_path, wait_for_completion)
        except Exception as e:
            # Catch any exception and return a safe error dict
            error_result = {
                "error": True,
                "message": f"Job submission failed: {str(e)}",
                "exception_type": type(e).__name__,
            }
            return _sanitize_for_json(error_result)

    return submit_job


def _submit_job_impl(backend: Any, script_path: str, wait_for_completion: bool) -> dict[str, Any]:
    """Internal implementation of submit_job with full error handling."""
    # Load config and create client
    config = _load_config_from_backend(backend)
    db_config = DatabricksConfig(config)
    client = db_config.get_client()

    # Read script content from agent's filesystem
    script_content = backend.read(script_path)

    # Validate script was found
    if script_content is None:
        return {
            "error": True,
            "status": "FAILED",
            "message": f"Script not found at path: {script_path}",
            "script_path": script_path,
        }

    # Ensure script content is a string (backend might return bytes)
    if isinstance(script_content, bytes):
        script_content = script_content.decode("utf-8", errors="replace")

    # Validate script is not empty
    if not script_content or not script_content.strip():
        return {
            "error": True,
            "status": "FAILED",
            "message": f"Script is empty: {script_path}",
            "script_path": script_path,
        }

    # Strip line numbers if present (handles both arrow and tab formats)
    clean_script = _strip_line_numbers(script_content)

    # Generate unique DBFS path for the script
    script_name = str(Path(script_path).stem)
    timestamp = int(time.time())
    dbfs_path = f"/tmp/deepmig/{script_name}_{timestamp}.py"

    # Upload script to DBFS
    # The REST API expects base64-encoded content
    import base64
    try:
        script_bytes = clean_script.encode("utf-8")
        script_b64 = base64.b64encode(script_bytes).decode("ascii")
        client.dbfs.put(
            path=str(dbfs_path),
            contents=script_b64,
            overwrite=True,
        )
    except TypeError as e:
        return {
            "error": True,
            "status": "FAILED",
            "message": f"DBFS upload failed (TypeError): {e}",
            "stage": "dbfs_upload",
        }
    except Exception as e:
        return {
            "error": True,
            "status": "FAILED",
            "message": f"DBFS upload failed: {type(e).__name__}: {e}",
            "stage": "dbfs_upload",
        }

    # Submit job - ensure all string parameters are explicitly str type
    run_name = f"deepmig-{script_name}"
    cluster_id = str(db_config.cluster_id) if db_config.cluster_id else ""
    python_file_path = f"dbfs:{dbfs_path}"

    try:
        run = client.jobs.submit(
            run_name=run_name,
            tasks=[
                SubmitTask(
                    task_key="migration",
                    existing_cluster_id=cluster_id,
                    spark_python_task=SparkPythonTask(python_file=python_file_path),
                )
            ],
        )
    except TypeError as e:
        return {
            "error": True,
            "status": "FAILED",
            "message": f"Job submit failed (TypeError): {e}",
            "stage": "job_submit",
            "run_name": run_name,
            "cluster_id": cluster_id,
            "python_file": python_file_path,
        }

    # Extract run_id - handle various SDK return types
    raw_run_id = run.run_id
    if isinstance(raw_run_id, bytes):
        run_id = int(raw_run_id.decode("utf-8"))
    elif isinstance(raw_run_id, str):
        run_id = int(raw_run_id)
    elif isinstance(raw_run_id, int):
        run_id = raw_run_id
    else:
        # Try to extract integer from whatever type it is
        run_id = int(str(raw_run_id))

    result: dict[str, Any] = {
        "run_id": run_id,
        "script": str(script_path),
        "dbfs_path": f"dbfs:{dbfs_path}",
        "cluster_id": str(db_config.cluster_id) if db_config.cluster_id else None,
    }

    if not wait_for_completion:
        result["status"] = "SUBMITTED"
        result["message"] = f"Job submitted with run_id {run_id}"
        return _sanitize_for_json(result)

    # Wait for completion
    start_time = time.time()
    while True:
        run_status = client.jobs.get_run(run_id=run_id)
        state = run_status.state

        if state.life_cycle_state in (
            RunLifeCycleState.TERMINATED,
            RunLifeCycleState.SKIPPED,
            RunLifeCycleState.INTERNAL_ERROR,
        ):
            # Job finished - extract status safely
            result["status"] = str(state.life_cycle_state.value) if state.life_cycle_state else "UNKNOWN"
            result["result_state"] = str(state.result_state.value) if state.result_state else None

            if state.result_state == RunResultState.SUCCESS:
                result["message"] = "Job completed successfully"
            else:
                # Get error message safely
                msg = str(state.state_message) if state.state_message else "Job failed"
                result["message"] = msg
                result["error"] = msg

            # Try to get output logs
            try:
                output = client.jobs.get_run_output(run_id=run_id)
                if output.logs:
                    logs_str = str(output.logs) if not isinstance(output.logs, str) else output.logs
                    result["logs"] = logs_str[:5000]
                if output.error:
                    error_str = str(output.error) if not isinstance(output.error, str) else output.error
                    result["error_trace"] = error_str
            except Exception:
                pass

            return _sanitize_for_json(result)

        # Check timeout
        elapsed = time.time() - start_time
        if elapsed > JOB_MAX_WAIT_SECONDS:
            result["status"] = "TIMEOUT"
            result["message"] = f"Job still running after {JOB_MAX_WAIT_SECONDS}s"
            return _sanitize_for_json(result)

        # Wait before next poll
        time.sleep(JOB_POLL_INTERVAL_SECONDS)


def _create_databricks_run_sql(backend: Any) -> BaseTool:
    """Create the databricks_run_sql tool with backend access."""

    @tool
    def run_sql(query: str) -> list[dict[str, Any]] | dict[str, Any]:
        """Execute a SQL query on the target platform and return results.

        Use this tool to:
        - Validate row counts after migration
        - Check data quality rules
        - Query table metadata
        - Compare expected vs actual values

        Args:
            query: SQL query to execute (e.g., "SELECT COUNT(*) as cnt FROM catalog.schema.table")

        Returns:
            List of row dictionaries for SELECT queries,
            or status dict for DDL/DML statements.

        Examples:
            # Count rows in a table
            run_sql("SELECT COUNT(*) as cnt FROM my_catalog.my_schema.my_table")

            # Check for null values in a column
            run_sql("SELECT COUNT(*) FROM my_catalog.my_schema.my_table WHERE id IS NULL")

            # Validate data quality rules
            run_sql("SELECT COUNT(*) FROM my_catalog.my_schema.orders WHERE amount <= 0")
        """
        # Load config and create client
        config = _load_config_from_backend(backend)
        db_config = DatabricksConfig(config)
        client = db_config.get_client()

        # Execute query with max allowed wait_timeout (50s)
        # If query takes longer, we poll for completion
        response = client.statement_execution.execute_statement(
            warehouse_id=db_config.warehouse_id,
            statement=query,
            wait_timeout="50s",  # Max allowed by Databricks API
        )

        # Poll if still pending (for queries that take longer than 50s)
        statement_id = response.statement_id
        max_poll_time = 300  # 5 minutes max
        poll_interval = 5  # Check every 5 seconds
        elapsed = 0

        while response.status.state in (StatementState.PENDING, StatementState.RUNNING):
            if elapsed >= max_poll_time:
                return _sanitize_for_json({
                    "error": True,
                    "message": f"Query timed out after {max_poll_time} seconds",
                    "query": query,
                    "statement_id": statement_id,
                })
            time.sleep(poll_interval)
            elapsed += poll_interval
            response = client.statement_execution.get_statement(statement_id=statement_id)

        # Check for errors
        if response.status.state == StatementState.FAILED:
            return _sanitize_for_json({
                "error": True,
                "message": response.status.error.message if response.status.error else "Query failed",
                "query": query,
            })

        if response.status.state not in (StatementState.SUCCEEDED,):
            return _sanitize_for_json({
                "error": True,
                "message": f"Query ended with state: {response.status.state.value}",
                "query": query,
            })

        # Check if we have results (SELECT query)
        if response.manifest and response.manifest.schema and response.result:
            columns = [col.name for col in response.manifest.schema.columns]
            rows = []

            if response.result.data_array:
                for row_data in response.result.data_array:
                    row_dict = {}
                    for i, col_name in enumerate(columns):
                        row_dict[col_name] = row_data[i] if i < len(row_data) else None
                    rows.append(row_dict)

            return _sanitize_for_json(rows)

        # DDL/DML statement (no results)
        return _sanitize_for_json({
            "status": "SUCCESS",
            "message": "Statement executed successfully",
            "query": query,
        })

    return run_sql
