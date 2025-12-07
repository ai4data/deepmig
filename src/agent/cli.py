"""DeepMig CLI - Entry point for the migration agent.

This module provides the command-line interface for DeepMig.
It creates its own agent with custom migration tools.
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Load .env file from current directory
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, rely on system env vars

from deepagents_cli.agent import list_agents, reset_agent
from deepagents_cli.config import COLORS, SessionState, console
from deepagents_cli.main import check_cli_dependencies
from deepagents_cli.token_utils import calculate_baseline_tokens
from deepagents_cli.ui import show_help

from agent.agent import create_migration_agent
from agent.prompts import get_main_prompt
from mig_core import create_llm, print_provider_info
from mig_core.skills.commands import execute_skills_command, setup_skills_parser
from mig_core.session import load_state, get_resume_info, create_initial_state, save_state


# DeepMig ASCII banner - ASCII-only for Windows compatibility
DEEPMIG_ASCII = """[bold #8142ff]
  ____  ______ ______ _____  __  __ _____ _____
 |  _ \\|  ____|  ____|  __ \\|  \\/  |_   _/ ____|
 | | | | |__  | |__  | |__) | \\  / | | || |  __
 | | | |  __| |  __| |  ___/| |\\/| | | || | |_ |
 | |_| | |____| |____| |    | |  | |_| || |__| |
 |____/|______|______|_|    |_|  |_|_____|\\_____|
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
    baseline_tokens = calculate_baseline_tokens(model, agent_dir, main_prompt)

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

        await execute_task(
            user_input, agent, assistant_id, session_state, token_tracker, backend=composite_backend
        )


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
