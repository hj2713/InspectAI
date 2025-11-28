"""Default configuration for the Multi-Agent Code Review System."""

ORCHESTRATOR_CONFIG = {
    "research": {
        "model": "gpt-4",
        "temperature": 0.7,
        "max_tokens": 1024
    },
    "analysis": {
        "model": "gpt-4",
        "temperature": 0.2,
        "max_tokens": 1024
    },
    "generation": {
        "model": "gpt-4",
        "temperature": 0.3,
        "max_tokens": 2048
    },
    "bug_detection": {
        "model": "gpt-4",
        "temperature": 0.1,
        "max_tokens": 1024
    },
    "security": {
        "model": "gpt-4",
        "temperature": 0.1,
        "max_tokens": 1024
    },
    "test_generation": {
        "model": "gpt-4",
        "temperature": 0.3,
        "max_tokens": 2048
    },
    "documentation": {
        "model": "gpt-4",
        "temperature": 0.3,
        "max_tokens": 2048
    }
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
