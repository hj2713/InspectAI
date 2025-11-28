"""Main entry point for the LLM-based multi-agent system.

This module provides the main entry point for running the multi-agent
code review system. It supports various task types and LLM providers.

Usage:
    # Run directly
    python -m src.main
    
    # Use the CLI (recommended)
    python -m src.cli review myfile.py --type full_review
    python -m src.cli pr owner/repo 123
    python -m src.cli server --port 8000
"""
import os
import copy
from typing import Dict, Any

from dotenv import load_dotenv

from src.orchestrator.orchestrator import OrchestratorAgent
from src.utils.logger import setup_logging, get_logger
from config.default_config import ORCHESTRATOR_CONFIG


logger = get_logger(__name__)


def get_config(provider: str = None) -> Dict[str, Any]:
    """Get configuration for the orchestrator.
    
    Args:
        provider: LLM provider (openai, bytez, local)
        
    Returns:
        Configuration dictionary
    """
    config = copy.deepcopy(ORCHESTRATOR_CONFIG)
    
    provider = provider or os.getenv("LLM_PROVIDER", "bytez")
    
    for key in config:
        if isinstance(config[key], dict):
            config[key]["provider"] = provider
            if provider == "bytez":
                from config.default_config import BYTEZ_MODEL
                config[key]["model"] = BYTEZ_MODEL
            elif provider == "local":
                config[key]["use_local"] = True
    
    return config


def demo_code_improvement():
    """Demo: Code improvement task."""
    
    code = """
def calculate_average(numbers):
    total = 0
    for num in numbers:
        total += num
    return total / len(numbers)
"""
    
    config = get_config()
    orchestrator = OrchestratorAgent(config)
    
    try:
        task = {
            "type": "code_improvement",
            "input": {
                "code": code,
                "requirements": ["Add type hints", "Add docstring", "Handle edge cases"]
            }
        }
        
        result = orchestrator.process_task(task)
        
        print("\n📊 Analysis:")
        print(result.get("analysis", {}).get("analysis", "N/A"))
        
        print("\n✨ Improved Code:")
        print(result.get("generation", {}).get("generated_code", "N/A"))
        
    finally:
        orchestrator.cleanup()


def demo_full_review():
    
    code = """
def fetch_user(user_id):
    query = f"SELECT * FROM users WHERE id = {user_id}"
    return execute_query(query)

def process_data(data):
    result = eval(data)  # Security issue
    return result
"""
    
    config = get_config()
    orchestrator = OrchestratorAgent(config)
    
    try:
        task = {
            "type": "full_review",
            "input": {"code": code}
        }
        
        result = orchestrator.process_task(task)
        
        print("\n📊 Analysis Suggestions:")
        for sug in result.get("analysis", {}).get("suggestions", [])[:3]:
            print(f"  - {sug}")
        
        print(f"\n🐛 Bugs Found: {result.get('bug_report', {}).get('bug_count', 0)}")
        print(f"🔒 Security Issues: {result.get('security_report', {}).get('vulnerability_count', 0)}")
        print(f"⚠️ Risk Score: {result.get('security_report', {}).get('risk_score', 0)}/10")
        
    finally:
        orchestrator.cleanup()


def main():
    """Main entry point."""
    # Load environment variables
    load_dotenv()
    
    # Setup logging
    setup_logging(log_level=os.getenv("LOG_LEVEL", "INFO"))
    
    # Get provider from env
    provider = os.getenv("LLM_PROVIDER", "bytez")
    logger.info(f"Using LLM provider: {provider}")
    
    demo_code_improvement()


if __name__ == "__main__":
    main()
