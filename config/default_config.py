"""Default configuration for the Multi-Agent Code Review System.

IMPORTANT: This is the SINGLE SOURCE OF TRUTH for LLM provider configuration.
Change DEFAULT_PROVIDER here, and it affects the ENTIRE project automatically.

Supported Providers:
- "openai": OpenAI GPT models (requires OPENAI_API_KEY)
- "bytez": Bytez API (requires BYTEZ_API_KEY)
- "local": Local models via Bytez (Qwen, etc.)
"""

# ===================================================================================
# LLM PROVIDER CONFIGURATION - Change this ONE place to affect entire project
# ===================================================================================

DEFAULT_PROVIDER = "bytez"  # Options: "openai", "bytez"

# For OpenAI (when DEFAULT_PROVIDER = "openai")
OPENAI_MODEL = "gpt-4"  # or "gpt-3.5-turbo", "gpt-4-turbo", etc.

# For Bytez (when DEFAULT_PROVIDER = "bytez")
BYTEZ_MODEL = "ibm-granite/granite-4.0-h-tiny"  # Primary Bytez model

# ===================================================================================
# AGENT CONFIGURATIONS - These will automatically use DEFAULT_PROVIDER
# ===================================================================================

ORCHESTRATOR_CONFIG = {
    "research": {
        "temperature": 0.7,
        "max_tokens": 1024,
        "confidence_threshold": 0.5
    },
    "analysis": {
        "temperature": 0.2,
        "max_tokens": 1024,
        "confidence_threshold": 0.5  # For code review findings
    },
    "generation": {
        "temperature": 0.3,
        "max_tokens": 2048,
        "confidence_threshold": 0.5
    },
    "bug_detection": {
        "temperature": 0.1,
        "max_tokens":  1024,
        "confidence_threshold": 0.6  # Higher threshold for bug findings
    },
    "security": {
        "temperature": 0.1,
        "max_tokens": 1024,
        "confidence_threshold": 0.65  # Highest threshold for security findings
    },
    "test_generation": {
        "temperature": 0.3,
        "max_tokens": 2048,
        "confidence_threshold": 0.5
    },
    "documentation": {
        "temperature": 0.3,
        "max_tokens": 2048,
        "confidence_threshold": 0.5
    }
}

# Filter Pipeline Configuration
FILTER_CONFIG = {
    "confidence_threshold": 0.5,  # Default for code review
    "similarity_threshold": 85,  # For deduplication (0-100)
    "strict_evidence": False  # Set to True to require evidence for all findings
}

# Logging configuration
LOGGING_CONFIG = {
    "level": "INFO",
    "log_to_console": True,
    "log_to_file": True,
}

# GitHub configuration
GITHUB_CONFIG = {
    "api_timeout": 30,
    "max_files_per_pr": 50,
}
