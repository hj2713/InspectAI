"""Centralized LLM Factory for Provider Management.

This module provides a single source of truth for LLM provider configuration.
ALL agents should use this factory to get LLM clients, ensuring consistency
across the entire project.

Usage:
    from src.llm.factory import get_llm_client
    
    # Get client with global defaults
    client = get_llm_client()
    
    # Override specific parameters
    client = get_llm_client(temperature=0.1, max_tokens=2048)
"""
import os
from typing import Optional
from .client import LLMClient


def get_provider() -> str:
    """Get the configured LLM provider from environment or config.
    
    Priority:
    1. Environment variable LLM_PROVIDER
    2. Config file DEFAULT_PROVIDER
    3. Fallback to "openai"
    
    Returns:
        Provider name ("openai", "bytez", or "local")
    """
    # Check environment first
    env_provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    if env_provider in ["openai", "bytez", "local"]:
        return env_provider
    
    # Fallback to config
    try:
        from config.default_config import DEFAULT_PROVIDER
        return DEFAULT_PROVIDER.lower()
    except ImportError:
        # Ultimate fallback
        return "openai"


def get_model_name(provider: Optional[str] = None) -> str:
    """Get the appropriate model name for the provider.
    
    Args:
        provider: Provider name (or None to use default)
        
    Returns:
        Model name string
    """
    provider = provider or get_provider()
    
    # Check environment overrides first
    env_model = os.getenv("LLM_MODEL", "").strip()
    if env_model:
        return env_model
    
    # Provider-specific defaults
    if provider == "openai":
        return os.getenv("OPENAI_MODEL", "gpt-4")
    elif provider in ["bytez", "local"]:
        # Try config first
        try:
            from config.default_config import QWEN_MODEL_NAME
            return QWEN_MODEL_NAME
        except ImportError:
            return "qwen2.5-coder"
    
    return "gpt-4"  # Ultimate fallback


def get_llm_client(
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    provider: Optional[str] = None
) -> LLMClient:
    """Factory function to create LLM clients with centralized configuration.
    
    This is the ONLY way agents should create LLM clients. It ensures:
    - Single source of truth for provider (OpenAI vs Bytez vs Local)
    - Consistent model selection across all agents
    - Easy switching between providers (change one place, affects everything)
    
    Args:
        model: Model name (None = auto-select based on provider)
        temperature: Sampling temperature (None = use defaults)
        max_tokens: Max tokens (None = use defaults)
        provider: Provider override (None = use global config)
        
    Returns:
        Configured LLMClient instance
        
    Examples:
        >>> # Use global defaults from config
        >>> client = get_llm_client()
        
        >>> # Override temperature for this specific agent
        >>> client = get_llm_client(temperature=0.1)
        
        >>> # Use different model but same provider
        >>> client = get_llm_client(model="gpt-3.5-turbo")
    """
    # Determine provider (priority: parameter > env > config > default)
    provider = provider or get_provider()
    
    # Determine model (priority: parameter > env > provider default)
    model = model or get_model_name(provider)
    
    # Set defaults if not provided
    if temperature is None:
        temperature = 0.2  # Conservative default for code analysis
    
    if max_tokens is None:
        max_tokens = 1024  # Reasonable default
    
    # Create and return client
    return LLMClient(
        default_model=model,
        default_temperature=temperature,
        default_max_tokens=max_tokens,
        provider=provider
    )


def get_llm_client_from_config(config: dict) -> LLMClient:
    """Create LLM client from an agent configuration dict.
    
    This is a convenience function for agents that receive configuration
    dicts from the orchestrator.
    
    Args:
        config: Agent configuration dictionary with optional keys:
            - model: Model name
            - temperature: Sampling temperature
            - max_tokens: Max tokens
            - provider: Provider name
            
    Returns:
        Configured LLMClient instance
        
    Example:
        >>> config = {"model": "gpt-4", "temperature": 0.1}
        >>> client = get_llm_client_from_config(config)
    """
    return get_llm_client(
        model=config.get("model"),
        temperature=config.get("temperature"),
        max_tokens=config.get("max_tokens"),
        provider=config.get("provider")
    )


# Convenience function for getting current provider info
def get_llm_info() -> dict:
    """Get information about the current LLM configuration.
    
    Useful for logging and debugging.
    
    Returns:
        Dictionary with provider, model, and config source
    """
    provider = get_provider()
    model = get_model_name(provider)
    
    # Determine config source
    config_source = "default"
    if os.getenv("LLM_PROVIDER"):
        config_source = "environment"
    else:
        try:
            from config.default_config import DEFAULT_PROVIDER
            config_source = "config file"
        except ImportError:
            pass
    
    return {
        "provider": provider,
        "model": model,
        "config_source": config_source,
        "openai_key_set": bool(os.getenv("OPENAI_API_KEY")),
        "bytez_key_set": bool(os.getenv("BYTEZ_API_KEY"))
    }
