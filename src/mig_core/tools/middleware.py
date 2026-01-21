"""Dynamic target tools middleware for DeepMig.

This middleware loads execution tools based on config.target.platform,
following the same pattern as SkillsMiddleware for technology-agnostic operation.

Instead of loading all platform tools at startup, only the tools for the
configured target platform are loaded. This keeps the context lean and
scales well as more platforms are added.

Usage:
    middleware = TargetToolsMiddleware(
        backend=composite_backend,
        config_path="/memories/input/config/migration_config.json"
    )
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
)
from langchain_core.tools import BaseTool


# Registry of platform tools factories
# Each factory takes a backend and returns a list of tools
_PLATFORM_TOOL_FACTORIES: dict[str, Callable[[Any], list[BaseTool]]] = {}


def register_platform_tools(platform: str):
    """Decorator to register tools for a target platform.

    Example:
        @register_platform_tools("databricks")
        def create_databricks_tools(backend) -> list[BaseTool]:
            return [databricks_submit_job, databricks_run_sql]
    """
    def decorator(factory: Callable[[Any], list[BaseTool]]):
        _PLATFORM_TOOL_FACTORIES[platform] = factory
        return factory
    return decorator


def get_registered_platforms() -> list[str]:
    """Get list of platforms with registered tools."""
    return list(_PLATFORM_TOOL_FACTORIES.keys())


class TargetToolsMiddleware(AgentMiddleware):
    """Middleware that dynamically loads tools based on config.target.platform.

    This middleware is technology-agnostic - it doesn't know about specific
    platforms. Instead, platforms register their tools using @register_platform_tools,
    and this middleware loads the appropriate tools based on the config.

    If the config file doesn't exist or can't be read, no platform-specific
    tools are loaded (graceful degradation).

    Args:
        backend: The CompositeBackend for reading config and files.
        config_path: Virtual path to migration config (default: /memories/input/config/migration_config.json).

    Example:
        ```python
        from mig_core.tools.middleware import TargetToolsMiddleware

        middleware = TargetToolsMiddleware(
            backend=composite_backend,
            config_path="/memories/input/config/migration_config.json"
        )
        ```
    """

    def __init__(
        self,
        backend: Any,
        config_path: str = "/memories/input/config/migration_config.json",
    ) -> None:
        """Initialize the target tools middleware.

        Args:
            backend: Backend for reading config files.
            config_path: Path to migration config file.
        """
        self.backend = backend
        self.config_path = config_path
        self._tools: list[BaseTool] | None = None
        self._platform: str | None = None

    def _read_config(self) -> dict[str, Any] | None:
        """Read and parse the migration config file."""
        import logging
        logger = logging.getLogger(__name__)

        try:
            content = self.backend.read(self.config_path)
            if not content:
                logger.debug(f"Config file empty or not found: {self.config_path}")
                return None

            # Handle bytes
            if isinstance(content, bytes):
                content = content.decode("utf-8", errors="replace")

            # Strip line numbers if present (backend format)
            lines = []
            for line in content.split("\n"):
                if "→" in line:
                    parts = line.split("→", 1)
                    if len(parts) > 1:
                        lines.append(parts[1])
                        continue
                if "\t" in line:
                    import re
                    match = re.match(r'^\s*\d+\t', line)
                    if match:
                        lines.append(line[match.end():])
                        continue
                lines.append(line)

            clean_content = "\n".join(lines).strip()

            # Remove BOM if present
            if clean_content.startswith('\ufeff'):
                clean_content = clean_content[1:]

            return json.loads(clean_content)

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse config JSON: {e}")
            return None
        except FileNotFoundError:
            logger.debug(f"Config file not found: {self.config_path}")
            return None
        except Exception as e:
            logger.warning(f"Error reading config from {self.config_path}: {e}")
            return None

    def _get_platform(self) -> str | None:
        """Get target platform from config."""
        if self._platform is not None:
            return self._platform

        config = self._read_config()
        if config:
            self._platform = config.get("target", {}).get("platform")

        return self._platform

    def _get_tools(self) -> list[BaseTool]:
        """Get tools for the configured platform."""
        import logging
        logger = logging.getLogger(__name__)

        if self._tools is not None:
            return self._tools

        self._tools = []
        platform = self._get_platform()

        if platform:
            if platform in _PLATFORM_TOOL_FACTORIES:
                factory = _PLATFORM_TOOL_FACTORIES[platform]
                self._tools = factory(self.backend)
                logger.debug(f"Loaded {len(self._tools)} tools for platform '{platform}'")
            else:
                available = list(_PLATFORM_TOOL_FACTORIES.keys())
                logger.warning(
                    f"No tools registered for platform '{platform}'. "
                    f"Available platforms: {available}"
                )
        else:
            logger.debug("No target platform configured, no platform-specific tools loaded")

        return self._tools

    @property
    def tools(self) -> list[BaseTool]:
        """Expose tools for framework registration."""
        return self._get_tools()

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        """Add platform-specific tools to the model request."""
        tools = list(request.tools) if request.tools else []
        tools.extend(self._get_tools())
        request.tools = tools
        return handler(request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """(async) Add platform-specific tools to the model request."""
        tools = list(request.tools) if request.tools else []
        tools.extend(self._get_tools())
        request.tools = tools
        return await handler(request)


# Import platform tools to trigger registration
# Each platform module uses @register_platform_tools to register itself
def _register_builtin_platforms():
    """Register built-in platform tools."""
    # Import modules directly (not from package) to avoid circular import issues
    # Each module uses @register_platform_tools to register itself
    try:
        import mig_core.tools.databricks_tools  # noqa: F401
    except ImportError as e:
        import logging
        logging.getLogger(__name__).debug(f"Could not load databricks_tools: {e}")


# Auto-register on module load
_register_builtin_platforms()
