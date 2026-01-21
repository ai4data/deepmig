"""Sub-agent definitions for DeepMig.

This module defines the specialized sub-agents that the main migration agent
can delegate tasks to: planning and critique agents.
"""

import os

from langchain_openai import AzureChatOpenAI

from agent.prompts import (
    get_code_prompt,
    get_code_review_prompt,
    get_critique_prompt,
    get_planning_prompt,
    get_validator_prompt,
)


def get_subagent_model(deployment_env_var: str):
    """Create Azure OpenAI model from environment variable.

    Args:
        deployment_env_var: Name of the environment variable containing the deployment name.

    Returns:
        AzureChatOpenAI instance or None if env var not set.
    """
    deployment = os.getenv(deployment_env_var)
    if not deployment:
        return None  # Will use default model from main agent

    return AzureChatOpenAI(
        azure_deployment=deployment,
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview"),
        # Note: temperature not set - some models (like o-series) only support default (1)
    )


def _create_subagent(
    name: str,
    description: str,
    system_prompt: str,
    model_env_var: str,
    tools: list | None = None,
) -> dict:
    """Create a subagent definition, only including model if set.

    Args:
        name: Subagent name
        description: Subagent description
        system_prompt: System prompt for the subagent
        model_env_var: Environment variable for the model deployment
        tools: Optional list of tools for the subagent

    Returns:
        Subagent dictionary (without model key if not configured)
    """
    agent = {
        "name": name,
        "description": description,
        "system_prompt": system_prompt,
    }
    model = get_subagent_model(model_env_var)
    if model is not None:
        agent["model"] = model
    if tools:
        agent["tools"] = tools
    return agent


def create_validator_agent_with_tools(tools: list) -> dict:
    """Create validator agent with execution tools.

    This is called from agent.py where the tools are available.

    Args:
        tools: List of execution tools (e.g., databricks_submit_job, databricks_run_sql)

    Returns:
        Validator agent definition with tools
    """
    return _create_subagent(
        name="validatorAgent",
        description=(
            "Expert QA engineer that validates migration scripts by executing them on "
            "the target platform and verifying data integrity. Validates data ingestion "
            "(source vs target comparison) and transformations (key integrity, "
            "referential integrity, data quality). Uploads code to target platform, executes it, "
            "and generates comprehensive validation reports. Adapts to platform from config. "
            "Pass the script content and validation configuration in the task description."
        ),
        system_prompt=get_validator_prompt(),
        model_env_var="AZURE_OPENAI_VALIDATOR_MODEL",
        tools=tools,
    )


# Planning sub-agent for migration analysis and planning
# Uses AZURE_OPENAI_PLANNING_MODEL if set
planning_agent = _create_subagent(
    name="planningAgent",
    description=(
        "Expert migration planner that analyzes legacy data systems and creates "
        "migration plans for modern platforms. Use when you need to analyze dependency graphs, "
        "identify ETL/data patterns, determine execution tiers, and create a phased "
        "migration plan. Adapts to source and target platforms from config. "
        "Pass the migration config and source metadata in the task description."
    ),
    system_prompt=get_planning_prompt(),
    model_env_var="AZURE_OPENAI_PLANNING_MODEL",
)

# Critique sub-agent for reviewing migration plans
# Uses AZURE_OPENAI_CRITIQUE_MODEL if set
critique_agent = _create_subagent(
    name="critiqueAgent",
    description=(
        "Expert reviewer that evaluates migration plans for completeness, accuracy, "
        "and feasibility. Use after creating a migration plan to get constructive "
        "feedback and suggestions for improvement. The agent will read the plan "
        "from /memories/migration_plan.md."
    ),
    system_prompt=get_critique_prompt(),
    model_env_var="AZURE_OPENAI_CRITIQUE_MODEL",
)

# Code generation sub-agent for creating migration scripts
# Uses AZURE_OPENAI_CODE_MODEL if set
code_agent = _create_subagent(
    name="codeAgent",
    description=(
        "Expert developer that generates production-ready migration code for the target platform. "
        "Creates data ingestion scripts (source → target) and transformation scripts "
        "(Bronze → Gold or similar patterns). Generates standalone scripts (PySpark, SQL, Python) "
        "based on target platform. Adapts to platform specifications from config. "
        "Pass the migration plan specification and configuration in the task description."
    ),
    system_prompt=get_code_prompt(),
    model_env_var="AZURE_OPENAI_CODE_MODEL",
)

# Code review sub-agent for validating generated code BEFORE execution
# Uses AZURE_OPENAI_CODE_REVIEW_MODEL if set
code_review_agent = _create_subagent(
    name="codeReviewAgent",
    description=(
        "Schema Guardian that validates generated migration code BEFORE execution. "
        "Performs static analysis to catch schema mismatches, cross-wave column name "
        "inconsistencies, syntax errors, and config violations. Use AFTER code generation "
        "but BEFORE submitting scripts to the cluster. Prevents broken code from wasting "
        "compute resources. Returns APPROVED, NEEDS_FIX, or REJECTED verdicts with "
        "specific fixes when issues are found."
    ),
    system_prompt=get_code_review_prompt(),
    model_env_var="AZURE_OPENAI_CODE_REVIEW_MODEL",
)

# Note: validator_agent is created dynamically in agent.py with tools
# Use create_validator_agent_with_tools() to create it with execution tools
