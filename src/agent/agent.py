"""Main agent creation for DeepMig.

This module creates the migration agent with its sub-agents and tools.
"""

import shutil
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends.composite import CompositeBackend
from deepagents.backends.filesystem import FilesystemBackend

from mig_core.backends import EncodingAwareFilesystemBackend
from langchain.agents.middleware import InterruptOnConfig
from langchain.agents.middleware.types import AgentState
from langchain.messages import ToolCall
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.runtime import Runtime

from deepagents_cli.config import config

from mig_core.agent_memory import AgentMemoryMiddleware
from mig_core.tools import TargetToolsMiddleware, LocalToolsMiddleware
from mig_core.workflow_middleware import WorkflowMiddleware

from agent.prompts import get_main_prompt
from agent.subagents import code_agent, code_review_agent, critique_agent, planning_agent, create_validator_agent_with_tools
from mig_core.skills import SkillsMiddleware, get_bundled_skills_dir


def _sync_bundled_skills(bundled_skills_dir: Path, agent_dir: Path) -> Path:
    """Copy bundled skills to agent's memories for virtual filesystem access.

    Args:
        bundled_skills_dir: Source path to bundled skills in package.
        agent_dir: Agent's directory (e.g., ~/.deepagents/migration-planner/).

    Returns:
        Path to the copied bundled skills in agent_dir/memories/.
    """
    # Place inside memories/ so /memories/bundled_skills/ route works
    target_dir = agent_dir / "memories" / "bundled_skills"

    # Only copy if bundled skills are newer or target doesn't exist
    if not target_dir.exists():
        shutil.copytree(bundled_skills_dir, target_dir)
    else:
        # Update any changed files
        for src_file in bundled_skills_dir.rglob("*"):
            if src_file.is_file():
                rel_path = src_file.relative_to(bundled_skills_dir)
                dst_file = target_dir / rel_path
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                # Only copy if source is newer
                if not dst_file.exists() or src_file.stat().st_mtime > dst_file.stat().st_mtime:
                    shutil.copy2(src_file, dst_file)

    return target_dir


def _find_project_skills_dir() -> Path | None:
    """Find project-level skills directory by looking for .git."""
    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        if (parent / ".git").exists():
            skills_dir = parent / ".deepagents" / "skills"
            return skills_dir if skills_dir.exists() else None
    return None


def _format_task_description(tool_call: ToolCall, state: AgentState, runtime: Runtime) -> str:
    """Format task (subagent) tool call for approval prompt."""
    args = tool_call["args"]
    description = args.get("description", "unknown")
    prompt = args.get("prompt", "")

    # Truncate prompt if too long
    prompt_preview = prompt[:300]
    if len(prompt) > 300:
        prompt_preview += "..."

    return (
        f"Task: {description}\n\n"
        f"Instructions to subagent:\n"
        f"{'─' * 40}\n"
        f"{prompt_preview}\n"
        f"{'─' * 40}\n\n"
        f"Subagent will analyze and provide recommendations"
    )


def create_migration_agent(
    model: object,
    assistant_id: str,
    auto_approve: bool = False,
) -> tuple[object, CompositeBackend]:
    """Create the main DeepMig migration agent with CLI infrastructure.

    Args:
        model: The LLM model to use.
        assistant_id: Agent identifier for memory storage.
        auto_approve: Whether to auto-approve tool calls.

    Returns:
        Tuple of (agent, composite_backend) for use with the CLI.
    """
    main_prompt = get_main_prompt()

    # Setup agent directory for persistent memory
    agent_dir = Path.home() / ".deepagents" / assistant_id
    agent_dir.mkdir(parents=True, exist_ok=True)

    # Memories directory - where /memories/ virtual route points to
    memories_dir = agent_dir / "memories"
    memories_dir.mkdir(parents=True, exist_ok=True)

    # Initialize agent.md with default content if it doesn't exist
    # Note: agent.md is inside memories/ so it's accessible via /memories/agent.md
    agent_md = memories_dir / "agent.md"
    if not agent_md.exists():
        agent_md.write_text("# DeepMig Agent Memory\n\nThis file stores the agent's long-term memory.\n")

    # Long-term backend for /memories/ route - maps to memories_dir
    # Uses encoding-aware backend to handle non-UTF-8 files gracefully
    long_term_backend = EncodingAwareFilesystemBackend(root_dir=memories_dir, virtual_mode=True)

    # Composite backend: local filesystem + /memories/ route
    # Default backend also uses encoding-aware version for consistency
    composite_backend = CompositeBackend(
        default=EncodingAwareFilesystemBackend(),  # Current working directory
        routes={"/memories/": long_term_backend},  # Agent memories
    )

    # Skills directories
    skills_dir = agent_dir / "skills"
    project_skills_dir = _find_project_skills_dir()

    # Copy bundled skills to agent directory for virtual filesystem access
    # This allows read_file to access them via /memories/bundled_skills/
    original_bundled_dir = get_bundled_skills_dir()
    if original_bundled_dir:
        bundled_skills_dir = _sync_bundled_skills(original_bundled_dir, agent_dir)
    else:
        bundled_skills_dir = None

    # Create target tools middleware to get platform-specific tools
    target_tools_middleware = TargetToolsMiddleware(backend=composite_backend)
    # Pass memories_dir so local_execute can resolve /memories/ virtual paths
    local_tools_middleware = LocalToolsMiddleware(memories_dir=memories_dir)

    # Get execution tools for validator agent
    # Combines local tools (always available) and platform tools (config-driven)
    validator_tools = local_tools_middleware.tools + target_tools_middleware.tools

    # Create validator agent with execution tools
    validator_agent = create_validator_agent_with_tools(tools=validator_tools)

    # Middleware: memory management + skills + workflow + execution tools
    # Note: SummarizationMiddleware is already added by create_deep_agent
    agent_middleware = [
        AgentMemoryMiddleware(backend=long_term_backend, memory_path="/memories/"),
        SkillsMiddleware(
            skills_dir=skills_dir,
            assistant_id=assistant_id,
            project_skills_dir=project_skills_dir,
            bundled_skills_dir=bundled_skills_dir,
        ),
        WorkflowMiddleware(agent_dir=agent_dir),
        local_tools_middleware,  # Local script execution (always available)
        target_tools_middleware,  # Platform tools loaded based on config
    ]

    # Configure human-in-the-loop for task tool (subagents)
    interrupt_on = {}
    if not auto_approve:
        task_interrupt_config: InterruptOnConfig = {
            "allowed_decisions": ["approve", "reject"],
            "description": _format_task_description,
        }
        interrupt_on["task"] = task_interrupt_config

    # Create the agent with sub-agents
    agent = create_deep_agent(
        model=model,
        system_prompt=main_prompt,
        subagents=[planning_agent, critique_agent, code_agent, code_review_agent, validator_agent],
        backend=composite_backend,
        middleware=agent_middleware,
        interrupt_on=interrupt_on if interrupt_on else None,
    ).with_config(config)

    agent.checkpointer = InMemorySaver()

    return agent, composite_backend
