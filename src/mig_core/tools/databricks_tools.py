"""Databricks platform tools registration.

This module registers Databricks execution tools with the TargetToolsMiddleware.
Tools are only loaded when config.target.platform == "databricks".
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool

from mig_core.tools.middleware import register_platform_tools


@register_platform_tools("databricks")
def create_databricks_tools(backend: Any) -> list[BaseTool]:
    """Create Databricks execution tools.

    This factory is called by TargetToolsMiddleware when the config
    specifies target.platform = "databricks".

    Args:
        backend: The CompositeBackend for reading config and scripts.

    Returns:
        List of Databricks tools: [databricks_submit_job, databricks_run_sql]
    """
    # Import here to avoid circular imports and only load when needed
    from mig_core.tools.databricks import (
        _create_databricks_submit_job,
        _create_databricks_run_sql,
    )

    return [
        _create_databricks_submit_job(backend),
        _create_databricks_run_sql(backend),
    ]
