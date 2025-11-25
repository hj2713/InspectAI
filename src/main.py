"""Main entry point for the LLM-based multi-agent system."""
import os
from typing import Dict, Any

from dotenv import load_dotenv
from src.orchestrator.orchestrator import OrchestratorAgent
from config.default_config import ORCHESTRATOR_CONFIG

def main():
    # Load environment variables
    load_dotenv()
    
    # Load environment variables (e.g., OPENAI_API_KEY)
    load_dotenv()

    # Initialize orchestrator with default config
    import copy
    config = copy.deepcopy(ORCHESTRATOR_CONFIG)

    print("Select API Provider:")
    print("1. OpenAI (Production)")
    print("2. Bytez (Testing)")
    choice = input("Enter choice (1/2): ").strip()

    provider = "openai"
    if choice == "2":
        provider = "bytez"
        print("Using Bytez API (Testing Mode)")
    else:
        print("Using OpenAI API (Production Mode)")

    # Update config with provider
    for key in config:
        if isinstance(config[key], dict):
            config[key]["provider"] = provider

    orchestrator = OrchestratorAgent(config)

    # Example task: code improvement
    task = {
        "type": "code_improvement",
        "input": {
            "code": "def add(a, b): return a+b",
            "requirements": ["Add type hints", "Add docstring"]
        }
    }

    try:
        # Process the task
        result = orchestrator.process_task(task)
        print("Task completed:")
        # print summary pieces so output is human-friendly
        print("Analysis:\n", result.get("analysis", {}).get("analysis") if isinstance(result.get("analysis"), dict) else result.get("analysis"))
        print("Generated code:\n", result.get("generation", {}).get("generated_code"))
    finally:
        # Cleanup
        orchestrator.cleanup()

if __name__ == "__main__":
    main()