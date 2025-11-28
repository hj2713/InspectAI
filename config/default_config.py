"""Default configuration for the Multi-Agent Code Review System."""

# LLM Provider Configuration
# Options: "openai", "bytez", "local" (for Qwen or other local models)
DEFAULT_PROVIDER = "local"  # Change to "openai" for production

# Qwen Model Configuration (adjust based on your model)
QWEN_MODEL_NAME = "qwen2.5-coder"  # or "qwen2.5" or specific model path

ORCHESTRATOR_CONFIG = {
    "research": {
        "model": QWEN_MODEL_NAME,
        "provider": DEFAULT_PROVIDER,
        "temperature": 0.7,
        "max_tokens": 1024,
        "confidence_threshold": 0.5
    },
    "analysis": {
        "model": QWEN_MODEL_NAME,
        "provider": DEFAULT_PROVIDER,
        "temperature": 0.2,
        "max_tokens": 1024,
        "confidence_threshold": 0.5  # For code review findings
    },
    "generation": {
        "model": QWEN_MODEL_NAME,
        "provider": DEFAULT_PROVIDER,
        "temperature": 0.3,
        "max_tokens": 2048,
        "confidence_threshold": 0.5
    },
    "bug_detection": {
        "model": QWEN_MODEL_NAME,
        "provider": DEFAULT_PROVIDER,
        "temperature": 0.1,
        "max_tokens": 1024,
        "confidence_threshold": 0.6  # Higher threshold for bug findings
    },
    "security": {
        "model": QWEN_MODEL_NAME,
        "provider": DEFAULT_PROVIDER,
        "temperature": 0.1,
        "max_tokens": 1024,
        "confidence_threshold": 0.65  # Highest threshold for security findings
    },
    "test_generation": {
        "model": QWEN_MODEL_NAME,
        "provider": DEFAULT_PROVIDER,
        "temperature": 0.3,
        "max_tokens": 2048,
        "confidence_threshold": 0.5
    },
    "documentation": {
        "model": QWEN_MODEL_NAME,
        "provider": DEFAULT_PROVIDER,
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
