"""Jinja2 template loader for DeepMig prompt templates."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml
from jinja2 import Environment, FileSystemLoader


class PromptLoader:
    """Load and render Jinja2 prompt templates.

    Uses Jinja2's built-in template object caching for efficient
    repeated template lookups.

    Time is captured once at initialization to ensure consistent
    date values across all prompts (preserves input cache).
    """

    def __init__(
        self,
        templates_dir: Optional[Path] = None,
        session_start_time: Optional[datetime] = None,
    ):
        """Initialize the prompt loader.

        Args:
            templates_dir: Path to templates directory. Defaults to
                          ./templates relative to this file.
            session_start_time: Time to use for all prompts. If None,
                               captures current time at initialization.
        """
        self.templates_dir = templates_dir or Path(__file__).parent / "templates"
        # Capture session start time once at initialization for cache consistency
        self._session_start_time = session_start_time or datetime.now()
        self.env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )
        self._config = self._load_config()

    @property
    def session_date(self) -> str:
        """Get formatted session date (YYYY-MM-DD)."""
        return self._session_start_time.strftime("%Y-%m-%d")

    @property
    def session_datetime(self) -> str:
        """Get formatted session datetime (YYYY-MM-DD HH:MM:SS)."""
        return self._session_start_time.strftime("%Y-%m-%d %H:%M:%S")

    @property
    def session_start_time(self) -> datetime:
        """Get the raw session start time."""
        return self._session_start_time

    def _load_config(self) -> dict:
        """Load configuration from prompts.yaml."""
        config_path = Path(__file__).parent / "config" / "prompts.yaml"
        if config_path.exists():
            return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        return {}

    def render(self, template_name: str, **kwargs: Any) -> str:
        """Render a template with variables.

        Args:
            template_name: Path to template relative to templates_dir
            **kwargs: Variables to pass to the template

        Returns:
            Rendered template string
        """
        template = self.env.get_template(template_name)
        # Build context with session time, config defaults, then user overrides
        # Order: session time (lowest) -> config defaults -> kwargs (highest)
        context = {
            "date": self.session_date,
            "datetime": self.session_datetime,
            **self._config.get("defaults", {}),
            **kwargs,  # User can override date if needed
        }
        return template.render(**context)

    def get_main_prompt(self, **kwargs: Any) -> str:
        """Get the main DeepMig agent prompt.

        Args:
            **kwargs: Variables to pass to the template
                - skills_list: Optional list of available skills

        Returns:
            Rendered main agent prompt
        """
        return self.render("main.md.j2", **kwargs)

    def get_subagent_prompt(self, subagent_type: str, **kwargs: Any) -> str:
        """Get prompt for a sub-agent type.

        Args:
            subagent_type: Sub-agent type name (planning, critique, code, validator)
            **kwargs: Variables to pass to the template

        Returns:
            Rendered sub-agent prompt
        """
        return self.render(f"subagents/{subagent_type}.md.j2", **kwargs)

    def get_planning_prompt(self, **kwargs: Any) -> str:
        """Get the planning sub-agent prompt."""
        return self.get_subagent_prompt("planning", **kwargs)

    def get_critique_prompt(self, **kwargs: Any) -> str:
        """Get the critique sub-agent prompt."""
        return self.get_subagent_prompt("critique", **kwargs)

    def get_code_prompt(self, **kwargs: Any) -> str:
        """Get the code generation sub-agent prompt."""
        return self.get_subagent_prompt("code", **kwargs)

    def get_validator_prompt(self, **kwargs: Any) -> str:
        """Get the validation sub-agent prompt."""
        return self.get_subagent_prompt("validator", **kwargs)

    def get_component(self, component_name: str, **kwargs: Any) -> str:
        """Get a single component template.

        Args:
            component_name: Component name (input_context, final_reminder, etc.)
            **kwargs: Variables to pass to the template

        Returns:
            Rendered component string
        """
        return self.render(f"components/{component_name}.md.j2", **kwargs)


# Singleton instance
_loader: Optional[PromptLoader] = None


def get_loader(session_start_time: Optional[datetime] = None) -> PromptLoader:
    """Get the singleton PromptLoader instance.

    Args:
        session_start_time: Optional time to use if creating a new loader.
                           Ignored if loader already exists.

    Returns:
        The global PromptLoader instance
    """
    global _loader
    if _loader is None:
        _loader = PromptLoader(session_start_time=session_start_time)
    return _loader


def init_loader(session_start_time: Optional[datetime] = None) -> PromptLoader:
    """Initialize a new loader with a specific start time.

    This resets any existing loader and creates a new one with the
    specified start time. Use this at the start of a new session.

    Args:
        session_start_time: Time to use for all prompts. If None,
                           captures current time.

    Returns:
        The new PromptLoader instance
    """
    global _loader
    _loader = PromptLoader(session_start_time=session_start_time)
    return _loader


def reset_loader() -> None:
    """Reset the singleton loader (useful for testing)."""
    global _loader
    _loader = None


# Convenience functions for backward compatibility
def get_main_prompt(**kwargs: Any) -> str:
    """Get the main DeepMig agent prompt (backward compatible)."""
    return get_loader().get_main_prompt(**kwargs)


def get_planning_prompt(**kwargs: Any) -> str:
    """Get the planning sub-agent prompt (backward compatible)."""
    return get_loader().get_planning_prompt(**kwargs)


def get_critique_prompt(**kwargs: Any) -> str:
    """Get the critique sub-agent prompt (backward compatible)."""
    return get_loader().get_critique_prompt(**kwargs)


def get_code_prompt(**kwargs: Any) -> str:
    """Get the code generation sub-agent prompt (backward compatible)."""
    return get_loader().get_code_prompt(**kwargs)


def get_validator_prompt(**kwargs: Any) -> str:
    """Get the validation sub-agent prompt (backward compatible)."""
    return get_loader().get_validator_prompt(**kwargs)
