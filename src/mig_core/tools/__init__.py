"""DeepMig tools for migration execution and validation."""

from mig_core.tools.middleware import (
    TargetToolsMiddleware,
    register_platform_tools,
    get_registered_platforms,
)

from mig_core.tools.local import (
    LocalToolsMiddleware,
)

# Import to trigger platform registration (use relative import to avoid circular issues)
from . import databricks_tools  # noqa: F401

__all__ = [
    # Dynamic target tools middleware (config-driven)
    "TargetToolsMiddleware",
    "register_platform_tools",
    "get_registered_platforms",
    # Local execution tools (always available)
    "LocalToolsMiddleware",
]
