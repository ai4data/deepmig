"""DeepMig CLI - Entry point for the migration agent.

This module provides the command-line interface for DeepMig.
It creates its own agent with custom migration tools.
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# Load .env file from current directory
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, rely on system env vars

import inspect

import shutil
from deepagents_cli.agent import list_agents, reset_agent as _reset_agent
from deepagents_cli.config import COLORS, SessionState, console
from rich.console import Console
from deepagents_cli.main import check_cli_dependencies

# Override colors with Metazense brand palette
COLORS.update({
    "primary": "#8142ff",    # Metazense primary purple
    "dim": "#706d72",        # Grey3 - secondary text
    "user": "#ffffff",       # White
    "agent": "#aa80ff",      # Purple-dark - agent output (softer for readability)
    "thinking": "#969499",   # Grey4 - thinking/processing
    "tool": "#8142ff",       # Primary purple - tool calls
})

from deepagents_cli.token_utils import calculate_baseline_tokens as _calculate_baseline_tokens
from deepagents_cli.ui import show_help


def calculate_baseline_tokens(model, agent_dir: Path, system_prompt: str, assistant_id: str) -> int:
    """Wrapper for calculate_baseline_tokens that handles different API versions."""
    sig = inspect.signature(_calculate_baseline_tokens)
    if len(sig.parameters) >= 4:
        # Official version: (model, agent_dir, system_prompt, assistant_id)
        return _calculate_baseline_tokens(model, agent_dir, system_prompt, assistant_id)
    else:
        # Older version: (model, agent_dir, system_prompt)
        return _calculate_baseline_tokens(model, agent_dir, system_prompt)


def reset_agent(agent_name: str, source_agent: str | None = None, hard: bool = False) -> None:
    """Reset an agent, optionally with hard delete.

    Args:
        agent_name: Name of the agent to reset
        source_agent: Optional source agent to copy prompt from
        hard: If True, delete everything including memories folder
    """
    if hard:
        agent_dir = Path.home() / ".deepagents" / agent_name
        if agent_dir.exists():
            shutil.rmtree(agent_dir)
            console.print(f"[bold green][+] Hard reset complete:[/bold green] Deleted {agent_dir}")
        else:
            console.print(f"[yellow]Agent '{agent_name}' not found at {agent_dir}[/yellow]")
    else:
        _reset_agent(agent_name, source_agent)


def _upload_config_to_databricks(
    agent_name: str,
    config: dict,
    config_file: Path,
    console: Console,
) -> None:
    """Upload config file to Databricks workspace for cluster-executed scripts.

    Args:
        agent_name: Name of the agent (used in workspace path)
        config: Parsed migration config dict
        config_file: Path to the local config file
        console: Rich console for output
    """
    try:
        from databricks.sdk import WorkspaceClient

        # Get credentials from config
        credentials = config.get("credentials", {}).get("databricks", {})
        workspace_url = config.get("target", {}).get("workspace_url")
        token = credentials.get("personal_access_token")

        if not workspace_url or not token:
            console.print("  [yellow]Skipping Databricks upload: missing workspace_url or token in config[/yellow]")
            return

        console.print()
        console.print("[bold]Uploading config to Databricks workspace...[/bold]")

        # Create workspace client
        client = WorkspaceClient(host=workspace_url, token=token)

        # Target path in workspace: /Workspace/Shared/{agent_name}/config/migration_config.json
        workspace_path = f"/Workspace/Shared/{agent_name}/config/migration_config.json"

        # Read config file content
        with open(config_file, "rb") as f:
            content = f.read()

        # Upload to workspace using the Files API for workspace files
        # First, try to create parent directory (ignore if exists)
        try:
            client.workspace.mkdirs(f"/Workspace/Shared/{agent_name}/config")
        except Exception:
            pass  # Directory may already exist

        # Use workspace.import_ for files (with AUTO format for JSON)
        from databricks.sdk.service.workspace import ImportFormat
        import base64

        client.workspace.import_(
            path=workspace_path,
            content=base64.b64encode(content).decode("utf-8"),
            format=ImportFormat.AUTO,
            overwrite=True,
        )

        console.print(f"  [green]+[/green] Uploaded config to {workspace_path}")
        console.print(f"  [dim]Cluster scripts can read config from: {workspace_path}[/dim]")

    except ImportError:
        console.print("  [yellow]Skipping Databricks upload: databricks-sdk not installed[/yellow]")
    except Exception as e:
        console.print(f"  [yellow]Warning: Could not upload to Databricks: {e}[/yellow]")
        console.print("  [dim]You may need to manually upload the config later[/dim]")


def init_project(
    agent_name: str,
    project_dir: str = ".",
    source_type: str | None = None,
    target_platform: str | None = None,
    input_path: str | None = None,
) -> None:
    """Initialize a new DeepMig migration project.

    Creates the project structure, config files, and symlinks to agent memories.

    Args:
        agent_name: Name of the agent/project
        project_dir: Directory to create project in
        source_type: Source system type (if None, prompt interactively)
        target_platform: Target platform (if None, prompt interactively)
        input_path: Path to existing input folder to copy (optional)
    """
    from prompt_toolkit import prompt
    from prompt_toolkit.shortcuts import radiolist_dialog

    project_path = Path(project_dir).resolve()
    agent_dir = Path.home() / ".deepagents" / agent_name
    memories_dir = agent_dir / "memories"
    # /memories/ is a virtual route that maps to agent_dir/memories/
    # So /memories/input/ maps to agent_dir/memories/input/
    # Files MUST live inside memories_dir for virtual_mode security checks
    agent_input_path = memories_dir / "input"
    # Project symlink points TO agent directory (not the other way around)
    project_symlink_path = project_path / "input"

    # Check if project already exists
    if agent_input_path.exists():
        console.print(f"[yellow]Warning: {agent_input_path} already exists[/yellow]")
        response = prompt("Overwrite? [y/N]: ").strip().lower()
        if response != "y":
            console.print("[dim]Aborted.[/dim]")
            return

    console.print(DEEPMIG_ASCII)
    console.print()
    console.print("[bold]Initializing new migration project...[/bold]", style=COLORS["primary"])
    console.print()

    # Interactive prompts if not provided via CLI
    source_options = [
        ("ssis", "SSIS (SQL Server Integration Services)"),
        ("informatica", "Informatica PowerCenter"),
        ("sql_server", "SQL Server (Stored Procedures/Views)"),
        ("sas", "SAS Data Integration"),
        ("oracle", "Oracle PL/SQL"),
        ("datastage", "IBM DataStage"),
        ("other", "Other"),
    ]

    target_options = [
        ("databricks", "Databricks (PySpark/Delta Lake)"),
        ("snowflake", "Snowflake (Snowpark/SQL)"),
        ("fabric", "Microsoft Fabric"),
        ("synapse", "Azure Synapse Analytics"),
        ("bigquery", "Google BigQuery"),
        ("redshift", "AWS Redshift"),
        ("other", "Other"),
    ]

    # Get project name (skip prompt if running in non-interactive mode with --input)
    console.print("[bold]Project Configuration[/bold]")
    console.print()
    if input_path and source_type and target_platform:
        # Non-interactive mode: use agent_name as project_name
        project_name = agent_name
        console.print(f"  Project name: {project_name}")
    else:
        project_name = prompt(f"  Project name [{agent_name}]: ").strip() or agent_name

    # Get source type
    if source_type is None:
        console.print()
        console.print("  [bold]Source system:[/bold]")
        for i, (key, label) in enumerate(source_options, 1):
            console.print(f"    {i}. {label}")
        while True:
            choice = prompt("  Select source [1-7]: ").strip()
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(source_options):
                    source_type = source_options[idx][0]
                    break
            except ValueError:
                pass
            console.print("  [red]Invalid choice[/red]")

    # Get target platform
    if target_platform is None:
        console.print()
        console.print("  [bold]Target platform:[/bold]")
        for i, (key, label) in enumerate(target_options, 1):
            console.print(f"    {i}. {label}")
        while True:
            choice = prompt("  Select target [1-7]: ").strip()
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(target_options):
                    target_platform = target_options[idx][0]
                    break
            except ValueError:
                pass
            console.print("  [red]Invalid choice[/red]")

    console.print()
    console.print("[bold]Creating project structure...[/bold]")

    # Create directory structure inside agent_dir (not project_path)
    # This is required because FilesystemBackend virtual_mode security
    # checks that resolved paths are inside the root directory
    dirs_to_create = [
        agent_input_path / "config",
        agent_input_path / "metadata",
        agent_input_path / "graph",
        agent_input_path / "codebase",
        project_path / "output",
    ]

    for dir_path in dirs_to_create:
        dir_path.mkdir(parents=True, exist_ok=True)
        try:
            rel_path = dir_path.relative_to(memories_dir)
            console.print(f"  [green]+[/green] Created ~/.deepagents/{agent_name}/memories/{rel_path}/")
        except ValueError:
            console.print(f"  [green]+[/green] Created {dir_path.relative_to(project_path)}/")

    # If input_path provided, copy existing input folder instead of creating template
    if input_path:
        input_source = Path(input_path).resolve()
        if not input_source.exists():
            console.print(f"  [red]Error: Input path does not exist: {input_source}[/red]")
            return

        console.print()
        console.print("[bold]Copying input folder...[/bold]")

        # Copy contents of input folder to agent_input_path
        for item in input_source.iterdir():
            dest = agent_input_path / item.name
            if item.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(item, dest)
                console.print(f"  [green]+[/green] Copied {item.name}/ -> ~/.deepagents/{agent_name}/memories/input/{item.name}/")
            else:
                shutil.copy2(item, dest)
                console.print(f"  [green]+[/green] Copied {item.name} -> ~/.deepagents/{agent_name}/memories/input/{item.name}")

        # Load the actual config to detect target platform and upload if Databricks
        config_file = agent_input_path / "config" / "migration_config.json"
        if config_file.exists():
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)

            # Override source/target from config if not specified via CLI
            if source_type is None:
                source_type = config.get("source", {}).get("type")
            if target_platform is None:
                target_platform = config.get("target", {}).get("platform")

            # Upload config to Databricks workspace if target is Databricks
            if target_platform == "databricks":
                _upload_config_to_databricks(agent_name, config, config_file, console)
        else:
            console.print(f"  [yellow]Warning: No migration_config.json found in input folder[/yellow]")
    else:
        # Create template migration_config.json
        config = {
            "project_name": project_name,
            "source": {
                "type": source_type,
                "connection": {
                    "_comment": "Add your source connection details here"
                }
            },
            "target": {
                "platform": target_platform,
                "connection": {
                    "_comment": "Add your target connection details here"
                }
            },
            "options": {
                "wave_size": 10,
                "parallel_jobs": 4
            }
        }

        config_file = agent_input_path / "config" / "migration_config.json"
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        console.print(f"  [green]+[/green] Created ~/.deepagents/{agent_name}/memories/input/config/migration_config.json")

    # Create deepmig.yaml project file
    project_config = f"""# DeepMig Project Configuration
