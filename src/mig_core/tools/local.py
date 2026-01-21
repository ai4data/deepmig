"""Local execution tools for DeepMig.

This module provides tools for executing scripts locally, which is required
for scenarios where the migration source (e.g., SQL Server) is on localhost
and cannot be reached from a cloud-based Databricks cluster.

Use cases:
- Wave 0 bronze ingestion from localhost SQL Server
- Any script that needs local filesystem or network access
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
)
from langchain_core.tools import BaseTool, tool


# Maximum execution time for local scripts (10 minutes)
LOCAL_SCRIPT_TIMEOUT_SECONDS = 600

# Maximum output length to return
MAX_OUTPUT_LENGTH = 10000

# Virtual path prefix used by the agent
MEMORIES_VIRTUAL_PREFIX = "/memories/"

# Default migration venv location
DEFAULT_MIGRATION_VENV_DIR = Path.home() / ".deepagents" / "migration-venv"


def _find_default_python_executable() -> Path | None:
    """Find the default Python executable in the shared migration venv.

    Checks for the migration-venv at ~/.deepagents/migration-venv/
    and returns the Python executable path if it exists.

    Returns:
        Path to Python executable, or None if not found.
    """
    # Check platform-specific locations
    if sys.platform == "win32":
        python_path = DEFAULT_MIGRATION_VENV_DIR / "Scripts" / "python.exe"
    else:
        # Linux, Mac, WSL
        python_path = DEFAULT_MIGRATION_VENV_DIR / "bin" / "python"

    if python_path.exists():
        return python_path

    return None


def _resolve_virtual_path(path: str, memories_dir: Path | None) -> Path:
    """Resolve a virtual path to a real filesystem path.

    Args:
        path: The path to resolve (can be virtual like /memories/... or real)
        memories_dir: The real directory that /memories/ maps to

    Returns:
        Resolved Path object pointing to real filesystem location
    """
    # Check if this is a virtual /memories/ path
    if path.startswith(MEMORIES_VIRTUAL_PREFIX) and memories_dir is not None:
        # Strip the /memories/ prefix and join with real memories_dir
        relative_path = path[len(MEMORIES_VIRTUAL_PREFIX):]
        return memories_dir / relative_path

    # Regular path - just resolve normally
    return Path(path).expanduser().resolve()


def _resolve_python_executable(
    python_executable: str | None,
    default_python: Path | None,
) -> str:
    """Resolve the Python executable to use.

    Priority:
    1. Explicit python_executable parameter (if provided)
    2. Default migration venv Python (if exists)
    3. Current Python interpreter (sys.executable)

    Args:
        python_executable: Explicitly specified Python path (optional)
        default_python: Default Python from migration-venv (optional)

    Returns:
        Path to Python executable as string
    """
    if python_executable:
        # Expand ~ and resolve
        resolved = Path(python_executable).expanduser().resolve()
        if resolved.exists():
            return str(resolved)
        # If specified but doesn't exist, return it anyway (will fail with clear error)
        return python_executable

    if default_python and default_python.exists():
        return str(default_python)

    return sys.executable


def _create_local_execute_tool(
    memories_dir: Path | None = None,
    default_python_executable: Path | None = None,
) -> BaseTool:
    """Create the local_execute tool for running local Python scripts.

    Args:
        memories_dir: The real filesystem path that /memories/ maps to.
                     If provided, /memories/... paths will be resolved.
        default_python_executable: Default Python interpreter to use.
                                  If None, will try to find migration-venv.
    """
    # Try to find default Python if not provided
    if default_python_executable is None:
        default_python_executable = _find_default_python_executable()

    @tool
    def local_execute(
        script_path: str,
        script_args: str = "",
        working_dir: str = "",
        python_executable: str = "",
        timeout: int = LOCAL_SCRIPT_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        """Execute a Python script locally on the user's machine (NOT on a remote cluster).

        USE THIS TOOL WHEN:
        - Script needs to connect to localhost/on-prem database (e.g., SQL Server on localhost)
        - Script needs local filesystem access
        - Source system is NOT reachable from cloud cluster (no VPN/Private Link)
        - Ingesting data FROM local source TO cloud (wave 0 / bronze ingestion)

        DO NOT USE when:
        - Transforming data already in the cloud (bronze → gold) - use submit_job instead

        Args:
            script_path: Path to the Python script. Supports both:
                         - Virtual paths: "/memories/scripts/wave0/script.py"
                         - Real paths: "C:/scripts/ingest.py" or "~/scripts/ingest.py"
            script_args: Command-line arguments to pass to the script.
            working_dir: Working directory for script execution. Supports virtual paths.
            python_executable: Python interpreter to use. If not specified, uses:
                              1. ~/.deepagents/migration-venv/ (if exists)
                              2. Current Python interpreter (fallback)
            timeout: Maximum execution time in seconds (default: 600).

        Returns:
            Dict with success, exit_code, stdout, stderr, message, python_used.

        Examples:
            # Using virtual path (recommended for agent-generated scripts)
            local_execute(script_path="/memories/scripts/wave0/wave0_bronze_ingestion.py")

            # With specific Python environment
            local_execute(
                script_path="/memories/scripts/wave0/ingest.py",
                python_executable="~/.deepagents/migration-venv/bin/python"
            )

            # With arguments
            local_execute(
                script_path="/memories/scripts/wave0/ingest.py",
                script_args="--config /memories/input/config/migration_config.json"
            )
        """
        # Resolve script path (handles both virtual and real paths)
        script_path_obj = _resolve_virtual_path(script_path, memories_dir)

        if not script_path_obj.exists():
            # Provide helpful error message
            if script_path.startswith(MEMORIES_VIRTUAL_PREFIX):
                return {
                    "success": False,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": f"Script not found: {script_path_obj}",
                    "message": (
                        f"Error: Script file does not exist.\n"
                        f"Virtual path: {script_path}\n"
                        f"Resolved to: {script_path_obj}\n"
                        f"Memories dir: {memories_dir}"
                    ),
                }
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Script not found: {script_path_obj}",
                "message": f"Error: Script file does not exist at {script_path_obj}",
            }

        if not script_path_obj.suffix == ".py":
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Not a Python file: {script_path_obj}",
                "message": "Error: Only Python scripts (.py) are allowed",
            }

        # Resolve Python executable
        python_exe = _resolve_python_executable(
            python_executable if python_executable else None,
            default_python_executable,
        )

        # Check if Python executable exists
        python_exe_path = Path(python_exe)
        if not python_exe_path.exists():
            # Provide helpful error about missing venv
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Python executable not found: {python_exe}",
                "message": (
                    f"Error: Python executable not found at {python_exe}\n\n"
                    f"To create the migration environment, run:\n"
                    f"  python -m venv ~/.deepagents/migration-venv\n"
                    f"  source ~/.deepagents/migration-venv/bin/activate  # Linux/Mac/WSL\n"
                    f"  pip install pandas pyodbc databricks-sdk python-dotenv"
                ),
            }

        # Determine working directory (also supports virtual paths)
        if working_dir:
            cwd = _resolve_virtual_path(working_dir, memories_dir)
        else:
            cwd = script_path_obj.parent

        # Build command
        cmd = [python_exe, str(script_path_obj)]
        if script_args:
            # Split script_args string into list (handles quoted strings)
            import shlex
            # Also resolve any /memories/ paths in arguments
            args = shlex.split(script_args)
            resolved_args = []
            for arg in args:
                if arg.startswith(MEMORIES_VIRTUAL_PREFIX) and memories_dir is not None:
                    resolved_args.append(str(_resolve_virtual_path(arg, memories_dir)))
                else:
                    resolved_args.append(arg)
            cmd.extend(resolved_args)

        try:
            # Execute the script
            result = subprocess.run(
                cmd,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            # Truncate output if too long
            stdout = result.stdout
            stderr = result.stderr

            if len(stdout) > MAX_OUTPUT_LENGTH:
                stdout = stdout[:MAX_OUTPUT_LENGTH] + f"\n... (truncated, {len(result.stdout)} total chars)"
            if len(stderr) > MAX_OUTPUT_LENGTH:
                stderr = stderr[:MAX_OUTPUT_LENGTH] + f"\n... (truncated, {len(result.stderr)} total chars)"

            success = result.returncode == 0

            return {
                "success": success,
                "exit_code": result.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "message": "Script completed successfully" if success else f"Script failed with exit code {result.returncode}",
                "script_path": str(script_path_obj),
                "python_used": python_exe,
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Script timed out after {timeout} seconds",
                "message": f"Error: Script execution timed out after {timeout} seconds",
                "python_used": python_exe,
            }
        except Exception as e:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
                "message": f"Error executing script: {e}",
                "python_used": python_exe,
            }

    return local_execute


def _create_local_shell_tool(memories_dir: Path | None = None) -> BaseTool:
    """Create the local_shell tool for running shell commands.

    Args:
        memories_dir: The real filesystem path that /memories/ maps to.
                     If provided, /memories/... paths in working_dir will be resolved.
    """

    @tool
    def local_shell(
        command: str,
        working_dir: str = "",
        timeout: int = 120,
    ) -> dict[str, Any]:
        """Execute a shell command locally on the user's machine.

        Use this tool for simple shell operations like checking file existence,
        listing directories, or running pip commands.

        Args:
            command: Shell command to execute (e.g., "pip install pandas").
            working_dir: Working directory for command execution. Supports virtual paths.
                         Defaults to current directory.
            timeout: Maximum execution time in seconds (default: 120 = 2 minutes).

        Returns:
            Dict with:
                - success: bool - Whether the command completed successfully
                - exit_code: int - The command's exit code (0 = success)
                - stdout: str - Standard output
                - stderr: str - Standard error
                - message: str - Human-readable status message

        Examples:
            # Check Python version
            local_shell("python --version")

            # Install a package
            local_shell("pip install pyodbc")

            # List files in memories directory
            local_shell("ls -la", working_dir="/memories/scripts/wave0")
        """
        # Determine working directory (supports virtual paths)
        if working_dir:
            cwd = _resolve_virtual_path(working_dir, memories_dir)
        else:
            cwd = Path.cwd()

        try:
            # Execute the command
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            # Truncate output if too long
            stdout = result.stdout
            stderr = result.stderr

            if len(stdout) > MAX_OUTPUT_LENGTH:
                stdout = stdout[:MAX_OUTPUT_LENGTH] + f"\n... (truncated)"
            if len(stderr) > MAX_OUTPUT_LENGTH:
                stderr = stderr[:MAX_OUTPUT_LENGTH] + f"\n... (truncated)"

            success = result.returncode == 0

            return {
                "success": success,
                "exit_code": result.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "message": "Command completed successfully" if success else f"Command failed with exit code {result.returncode}",
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Command timed out after {timeout} seconds",
                "message": f"Error: Command execution timed out after {timeout} seconds",
            }
        except Exception as e:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
                "message": f"Error executing command: {e}",
            }

    return local_shell


class LocalToolsMiddleware(AgentMiddleware):
    """Middleware that provides local execution tools to the agent.

    This middleware adds tools for executing scripts and commands locally,
    which is required for migrations where the source system is on localhost.

    Tools provided:
    - local_execute: Run Python scripts locally (supports /memories/ paths)
    - local_shell: Run shell commands locally

    Python Environment Resolution:
    The local_execute tool automatically uses the shared migration venv at
    ~/.deepagents/migration-venv/ if it exists. This can be overridden per-call
    with the python_executable parameter.

    Args:
        memories_dir: The real filesystem path that /memories/ maps to.
                     This enables the tools to resolve virtual paths like
                     /memories/scripts/wave0/script.py to real paths.
        python_executable: Default Python interpreter for local_execute.
                          If None, will auto-detect ~/.deepagents/migration-venv/.

    Example:
        ```python
        from pathlib import Path
        from mig_core.tools import LocalToolsMiddleware

        # With virtual path support (recommended)
        memories_dir = Path.home() / ".deepagents" / "my-agent" / "memories"
        middleware = LocalToolsMiddleware(memories_dir=memories_dir)

        # With custom Python executable
        middleware = LocalToolsMiddleware(
            memories_dir=memories_dir,
            python_executable=Path("/path/to/venv/bin/python")
        )
        ```
    """

    def __init__(
        self,
        memories_dir: Path | None = None,
        python_executable: Path | None = None,
    ) -> None:
        """Initialize the local tools middleware.

        Args:
            memories_dir: The real filesystem path that /memories/ maps to.
                         If None, virtual paths won't be resolved.
            python_executable: Default Python interpreter for local_execute.
                              If None, will auto-detect migration-venv.
        """
        self._memories_dir = memories_dir
        self._python_executable = python_executable
        self._tools: list[BaseTool] | None = None

    def _get_tools(self) -> list[BaseTool]:
        """Lazily create tools."""
        if self._tools is None:
            self._tools = [
                _create_local_execute_tool(
                    memories_dir=self._memories_dir,
                    default_python_executable=self._python_executable,
                ),
                _create_local_shell_tool(memories_dir=self._memories_dir),
            ]
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
        """Add local tools to the model request."""
        tools = list(request.tools) if request.tools else []
        tools.extend(self._get_tools())
        request.tools = tools
        return handler(request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """(async) Add local tools to the model request."""
        tools = list(request.tools) if request.tools else []
        tools.extend(self._get_tools())
        request.tools = tools
        return await handler(request)
