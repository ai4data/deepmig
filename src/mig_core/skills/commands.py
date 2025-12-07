"""CLI commands for skill management in DeepMig.

These commands are registered with the CLI via cli.py:
- deepmig skills list --agent <agent>
- deepmig skills create <name> --agent <agent>
- deepmig skills info <name> --agent <agent>
"""

import argparse
import re
from pathlib import Path
from typing import Any

from rich.console import Console

from mig_core.skills.load import get_bundled_skills_dir, list_skills

# Simple console and colors for CLI output
console = Console()
COLORS = {
    "primary": "cyan",
    "dim": "dim",
    "success": "green",
    "error": "red",
    "warning": "yellow",
}


def _validate_name(name: str) -> tuple[bool, str]:
    """Validate name to prevent path traversal attacks.

    Args:
        name: The name to validate

    Returns:
        Tuple of (is_valid, error_message). If valid, error_message is empty.
    """
    # Check for empty or whitespace-only names
    if not name or not name.strip():
        return False, "cannot be empty"

    # Check for path traversal sequences
    if ".." in name:
        return False, "name cannot contain '..' (path traversal)"

    # Check for absolute paths
    if name.startswith(("/", "\\")):
        return False, "name cannot be an absolute path"

    # Check for path separators
    if "/" in name or "\\" in name:
        return False, "name cannot contain path separators"

    # Only allow alphanumeric, hyphens, underscores
    if not re.match(r"^[a-zA-Z0-9_-]+$", name):
        return False, "name can only contain letters, numbers, hyphens, and underscores"

    return True, ""


def _get_user_skills_dir(agent_name: str) -> Path:
    """Get user-level skills directory path for a specific agent."""
    return Path.home() / ".deepagents" / agent_name / "skills"


def _find_project_skills_dir() -> Path | None:
    """Find project-level skills directory by looking for .git."""
    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        if (parent / ".git").exists():
            skills_dir = parent / ".deepagents" / "skills"
            return skills_dir if skills_dir.exists() else None
    return None


def _list(agent: str) -> None:
    """List all available skills for the specified agent.

    Args:
        agent: Agent identifier for skills (default: migration-planner).
    """
    user_skills_dir = _get_user_skills_dir(agent)
    project_skills_dir = _find_project_skills_dir()
    bundled_skills_dir = get_bundled_skills_dir()

    # Load bundled, user, and project skills
    skills = list_skills(
        bundled_skills_dir=bundled_skills_dir,
        user_skills_dir=user_skills_dir,
        project_skills_dir=project_skills_dir,
    )

    if not skills:
        console.print("[yellow]No skills found.[/yellow]")
        console.print(
            f"[dim]Skills will be created in ~/.deepagents/{agent}/skills/ when you add them.[/dim]",
            style=COLORS["dim"],
        )
        console.print(
            f"\n[dim]Create your first skill:\n  deepmig skills create my-skill --agent {agent}[/dim]",
            style=COLORS["dim"],
        )
        return

    console.print("\n[bold]Available Skills:[/bold]\n", style=COLORS["primary"])

    # Group skills by source
    bundled_skills = [s for s in skills if s["source"] == "bundled"]
    user_skills = [s for s in skills if s["source"] == "user"]
    project_skills_list = [s for s in skills if s["source"] == "project"]

    # Show bundled skills
    if bundled_skills:
        console.print("[bold magenta]Bundled Skills:[/bold magenta] (shipped with DeepMig)")
        for skill in bundled_skills:
            console.print(f"  - [bold]{skill['name']}[/bold]", style=COLORS["primary"])
            console.print(f"    {skill['description']}", style=COLORS["dim"])
            console.print()

    # Show user skills
    if user_skills:
        if bundled_skills:
            console.print()
        console.print("[bold cyan]User Skills:[/bold cyan]", style=COLORS["primary"])
        for skill in user_skills:
            skill_path = Path(skill["path"])
            console.print(f"  - [bold]{skill['name']}[/bold]", style=COLORS["primary"])
            console.print(f"    {skill['description']}", style=COLORS["dim"])
            console.print(f"    Location: {skill_path.parent}/", style=COLORS["dim"])
            console.print()

    # Show project skills
    if project_skills_list:
        if user_skills or bundled_skills:
            console.print()
        console.print("[bold green]Project Skills:[/bold green]", style=COLORS["primary"])
        for skill in project_skills_list:
            skill_path = Path(skill["path"])
            console.print(f"  - [bold]{skill['name']}[/bold]", style=COLORS["primary"])
            console.print(f"    {skill['description']}", style=COLORS["dim"])
            console.print(f"    Location: {skill_path.parent}/", style=COLORS["dim"])
            console.print()


