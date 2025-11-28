"""Naming Convention Reviewer - Specialized agent for PEP 8 naming analysis.

This agent focuses specifically on naming conventions, variable clarity,
and identifier quality in Python code.
"""
from typing import List
from ..specialized_agent import SpecializedAgent, Finding


class NamingReviewer(SpecializedAgent):
    """Specialized agent for analyzing naming conventions and variable clarity."""
    
    def initialize(self) -> None:
        """Initialize LLM client for naming analysis."""
        from ...llm import get_llm_client_from_config
        
        cfg = self.config or {}
        self.client = get_llm_client_from_config(cfg)
    
    def analyze(self, code: str) -> List[Finding]:
        """Analyze code for naming convention issues.
        
        Args:
            code: Python source code to analyze
            
        Returns:
            List of Finding objects related to naming
        """
        system_prompt = {
            "role": "system",
            "content": """You are a Python naming convention expert. Analyze code ONLY for naming issues.

Focus on:
1. PEP 8 naming conventions (snake_case for functions/variables, PascalCase for classes)
2. Variable name clarity and descriptiveness  
3. Avoiding single-letter names (except loop counters i, j, k)
4. Boolean names should be clear (is_, has_, can_, etc.)
5. Constant names should be UPPER_CASE

For EACH naming issue found, respond with this EXACT format:
Category: Naming Convention
Severity: [low/medium/high]
Description: [what's wrong with the name]
Location: [line X or function/variable name]
Fix: [specific suggestion for better name]
Confidence: [0.0-1.0]

Only report actual naming problems. If names are fine, respond with "No naming issues found."
"""
        }
        
        user_prompt = {
            "role": "user",
            "content": f"Analyze this Python code for naming convention issues:\n\n```python\n{code}\n```"
        }
        
        response = self.client.chat(
            [system_prompt, user_prompt],
            model=self.config.get("model"),
            temperature=self.config.get("temperature"),
            max_tokens=self.config.get("max_tokens")
        )
        
        # Check if no issues found
        if "no naming issues" in response.lower() or "no issues found" in response.lower():
            return []
        
        # Parse findings from response
        findings = self._parse_llm_response(response, code)
        
        # Ensure all findings have correct category
        for finding in findings:
            finding.category = "Naming Convention"
        
        return findings
