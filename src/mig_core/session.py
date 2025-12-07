"""Workflow state management for DeepMig.

This module provides utilities for tracking migration workflow progress,
enabling resume capability after API errors or session interruptions.

The workflow state is saved to /memories/workflow_state.json and tracks:
- Current stage in the migration workflow
- Completed stages
- Attempt counts for retry logic
- Timestamps for debugging
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Migration workflow stages in order
WORKFLOW_STAGES = [
    "planning",      # Create migration plan
    "critique",      # Review and improve plan
    "coding",        # Generate migration scripts
    "validation",    # Execute and validate
    "completed",     # All done
]


def get_state_path(agent_dir: str | Path) -> Path:
    """Get the path to the workflow state file.

    Args:
        agent_dir: The agent's directory (e.g., ~/.deepagents/migration-planner)

    Returns:
        Path to workflow_state.json (inside memories folder for agent access via /memories/)
    """
    return Path(agent_dir).expanduser() / "memories" / "workflow_state.json"


def compute_config_hash(config_content: str) -> str:
    """Compute a hash of the migration config to detect changes.

    Args:
        config_content: The raw config file content

    Returns:
        Short hash string (first 8 chars of SHA256)
    """
    return hashlib.sha256(config_content.encode()).hexdigest()[:8]


def load_state(agent_dir: str | Path) -> dict[str, Any] | None:
    """Load the workflow state from disk.

    Args:
        agent_dir: The agent's directory

    Returns:
        The workflow state dict, or None if no state exists
    """
    state_path = get_state_path(agent_dir)
    if not state_path.exists():
        return None

    try:
        with open(state_path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def save_state(agent_dir: str | Path, state: dict[str, Any]) -> None:
    """Save the workflow state to disk.

    Args:
        agent_dir: The agent's directory
        state: The workflow state dict to save
    """
    state_path = get_state_path(agent_dir)
    state_path.parent.mkdir(parents=True, exist_ok=True)

    # Update timestamp
    state["last_updated"] = datetime.now(timezone.utc).isoformat()

    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def create_initial_state(config_hash: str = "") -> dict[str, Any]:
    """Create a fresh workflow state.

    Args:
        config_hash: Hash of the migration config (to detect changes)

    Returns:
        Initial workflow state dict
    """
    return {
        "current_stage": "planning",
        "completed_stages": [],
        "attempts": {stage: 0 for stage in WORKFLOW_STAGES},
        "config_hash": config_hash,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "error_log": [],
    }


def advance_stage(state: dict[str, Any]) -> dict[str, Any]:
    """Mark current stage as completed and advance to next stage.

    Args:
        state: Current workflow state

    Returns:
        Updated workflow state
    """
    current = state["current_stage"]

    if current == "completed":
        return state

    # Mark current stage as completed
    if current not in state["completed_stages"]:
        state["completed_stages"].append(current)

    # Move to next stage
    try:
        current_idx = WORKFLOW_STAGES.index(current)
        if current_idx < len(WORKFLOW_STAGES) - 1:
            state["current_stage"] = WORKFLOW_STAGES[current_idx + 1]
    except ValueError:
        pass

    return state


def record_attempt(state: dict[str, Any], stage: str) -> dict[str, Any]:
    """Record an attempt at a stage (for retry tracking).

    Args:
        state: Current workflow state
        stage: The stage being attempted

    Returns:
        Updated workflow state
    """
    if stage in state["attempts"]:
        state["attempts"][stage] += 1
    return state


def record_error(state: dict[str, Any], stage: str, error: str) -> dict[str, Any]:
    """Record an error for debugging.

    Args:
        state: Current workflow state
        stage: The stage where error occurred
        error: Error message

    Returns:
        Updated workflow state
    """
    state["error_log"].append({
        "stage": stage,
        "error": error,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    # Keep only last 10 errors
    state["error_log"] = state["error_log"][-10:]
    return state


def should_reset_state(state: dict[str, Any], new_config_hash: str) -> bool:
    """Check if state should be reset due to config change.

    Args:
        state: Current workflow state
        new_config_hash: Hash of the current config

    Returns:
        True if state should be reset
    """
    return state.get("config_hash", "") != new_config_hash


def get_resume_info(state: dict[str, Any]) -> str:
    """Get human-readable resume information.

    Args:
        state: Current workflow state

    Returns:
        Formatted string describing the state
    """
    if state is None:
        return "No previous session found. Starting fresh."

    current = state.get("current_stage", "unknown")
    completed = state.get("completed_stages", [])
    last_updated = state.get("last_updated", "unknown")

    if current == "completed":
        return f"Previous migration completed at {last_updated}. Starting fresh."

    completed_str = ", ".join(completed) if completed else "none"
    return (
        f"Resuming from stage: {current}\n"
        f"Completed stages: {completed_str}\n"
        f"Last updated: {last_updated}"
    )


def format_state_for_prompt(state: dict[str, Any] | None) -> str:
    """Format workflow state for injection into agent prompt.

    Args:
        state: Current workflow state (or None)

    Returns:
        Markdown-formatted state information
    """
    if state is None:
        return """## Workflow State
No previous session found. This is a fresh start.
Current stage: **planning**
"""

    current = state.get("current_stage", "planning")
    completed = state.get("completed_stages", [])
    attempts = state.get("attempts", {})

    # Check for existing artifacts
    artifacts = []
    if "planning" in completed:
        artifacts.append("- `/memories/migration_plan.md` (from planning stage)")
    if "critique" in completed:
        artifacts.append("- Plan has been reviewed and approved")
    if "coding" in completed:
        artifacts.append("- `/memories/scripts/` (generated code)")

    artifacts_str = "\n".join(artifacts) if artifacts else "None yet"

    return f"""## Workflow State (Resume Session)

**Current stage**: {current}
**Completed stages**: {", ".join(completed) if completed else "none"}
**Attempt count for {current}**: {attempts.get(current, 0)}

### Existing Artifacts
{artifacts_str}

### Instructions
{"Resume from " + current + " stage. Do NOT repeat completed stages." if completed else "Start fresh with planning."}
"""