def _create(skill_name: str, agent: str) -> None:
    """Create a new skill with a template SKILL.md file.

    Args:
        skill_name: Name of the skill to create.
        agent: Agent identifier for skills
    """
    # Validate skill name first
    is_valid, error_msg = _validate_name(skill_name)
    if not is_valid:
        console.print(f"[bold red]Error:[/bold red] Invalid skill name: {error_msg}")
        console.print(
            "[dim]Skill names must only contain letters, numbers, hyphens, and underscores.[/dim]",
            style=COLORS["dim"],
        )
        return

    # Determine target directory
    skills_dir = _get_user_skills_dir(agent)
    skill_dir = skills_dir / skill_name

    if skill_dir.exists():
        console.print(
            f"[bold red]Error:[/bold red] Skill '{skill_name}' already exists at {skill_dir}"
        )
        return

    # Create skill directory
    skill_dir.mkdir(parents=True, exist_ok=True)

    # Create template SKILL.md
    template = f"""---
name: {skill_name}
description: [Brief description of what this skill does]
---

# {skill_name.title().replace("-", " ")} Skill

## Description

[Provide a detailed explanation of what this skill does and when it should be used]

## When to Use

- [Scenario 1: When the user asks...]
- [Scenario 2: When you need to...]
- [Scenario 3: When the task involves...]

## How to Use

### Step 1: [First Action]
[Explain what to do first]

### Step 2: [Second Action]
[Explain what to do next]

### Step 3: [Final Action]
[Explain how to complete the task]

## Best Practices

- [Best practice 1]
- [Best practice 2]
- [Best practice 3]

## Supporting Files

This skill directory can include supporting files referenced in the instructions:
- `helper.py` - Python scripts for automation
- `config.json` - Configuration files
- `reference.md` - Additional reference documentation

## Examples

### Example 1: [Scenario Name]

**User Request:** "[Example user request]"

**Approach:**
1. [Step-by-step breakdown]
2. [Using tools and commands]
3. [Expected outcome]

## Notes

- [Additional tips, warnings, or context]
- [Known limitations or edge cases]
"""

    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(template)

    console.print(f"Created skill '{skill_name}' successfully!", style=COLORS["primary"])
    console.print(f"Location: {skill_dir}\n", style=COLORS["dim"])
    console.print(
        "[dim]Edit the SKILL.md file to customize:\n"
        "  1. Update the description in YAML frontmatter\n"
        "  2. Fill in the instructions and examples\n"
        "  3. Add any supporting files (scripts, configs, etc.)\n"
        "\n"
        f"  Open: {skill_md}\n",
        style=COLORS["dim"],
    )


def _info(skill_name: str, agent: str) -> None:
    """Show detailed information about a specific skill.

    Args:
        skill_name: Name of the skill to show info for.
        agent: Agent identifier for skills.
    """
    user_skills_dir = _get_user_skills_dir(agent)
    project_skills_dir = _find_project_skills_dir()
    bundled_skills_dir = get_bundled_skills_dir()

    # Load skills
    skills = list_skills(
        bundled_skills_dir=bundled_skills_dir,
        user_skills_dir=user_skills_dir,
        project_skills_dir=project_skills_dir,
    )

    # Find the skill
    skill = next((s for s in skills if s["name"] == skill_name), None)

    if not skill:
        console.print(f"[bold red]Error:[/bold red] Skill '{skill_name}' not found.")
        console.print("\n[dim]Available skills:[/dim]", style=COLORS["dim"])
        for s in skills:
            console.print(f"  - {s['name']}", style=COLORS["dim"])
        return

    # Read the full SKILL.md file
    skill_path = Path(skill["path"])
    skill_content = skill_path.read_text()

    # Determine source label and color
    source_labels = {
        "bundled": ("Bundled Skill", "magenta"),
        "user": ("User Skill", "cyan"),
        "project": ("Project Skill", "green"),
    }
    source_label, source_color = source_labels.get(skill["source"], ("Unknown", "white"))

    console.print(
        f"\n[bold]Skill: {skill['name']}[/bold] [bold {source_color}]({source_label})[/bold {source_color}]\n",
        style=COLORS["primary"],
    )
    console.print(f"[bold]Description:[/bold] {skill['description']}\n", style=COLORS["dim"])
    console.print(f"[bold]Location:[/bold] {skill_path.parent}/\n", style=COLORS["dim"])

    # List supporting files
    skill_dir = skill_path.parent
    supporting_files = [f for f in skill_dir.iterdir() if f.name != "SKILL.md"]

    if supporting_files:
        console.print("[bold]Supporting Files:[/bold]", style=COLORS["dim"])
        for file in supporting_files:
            console.print(f"  - {file.name}", style=COLORS["dim"])
        console.print()

    # Show the full SKILL.md content
    console.print("[bold]Full SKILL.md Content:[/bold]\n", style=COLORS["primary"])
    console.print(skill_content, style=COLORS["dim"])
    console.print()


