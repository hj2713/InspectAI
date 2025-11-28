#!/usr/bin/env python3
"""Script to update all specialized agents to use LLM factory pattern."""

import os
import re

# Files to update (all specialized agents)
files_to_update = [
    "src/agents/code_review/quality_reviewer.py",
    "src/agents/code_review/duplication_detector.py",
    "src/agents/code_review/pep8_reviewer.py",
    "src/agents/bug_detection/logic_error_detector.py",
    "src/agents/bug_detection/edge_case_analyzer.py",
    "src/agents/bug_detection/type_error_detector.py",
    "src/agents/bug_detection/runtime_issue_detector.py",
    "src/agents/security/injection_scanner.py",
    "src/agents/security/auth_scanner.py",
    "src/agents/security/data_exposure_scanner.py",
    "src/agents/security/dependency_scanner.py",
]

# Pattern to find and replace
old_pattern = r'''    def initialize\(self\) -> None:
        """Initialize LLM client.*?"""
        cfg = self\.config or \{\}
        provider = cfg\.get\("provider", "openai"\)
        
        from \.\.\.llm\.client import LLMClient
        self\.client = LLMClient\(
            default_temperature=cfg\.get\("temperature", 0\.\d+\),
            default_max_tokens=cfg\.get\("max_tokens", \d+\),
            provider=provider
        \)'''

new_code = '''    def initialize(self) -> None:
        """Initialize LLM client."""
        from ...llm import get_llm_client_from_config
        
        cfg = self.config or {}
        self.client = get_llm_client_from_config(cfg)'''

def update_file(filepath):
    """Update a single file to use factory pattern."""
    if not os.path.exists(filepath):
        print(f"Skipping {filepath} (not found)")
        return False
        
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Use regex to replace
    new_content = re.sub(old_pattern, new_code, content, flas=re.DOTALL)
    
    if new_content != content:
        with open(filepath, 'w') as f:
            f.write(new_content)
        print(f"✓ Updated {filepath}")
        return True
    else:
        print(f"✗ No changes needed in {filepath}")
        return False

if __name__ == "__main__":
    updated = 0
    for filepath in files_to_update:
        if update_file(filepath):
            updated += 1
    
    print(f"\n{updated}/{len(files_to_update)} files updated")
