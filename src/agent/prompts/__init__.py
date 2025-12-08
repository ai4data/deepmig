"""DeepMig agent prompts.

This module provides Jinja2-based prompt templates for all DeepMig agents.
Templates are located in ./templates/ and can be customized with runtime variables.

Usage:
    from agent.prompts import get_main_prompt, get_planning_prompt

    # Simple usage (uses defaults from config/prompts.yaml)
    prompt = get_main_prompt()

    # With dynamic data
    prompt = get_main_prompt(skills_list=[{"name": "source-ssis", "description": "..."}])

    # Using the loader directly for more control
    from agent.prompts.loader import get_loader, init_loader
    loader = init_loader()  # Reset with current timestamp
    prompt = loader.get_main_prompt(custom_var="value")
"""

from .loader import (
    PromptLoader,
    get_loader,
    init_loader,
    reset_loader,
    get_main_prompt,
    get_planning_prompt,
    get_critique_prompt,
    get_code_prompt,
    get_validator_prompt,
)

__all__ = [
    "PromptLoader",
    "get_loader",
    "init_loader",
    "reset_loader",
    "get_main_prompt",
    "get_planning_prompt",
    "get_critique_prompt",
    "get_code_prompt",
    "get_validator_prompt",
]