agent: {agent_name}
input_dir: ./input
output_dir: ./output

# Source: {source_type}
# Target: {target_platform}
"""
    project_file = project_path / "deepmig.yaml"
    with open(project_file, "w", encoding="utf-8") as f:
        f.write(project_config)
    console.print(f"  [green]+[/green] Created deepmig.yaml")

    # Create symlink from project directory to agent directory
    # This allows users to access files from their project folder
    console.print()
    console.print("[bold]Setting up project symlink...[/bold]")

    # Remove existing symlink or directory if it exists in project path
    if project_symlink_path.exists() or project_symlink_path.is_symlink():
        if project_symlink_path.is_symlink():
            project_symlink_path.unlink()
        else:
            shutil.rmtree(project_symlink_path)

    # Create symlink: ./input -> ~/.deepagents/{agent}/memories/input
    try:
        if sys.platform == "win32":
            os.symlink(str(agent_input_path), str(project_symlink_path), target_is_directory=True)
        else:
            project_symlink_path.symlink_to(agent_input_path)
        console.print(f"  [green]+[/green] Linked ./input -> ~/.deepagents/{agent_name}/memories/input")
    except OSError as e:
        console.print(f"  [yellow]![/yellow] Could not create symlink: {e}")
        console.print(f"  [dim]You can access files directly at: ~/.deepagents/{agent_name}/memories/input/[/dim]")

    # Done!
    console.print()
    console.print("[bold green]Project initialized successfully![/bold green]")
    console.print()
    console.print("[bold]Next steps:[/bold]")
    console.print(f"  1. Add your legacy source files to: [cyan]./input/codebase/[/cyan]")
    console.print(f"     (or directly: ~/.deepagents/{agent_name}/memories/input/codebase/)")
    console.print(f"  2. Add schema metadata to: [cyan]./input/metadata/[/cyan]")
    console.print(f"  3. (Optional) Add dependency graph: [cyan]./input/graph/graph_summary.yaml[/cyan]")
    console.print(f"  4. Edit config if needed: [cyan]./input/config/migration_config.json[/cyan]")
    console.print()
    console.print(f"  Then run: [bold cyan]deepmig --agent {agent_name}[/bold cyan]")
    console.print()


from agent.agent import create_migration_agent
from agent.prompts import get_main_prompt
from mig_core import create_llm, print_provider_info
from mig_core.skills.commands import execute_skills_command, setup_skills_parser
from mig_core.session import load_state, get_resume_info, create_initial_state, save_state, WorkflowSession


# DeepMig ASCII banner - Metazense purple filled block letters
DEEPMIG_ASCII = """[bold #8142ff]
 ██████╗  ███████╗ ███████╗ ██████╗  ███╗   ███╗ ██╗  ██████╗
 ██╔══██╗ ██╔════╝ ██╔════╝ ██╔══██╗ ████╗ ████║ ██║ ██╔════╝
 ██║  ██║ █████╗   █████╗   ██████╔╝ ██╔████╔██║ ██║ ██║  ███╗
 ██║  ██║ ██╔══╝   ██╔══╝   ██╔═══╝  ██║╚██╔╝██║ ██║ ██║   ██║
 ██████╔╝ ███████╗ ███████╗ ██║      ██║ ╚═╝ ██║ ██║ ╚██████╔╝
 ╚═════╝  ╚══════╝ ╚══════╝ ╚═╝      ╚═╝     ╚═╝ ╚═╝  ╚═════╝
[/bold #8142ff]"""




def parse_args() -> argparse.Namespace:
    """Parse command line arguments for DeepMig.

    Returns:
        Parsed command line arguments.
    """
    parser = argparse.ArgumentParser(
        description="DeepMig - AI-powered ETL Migration Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # List command
    subparsers.add_parser("list", help="List all available agents")

    # Help command
    subparsers.add_parser("help", help="Show help information")

    # Reset command
    reset_parser = subparsers.add_parser("reset", help="Reset an agent")
    reset_parser.add_argument("--agent", required=True, help="Name of agent to reset")
    reset_parser.add_argument(
        "--target", dest="source_agent", help="Copy prompt from another agent"
    )
    reset_parser.add_argument(
        "--hard",
        action="store_true",
        help="Delete everything including /memories/ folder (default: preserves artifacts)"
    )

    # Init command
    init_parser = subparsers.add_parser("init", help="Initialize a new migration project")
    init_parser.add_argument("--agent", required=True, help="Name of the agent/project")
    init_parser.add_argument(
        "--dir",
        default=".",
        help="Directory to create project in (default: current directory)"
    )
    init_parser.add_argument(
        "--source",
        choices=["ssis", "informatica", "sql_server", "sas", "oracle", "datastage", "other"],
        help="Source system type (skip interactive prompt)"
    )
    init_parser.add_argument(
        "--target",
        choices=["databricks", "snowflake", "fabric", "synapse", "bigquery", "redshift", "other"],
        help="Target platform (skip interactive prompt)"
    )
    init_parser.add_argument(
        "--input",
        help="Path to existing input folder to copy (config, metadata, codebase)"
    )

    # Skills command
    setup_skills_parser(subparsers)

    # Providers command
    subparsers.add_parser("providers", help="List available LLM providers and current config")

    # Default interactive mode
    parser.add_argument(
        "--agent",
        default="migration-planner",
        help="Agent identifier for separate memory stores (default: migration-planner).",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Auto-approve tool usage without prompting (disables human-in-the-loop)",
    )

    return parser.parse_args()


async def run_deepmig_session(
    model: object,
    assistant_id: str,
    session_state: SessionState,
) -> None:
    """Create migration agent and run CLI session.

    Args:
        model: LLM model to use
        assistant_id: Agent identifier for memory storage
        session_state: Session state with auto-approve settings
    """
    # Create migration agent with sub-agents
    agent, composite_backend = create_migration_agent(
        model, assistant_id, auto_approve=session_state.auto_approve
    )

    # Calculate baseline token count for accurate token tracking
    agent_dir = Path.home() / ".deepagents" / assistant_id
    main_prompt = get_main_prompt()
    baseline_tokens = calculate_baseline_tokens(model, agent_dir, main_prompt, assistant_id)

    # Show DeepMig banner instead of default
    console.clear()
    console.print(DEEPMIG_ASCII)
    console.print()

    console.print("Ready to migrate! What would you like to do?", style=COLORS["agent"])
    console.print(f"  [dim]Working directory: {Path.cwd()}[/dim]")
    console.print()

    # Check for existing workflow state (resume capability)
    # Create initial state if it doesn't exist
    workflow_state = load_state(agent_dir)
    if workflow_state is None:
        workflow_state = create_initial_state()
        save_state(agent_dir, workflow_state)
        console.print(f"  [bold green][+] New workflow state created[/bold green]")
        console.print(f"  [dim]Starting fresh at: planning[/dim]")
        console.print()
    else:
        resume_info = get_resume_info(workflow_state)
        console.print(f"  [bold cyan][*] Session Resume Available[/bold cyan]")
        for line in resume_info.split("\n"):
            console.print(f"  [dim]{line}[/dim]")
        console.print()

    if session_state.auto_approve:
        console.print(
            "  [yellow][!] Auto-approve: ON[/yellow] [dim](tools run without confirmation)[/dim]"
        )
        console.print()

    console.print(
        "  Tips: Enter to submit, Alt+Enter for newline, Ctrl+C to interrupt",
        style=f"dim {COLORS['dim']}",
    )
    console.print()

    # Import and run the CLI loop directly (skip simple_cli's banner)
    from deepagents_cli.commands import execute_bash_command, handle_command
    from deepagents_cli.execution import execute_task
    from deepagents_cli.input import create_prompt_session
    from deepagents_cli.ui import TokenTracker

    session = create_prompt_session(assistant_id, session_state)
    token_tracker = TokenTracker()
    token_tracker.set_baseline(baseline_tokens)

    while True:
        try:
            user_input = await session.prompt_async()
            if session_state.exit_hint_handle:
                session_state.exit_hint_handle.cancel()
                session_state.exit_hint_handle = None
            session_state.exit_hint_until = None
            user_input = user_input.strip()
        except EOFError:
            break
        except KeyboardInterrupt:
            console.print("\nGoodbye!", style=COLORS["primary"])
            break

        if not user_input:
            continue

        # Check for slash commands first
        if user_input.startswith("/"):
            result = handle_command(user_input, agent, token_tracker)
            if result == "exit":
                console.print("\nGoodbye!", style=COLORS["primary"])
                break
            if result:
                continue

        # Check for bash commands (!)
        if user_input.startswith("!"):
            execute_bash_command(user_input)
            continue

        # Handle regular quit keywords
        if user_input.lower() in ["quit", "exit", "q"]:
            console.print("\nGoodbye!", style=COLORS["primary"])
            break

        # Execute with retry logic for transient API errors
        max_retries = 3
        for attempt in range(max_retries):
            try:
                await execute_task(
                    user_input, agent, assistant_id, session_state, token_tracker, backend=composite_backend
                )
                break  # Success, exit retry loop
            except ValueError as e:
                if "No generations found in stream" in str(e):
                    if attempt < max_retries - 1:
                        console.print(f"\n[yellow][!] API returned empty response. Retrying ({attempt + 2}/{max_retries})...[/yellow]")
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s, 4s
                    else:
                        console.print(f"\n[red][X] API error after {max_retries} attempts:[/red] {e}")
                        console.print("[dim]The session is still active. You can try again or type a different command.[/dim]\n")
                else:
                    raise  # Re-raise non-API errors
            except Exception as e:
                error_msg = str(e).lower()
                # Handle other transient errors (rate limits, timeouts, etc.)
                if any(term in error_msg for term in ["rate limit", "timeout", "connection", "503", "429"]):
                    if attempt < max_retries - 1:
                        wait_time = 2 ** (attempt + 1)
                        console.print(f"\n[yellow][!] Transient error: {e}. Retrying in {wait_time}s...[/yellow]")
                        await asyncio.sleep(wait_time)
                    else:
                        console.print(f"\n[red][X] Error after {max_retries} attempts:[/red] {e}")
                        console.print("[dim]The session is still active. You can try again.[/dim]\n")
                else:
                    # For unexpected errors, log but keep session alive
                    console.print(f"\n[red][X] Error:[/red] {e}")
                    console.print("[dim]The session is still active. You can try again or type /help for commands.[/dim]\n")
                    break


async def async_main(assistant_id: str, session_state: SessionState) -> None:
    """Async main entry point.

    Args:
        assistant_id: Agent identifier for memory storage
        session_state: Session state with auto-approve settings
    """
    try:
        # Use multi-provider LLM factory (reads from config.yaml or env)
        model = create_llm()
    except (ValueError, ImportError) as e:
        console.print(f"\n[bold red][X] LLM Configuration Error:[/bold red] {e}\n")
        console.print("[dim]Run 'deepmig providers' to see available providers and configuration.[/dim]")
        sys.exit(1)

    try:
        await run_deepmig_session(model, assistant_id, session_state)
    except KeyboardInterrupt:
        console.print("\n\n[yellow]Interrupted[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[bold red][X] Error:[/bold red] {e}\n")
        console.print_exception()
        sys.exit(1)


def main() -> None:
    """Entry point for DeepMig CLI."""
    # Check dependencies first
    check_cli_dependencies()

    try:
        args = parse_args()

        if args.command == "help":
            show_help()
        elif args.command == "list":
            list_agents()
        elif args.command == "reset":
            reset_agent(args.agent, args.source_agent, hard=args.hard)
        elif args.command == "init":
            init_project(
                agent_name=args.agent,
                project_dir=args.dir,
                source_type=args.source,
                target_platform=args.target,
                input_path=args.input,
            )
        elif args.command == "skills":
            execute_skills_command(args)
        elif args.command == "providers":
            print_provider_info()
        else:
            # Create session state from args
            session_state = SessionState(auto_approve=args.auto_approve)

            # Run the migration agent
            asyncio.run(async_main(args.agent, session_state))

    except KeyboardInterrupt:
        console.print("\n\n[yellow]Interrupted[/yellow]")
        sys.exit(0)


if __name__ == "__main__":
    main()
