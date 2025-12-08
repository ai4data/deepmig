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




# =============================================================================
# Class-Based Session Management (New - adopted from open-ptc-agent patterns)
# =============================================================================

class WorkflowSession:
    """Manages workflow state lifecycle with lazy initialization.

    Adopts patterns from open-ptc-agent Session class:
    - Lazy initialization (state loaded on first access)
    - Async context manager support (auto-save on exit)
    - Initialization state tracking (prevents double-init)

    Example:
        async with WorkflowSession(agent_dir) as session:
            state = await session.get_state()
            session.advance_stage()
            # State automatically saved on exit
    """

    def __init__(
        self,
        agent_dir: str | Path,
        config_hash: str = "",
        auto_reset_on_config_change: bool = True,
    ):
        self.agent_dir = Path(agent_dir).expanduser()
        self.config_hash = config_hash
        self.auto_reset_on_config_change = auto_reset_on_config_change
        self._state: dict[str, Any] | None = None
        self._initialized: bool = False
        self._dirty: bool = False

    @property
    def state_path(self) -> Path:
        return self.agent_dir / "memories" / "workflow_state.json"

    @property
    def snapshots_dir(self) -> Path:
        return self.agent_dir / "memories" / "snapshots"

    async def initialize(self) -> None:
        """Load state from disk (lazy, idempotent)."""
        if self._initialized:
            return
        self._state = load_state(self.agent_dir)
        if self._state is None:
            self._state = create_initial_state(self.config_hash)
            self._dirty = True
        elif self.auto_reset_on_config_change and self.config_hash:
            if should_reset_state(self._state, self.config_hash):
                await self.save_snapshot("before_config_reset")
                self._state = create_initial_state(self.config_hash)
                self._dirty = True
        self._initialized = True

    async def get_state(self) -> dict[str, Any]:
        """Get state (auto-initializes if needed)."""
        if not self._initialized:
            await self.initialize()
        return self._state

    async def save(self) -> None:
        """Save current state to disk."""
        if self._state is not None:
            save_state(self.agent_dir, self._state)
            self._dirty = False

    async def save_snapshot(self, tag: str = "") -> Path:
        """Save a timestamped snapshot."""
        if self._state is None:
            await self.initialize()
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        from datetime import datetime, timezone
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"workflow_state_{tag}_{timestamp}.json" if tag else f"workflow_state_{timestamp}.json"
        snapshot_path = self.snapshots_dir / filename
        import json
        snapshot_data = {**self._state, "snapshot_at": datetime.now(timezone.utc).isoformat(), "snapshot_tag": tag}
        with open(snapshot_path, "w", encoding="utf-8") as f:
            json.dump(snapshot_data, f, indent=2)
        return snapshot_path

    def advance_stage(self) -> dict[str, Any]:
        if self._state is None:
            raise RuntimeError("Session not initialized")
        self._state = advance_stage(self._state)
        self._dirty = True
        return self._state

    def record_attempt(self, stage: str | None = None) -> dict[str, Any]:
        if self._state is None:
            raise RuntimeError("Session not initialized")
        stage = stage or self._state.get("current_stage", "planning")
        self._state = record_attempt(self._state, stage)
        self._dirty = True
        return self._state

    def record_error(self, error: str, stage: str | None = None) -> dict[str, Any]:
        if self._state is None:
            raise RuntimeError("Session not initialized")
        stage = stage or self._state.get("current_stage", "planning")
        self._state = record_error(self._state, stage, error)
        self._dirty = True
        return self._state

    @property
    def current_stage(self) -> str:
        return self._state.get("current_stage", "planning") if self._state else "planning"

    @property
    def completed_stages(self) -> list[str]:
        return self._state.get("completed_stages", []) if self._state else []

    @property
    def is_completed(self) -> bool:
        return self.current_stage == "completed"

    def get_resume_info(self) -> str:
        return get_resume_info(self._state)

    def format_for_prompt(self) -> str:
        return format_state_for_prompt(self._state)

    async def cleanup(self) -> None:
        if self._dirty and self._state is not None:
            await self.save()

    async def __aenter__(self) -> "WorkflowSession":
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.cleanup()


class WorkflowSessionManager:
    """Registry for managing multiple workflow sessions."""
    _sessions: dict[str, WorkflowSession] = {}

    @classmethod
    def get_session(cls, workflow_id: str, agent_dir: str | Path, config_hash: str = "") -> WorkflowSession:
        if workflow_id not in cls._sessions:
            cls._sessions[workflow_id] = WorkflowSession(agent_dir=agent_dir, config_hash=config_hash)
        return cls._sessions[workflow_id]

    @classmethod
    async def cleanup_session(cls, workflow_id: str) -> None:
        if workflow_id in cls._sessions:
            await cls._sessions[workflow_id].cleanup()
            del cls._sessions[workflow_id]

    @classmethod
    async def cleanup_all(cls) -> None:
        for session in cls._sessions.values():
            await session.cleanup()
        cls._sessions.clear()

    @classmethod
    def get_active_sessions(cls) -> list[str]:
        return list(cls._sessions.keys())

    @classmethod
    def get_session_count(cls) -> int:
        return len(cls._sessions)


# =============================================================================
# Legacy Function-Based API (Preserved for Backward Compatibility)
# =============================================================================

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