def setup_skills_parser(
    subparsers: Any,
) -> argparse.ArgumentParser:
    """Setup the skills subcommand parser with all its subcommands."""
    skills_parser = subparsers.add_parser(
        "skills",
        help="Manage agent skills",
        description="Manage agent skills - create, list, and view skill information",
    )
    skills_subparsers = skills_parser.add_subparsers(dest="skills_command", help="Skills command")

    # Skills list
    list_parser = skills_subparsers.add_parser(
        "list", help="List all available skills", description="List all available skills"
    )
    list_parser.add_argument(
        "--agent",
        default="migration-planner",
        help="Agent identifier for skills (default: migration-planner)",
    )

    # Skills create
    create_parser = skills_subparsers.add_parser(
        "create",
        help="Create a new skill",
        description="Create a new skill with a template SKILL.md file",
    )
    create_parser.add_argument("name", help="Name of the skill to create (e.g., web-research)")
    create_parser.add_argument(
        "--agent",
        default="migration-planner",
        help="Agent identifier for skills (default: migration-planner)",
    )

    # Skills info
    info_parser = skills_subparsers.add_parser(
        "info",
        help="Show detailed information about a skill",
        description="Show detailed information about a specific skill",
    )
    info_parser.add_argument("name", help="Name of the skill to show info for")
    info_parser.add_argument(
        "--agent",
        default="migration-planner",
        help="Agent identifier for skills (default: migration-planner)",
    )

    return skills_parser


def execute_skills_command(args: argparse.Namespace) -> None:
    """Execute skills subcommands based on parsed arguments.

    Args:
        args: Parsed command line arguments with skills_command attribute
    """
    # validate agent argument
    if hasattr(args, "agent") and args.agent:
        is_valid, error_msg = _validate_name(args.agent)
        if not is_valid:
            console.print(f"[bold red]Error:[/bold red] Invalid agent name: {error_msg}")
            console.print(
                "[dim]Agent names must only contain letters, numbers, hyphens, and underscores.[/dim]",
                style=COLORS["dim"],
            )
            return

    if args.skills_command == "list":
        _list(agent=args.agent)
    elif args.skills_command == "create":
        _create(args.name, agent=args.agent)
    elif args.skills_command == "info":
        _info(args.name, agent=args.agent)
    else:
        # No subcommand provided, show help
        console.print("[yellow]Please specify a skills subcommand: list, create, or info[/yellow]")
        console.print("\n[bold]Usage:[/bold]", style=COLORS["primary"])
        console.print("  deepmig skills <command> [options]\n")
        console.print("[bold]Available commands:[/bold]", style=COLORS["primary"])
        console.print("  list              List all available skills")
        console.print("  create <name>     Create a new skill")
        console.print("  info <name>       Show detailed information about a skill")
        console.print("\n[bold]Examples:[/bold]", style=COLORS["primary"])
        console.print("  deepmig skills list")
        console.print("  deepmig skills create databricks-execution")
        console.print("  deepmig skills info databricks-execution")
        console.print("\n[dim]For more help on a specific command:[/dim]", style=COLORS["dim"])
        console.print("  deepmig skills <command> --help", style=COLORS["dim"])


__all__ = [
    "execute_skills_command",
    "setup_skills_parser",
]
