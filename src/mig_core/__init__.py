"""MigCore - Core infrastructure for DeepMig migration agent."""

__version__ = "0.2.0"

from mig_core.llm import (
    LLMProvider,
    create_llm,
    get_available_providers,
    load_config,
    print_provider_info,
)

from mig_core.session import (
    # New class-based API
    WorkflowSession,
    WorkflowSessionManager,
    # Legacy function-based API (preserved for backward compatibility)
    WORKFLOW_STAGES,
    load_state,
    save_state,
    create_initial_state,
    advance_stage,
    record_attempt,
    record_error,
    should_reset_state,
    get_resume_info,
    format_state_for_prompt,
    compute_config_hash,
)

__all__ = [
    # LLM
    "LLMProvider",
    "create_llm",
    "get_available_providers",
    "load_config",
    "print_provider_info",
    # Session (new)
    "WorkflowSession",
    "WorkflowSessionManager",
    # Session (legacy)
    "WORKFLOW_STAGES",
    "load_state",
    "save_state",
    "create_initial_state",
    "advance_stage",
    "record_attempt",
    "record_error",
    "should_reset_state",
    "get_resume_info",
    "format_state_for_prompt",
    "compute_config_hash",
]
