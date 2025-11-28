"""LLM Package - Centralized LLM provider management.

This package provides a unified interface for working with different LLM providers
(OpenAI, Bytez, local models) across the entire project.

IMPORTANT: All agents should use the factory pattern to get LLM clients,
NOT create LLMClient instances directly.

Recommended Usage:
    from src.llm import get_llm_client
    
    client = get_llm_client()  # Uses global config
    response = client.chat(messages)

Configuration:
    Set LLM_PROVIDER environment variable or DEFAULT_PROVIDER in config/default_config.py
    Options: "openai", "bytez", "local"
"""
from .client import LLMClient
from .factory import (
    get_llm_client,
    get_llm_client_from_config,
    get_provider,
    get_model_name,
    get_llm_info
)

__all__ = [
    "LLMClient",
    "get_llm_client",
    "get_llm_client_from_config",
    "get_provider",
    "get_model_name",
    "get_llm_info"
]
