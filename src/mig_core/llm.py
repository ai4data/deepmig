"""Multi-provider LLM factory for DeepMig.

Supports multiple LLM providers:
- Azure OpenAI (default, for enterprise)
- OpenAI (GPT-4, GPT-4o)
- Anthropic (Claude)
- Google (Gemini)
- Deepseek (Chinese, cost-effective)
- Alibaba Qwen/Tongyi (Chinese)
- Zhipu AI (Chinese, GLM models)

Configuration is loaded from:
1. config.yaml in current directory (highest priority)
2. ~/.deepagents/config.yaml (user-level)
3. Environment variables (fallback)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from langchain_core.language_models import BaseChatModel

# Provider type literals
LLMProvider = Literal[
    "azure",
    "openai",
    "anthropic",
    "google",
    "deepseek",
    "qwen",
    "zhipu",
]

# Default models per provider
DEFAULT_MODELS: dict[str, str] = {
    "azure": "",  # Uses deployment name from env
    "openai": "gpt-4o",
    "anthropic": "claude-sonnet-4-20250514",
    "google": "gemini-2.0-flash",
    "deepseek": "deepseek-chat",
    "qwen": "qwen-max",
    "zhipu": "glm-4-plus",
}


def load_config() -> dict[str, Any]:
    """Load configuration from config.yaml files.

    Searches in order (first found wins):
    1. ./config.yaml (project-level)
    2. ~/.deepagents/config.yaml (user-level)

    Returns:
        Configuration dictionary, empty if no config found.
    """
    search_paths = [
        Path.cwd() / "config.yaml",
        Path.home() / ".deepagents" / "config.yaml",
    ]

    for config_path in search_paths:
        if config_path.exists():
            try:
                with open(config_path, encoding="utf-8") as f:
                    config = yaml.safe_load(f) or {}
                    # Expand environment variables in string values
                    return _expand_env_vars(config)
            except (yaml.YAMLError, OSError):
                continue

    return {}


def _expand_env_vars(obj: Any) -> Any:
    """Recursively expand ${VAR} patterns in config values."""
    if isinstance(obj, str):
        # Handle ${VAR} and ${VAR:-default} patterns
        import re
        def replace_env(match: re.Match) -> str:
            var_expr = match.group(1)
            if ":-" in var_expr:
                var_name, default = var_expr.split(":-", 1)
                return os.environ.get(var_name, default)
            return os.environ.get(var_expr, match.group(0))
        return re.sub(r"\$\{([^}]+)\}", replace_env, obj)
    elif isinstance(obj, dict):
        return {k: _expand_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_expand_env_vars(item) for item in obj]
    return obj


def create_llm(
    provider: LLMProvider | None = None,
    model: str | None = None,
    **kwargs: Any,
) -> BaseChatModel:
    """Create an LLM instance based on provider configuration.

    Args:
        provider: LLM provider name. If None, reads from config or env.
        model: Model name/ID. If None, uses provider default.
        **kwargs: Additional provider-specific arguments.

    Returns:
        Configured LangChain chat model.

    Raises:
        ValueError: If provider is not supported or not configured.
        ImportError: If required provider package is not installed.

    Examples:
        # Use config.yaml settings
        llm = create_llm()

        # Override provider
        llm = create_llm(provider="anthropic", model="claude-sonnet-4-20250514")

        # Use OpenAI with custom temperature
        llm = create_llm(provider="openai", model="gpt-4o", temperature=0.7)
    """
    config = load_config()
    llm_config = config.get("llm", {})

    # Determine provider (argument > config > env > default)
    if provider is None:
        provider = llm_config.get("provider") or os.getenv("LLM_PROVIDER", "azure")

    # Determine model (argument > config > provider default)
    if model is None:
        model = llm_config.get("model") or DEFAULT_MODELS.get(provider, "")

    # Merge config kwargs with explicit kwargs (explicit wins)
    merged_kwargs = {**llm_config.get("options", {}), **kwargs}

    # Create provider-specific LLM
    if provider == "azure":
        return _create_azure_llm(model, **merged_kwargs)
    elif provider == "openai":
        return _create_openai_llm(model, **merged_kwargs)
    elif provider == "anthropic":
        return _create_anthropic_llm(model, **merged_kwargs)
    elif provider == "google":
        return _create_google_llm(model, **merged_kwargs)
    elif provider == "deepseek":
        return _create_deepseek_llm(model, **merged_kwargs)
    elif provider == "qwen":
        return _create_qwen_llm(model, **merged_kwargs)
    elif provider == "zhipu":
        return _create_zhipu_llm(model, **merged_kwargs)
    else:
        raise ValueError(
            f"Unsupported LLM provider: {provider}. "
            f"Supported: azure, openai, anthropic, google, deepseek, qwen, zhipu"
        )


def _create_azure_llm(model: str, **kwargs: Any) -> BaseChatModel:
    """Create Azure OpenAI LLM."""
    try:
        from langchain_openai import AzureChatOpenAI
    except ImportError as e:
        raise ImportError(
            "langchain-openai is required for Azure provider. "
            "Install with: pip install langchain-openai"
        ) from e

    # Accept both AZURE_OPENAI_DEPLOYMENT and AZURE_OPENAI_DEPLOYMENT_NAME
    deployment = (
        model
        or os.getenv("AZURE_OPENAI_DEPLOYMENT")
        or os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
    )
    if not deployment:
        raise ValueError(
            "Azure deployment not configured. Set AZURE_OPENAI_DEPLOYMENT or "
            "AZURE_OPENAI_DEPLOYMENT_NAME env var, or specify model in config.yaml"
        )

    return AzureChatOpenAI(
        azure_deployment=deployment,
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview"),
        **kwargs,
    )


def _create_openai_llm(model: str, **kwargs: Any) -> BaseChatModel:
    """Create OpenAI LLM."""
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as e:
        raise ImportError(
            "langchain-openai is required for OpenAI provider. "
            "Install with: pip install langchain-openai"
        ) from e

    return ChatOpenAI(
        model=model,
        **kwargs,
    )


def _create_anthropic_llm(model: str, **kwargs: Any) -> BaseChatModel:
    """Create Anthropic Claude LLM."""
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError as e:
        raise ImportError(
            "langchain-anthropic is required for Anthropic provider. "
            "Install with: pip install langchain-anthropic"
        ) from e

    return ChatAnthropic(
        model=model,
        **kwargs,
    )


def _create_google_llm(model: str, **kwargs: Any) -> BaseChatModel:
    """Create Google Gemini LLM."""
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ImportError as e:
        raise ImportError(
            "langchain-google-genai is required for Google provider. "
            "Install with: pip install langchain-google-genai"
        ) from e

    return ChatGoogleGenerativeAI(
        model=model,
        **kwargs,
    )


def _create_deepseek_llm(model: str, **kwargs: Any) -> BaseChatModel:
    """Create Deepseek LLM (uses OpenAI-compatible API)."""
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as e:
        raise ImportError(
            "langchain-openai is required for Deepseek provider. "
            "Install with: pip install langchain-openai"
        ) from e

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY environment variable is required")

    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url="https://api.deepseek.com/v1",
        **kwargs,
    )


def _create_qwen_llm(model: str, **kwargs: Any) -> BaseChatModel:
    """Create Alibaba Qwen/Tongyi LLM (uses OpenAI-compatible API)."""
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as e:
        raise ImportError(
            "langchain-openai is required for Qwen provider. "
            "Install with: pip install langchain-openai"
        ) from e

    api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY")
    if not api_key:
        raise ValueError(
            "DASHSCOPE_API_KEY or QWEN_API_KEY environment variable is required"
        )

    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        **kwargs,
    )


def _create_zhipu_llm(model: str, **kwargs: Any) -> BaseChatModel:
    """Create Zhipu AI GLM LLM (uses OpenAI-compatible API)."""
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as e:
        raise ImportError(
            "langchain-openai is required for Zhipu provider. "
            "Install with: pip install langchain-openai"
        ) from e

    api_key = os.getenv("ZHIPU_API_KEY")
    if not api_key:
        raise ValueError("ZHIPU_API_KEY environment variable is required")

    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url="https://open.bigmodel.cn/api/paas/v4",
        **kwargs,
    )


def get_available_providers() -> list[str]:
    """Get list of available LLM providers based on installed packages.

    Returns:
        List of provider names that have required packages installed.
    """
    available = []

    # Azure/OpenAI share the same package
    try:
        import langchain_openai  # noqa: F401
        available.extend(["azure", "openai", "deepseek", "qwen", "zhipu"])
    except ImportError:
        pass

    try:
        import langchain_anthropic  # noqa: F401
        available.append("anthropic")
    except ImportError:
        pass

    try:
        import langchain_google_genai  # noqa: F401
        available.append("google")
    except ImportError:
        pass

    return available


def print_provider_info() -> None:
    """Print information about available LLM providers."""
    available = get_available_providers()

    providers_info = {
        "azure": ("Azure OpenAI", "AZURE_OPENAI_DEPLOYMENT, AZURE_OPENAI_API_KEY"),
        "openai": ("OpenAI", "OPENAI_API_KEY"),
        "anthropic": ("Anthropic Claude", "ANTHROPIC_API_KEY"),
        "google": ("Google Gemini", "GOOGLE_API_KEY"),
        "deepseek": ("Deepseek", "DEEPSEEK_API_KEY"),
        "qwen": ("Alibaba Qwen/Tongyi", "DASHSCOPE_API_KEY or QWEN_API_KEY"),
        "zhipu": ("Zhipu AI GLM", "ZHIPU_API_KEY"),
    }

    print("\nAvailable LLM Providers:")
    print("-" * 50)

    for provider, (name, env_vars) in providers_info.items():
        status = "[+]" if provider in available else "[ ]"
        install_hint = "" if provider in available else " (install langchain package)"
        print(f"  {status} {provider}: {name}{install_hint}")
        print(f"      Env vars: {env_vars}")

    print("\nCurrent config:")
    config = load_config()
    llm_config = config.get("llm", {})
    current_provider = llm_config.get("provider") or os.getenv("LLM_PROVIDER", "azure")
    current_model = llm_config.get("model") or DEFAULT_MODELS.get(current_provider, "")
    print(f"  Provider: {current_provider}")
    print(f"  Model: {current_model or '(from env)'}")
