"""Workflow state middleware for DeepMig.

This middleware provides tools for the agent to manage workflow state,
specifically to advance stages when work is completed.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
)
from langchain_core.tools import BaseTool, tool

from mig_core.session import (
    WORKFLOW_STAGES,
    advance_stage,
    load_state,
    save_state,
    create_initial_state,
)


def _create_complete_stage_tool(agent_dir: Path) -> BaseTool:
    """Create the complete_stage tool with agent directory access."""

    @tool
    def complete_stage(stage_name: str | None = None) -> dict[str, Any]:
        """Mark the current workflow stage as complete and advance to the next stage.

        Call this tool when you have finished all work for the current stage:
        - After saving migration_plan.md → complete_stage("planning")
        - After plan is approved (score ≥ 8/10) → complete_stage("critique")
        - After all scripts are generated → complete_stage("coding")
        - After validation passes → complete_stage("validation")

        Args:
            stage_name: Optional stage name to complete. If not provided,
                       completes the current stage from workflow_state.json.

        Returns:
            Dict with previous_stage, current_stage, and completed_stages.

        Example:
            complete_stage("planning")  # After creating migration plan
            complete_stage()  # Completes whatever the current stage is
        """
        # Load current state
        state = load_state(agent_dir)
        if state is None:
            state = create_initial_state()

        previous_stage = state["current_stage"]

        # Validate stage_name if provided
        if stage_name and stage_name != previous_stage:
            return {
                "error": True,
                "message": f"Cannot complete stage '{stage_name}' - current stage is '{previous_stage}'",
                "current_stage": previous_stage,
                "completed_stages": state["completed_stages"],
            }

        # Advance the stage
        state = advance_stage(state)

        # Save updated state
        save_state(agent_dir, state)

        return {
            "success": True,
            "previous_stage": previous_stage,
            "current_stage": state["current_stage"],
            "completed_stages": state["completed_stages"],
            "message": f"Completed '{previous_stage}', now in '{state['current_stage']}' stage",
        }

    return complete_stage


def _create_get_workflow_state_tool(agent_dir: Path) -> BaseTool:
    """Create the get_workflow_state tool."""

    @tool
    def get_workflow_state() -> dict[str, Any]:
        """Get the current workflow state.

        Returns the current stage, completed stages, and other workflow information.
        Use this to check where you are in the migration workflow.

        Returns:
            Dict with current_stage, completed_stages, attempts, and timestamps.

        Example:
            get_workflow_state()  # Returns {"current_stage": "coding", "completed_stages": ["planning", "critique"], ...}
        """
        state = load_state(agent_dir)
        if state is None:
            state = create_initial_state()
            save_state(agent_dir, state)

        return {
            "current_stage": state["current_stage"],
            "completed_stages": state["completed_stages"],
            "attempts": state.get("attempts", {}),
            "last_updated": state.get("last_updated"),
            "available_stages": WORKFLOW_STAGES,
        }

    return get_workflow_state


class WorkflowMiddleware(AgentMiddleware):
    """Middleware that provides workflow state management tools.

    This middleware adds tools for the agent to:
    - complete_stage: Mark current stage as done and advance
    - get_workflow_state: Check current workflow status

    Example:
        ```python
        from mig_core.workflow_middleware import WorkflowMiddleware

        middleware = WorkflowMiddleware(agent_dir=agent_dir)
        ```
    """

    def __init__(self, agent_dir: str | Path) -> None:
        """Initialize with the agent's directory.

        Args:
            agent_dir: Path to agent directory (e.g., ~/.deepagents/my-agent)
        """
        self.agent_dir = Path(agent_dir).expanduser()
        self._tools: list[BaseTool] | None = None

    def _get_tools(self) -> list[BaseTool]:
        """Lazily create tools."""
        if self._tools is None:
            self._tools = [
                _create_complete_stage_tool(self.agent_dir),
                _create_get_workflow_state_tool(self.agent_dir),
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
        """Add workflow tools to the model request."""
        tools = list(request.tools) if request.tools else []
        tools.extend(self._get_tools())
        request.tools = tools
        return handler(request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """(async) Add workflow tools to the model request."""
        tools = list(request.tools) if request.tools else []
        tools.extend(self._get_tools())
        request.tools = tools
        return await handler(request)
