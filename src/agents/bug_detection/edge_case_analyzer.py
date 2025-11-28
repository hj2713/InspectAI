"""Edge Case Analyzer - Specialized agent for finding edge case vulnerabilities.

This agent focuses on null/None checks, boundary conditions, empty collections,
and other edge cases that could cause runtime errors.
"""
from typing import List
from ..specialized_agent import SpecializedAgent, Finding


class EdgeCaseAnalyzer(SpecializedAgent):
    """Specialized agent for analyzing edge case handling."""
    
    def initialize(self) -> None:
        """Initialize LLM client for edge case analysis."""
        cfg = self.config or {}
        
        from ...llm import get_llm_client_from_config
        self.client = get_llm_client_from_config(cfg)
    
    def analyze(self, code: str) -> List[Finding]:
        """Analyze code for edge case vulnerabilities.
        
        Args:
            code: Python source code to analyze
            
        Returns:
            List of Finding objects related to edge cases
        """
        system_prompt = {
            "role": "system",
            "content": """You are an expert at finding edge case bugs. Analyze for edge case issues ONLY.

Focus on:
1. Missing None/null checks before using variables
2. Division by zero possibilities
3. Empty list/dict access without checking
4. Index out of bounds risks
5. String operations on empty strings
6. Missing error handling for external calls

For EACH edge case issue found, respond with this EXACT format:
Category: Edge Case
Severity: [medium/high/critical]
Description: [explain the edge case problem]
Location: [line X or function name]
Fix: [add check/handling for edge case]
Confidence: [0.0-1.0]

Only report actual edge case vulnerabilities. If edge cases are handled, respond with "No edge case issues found."
"""
        }
        
        user_prompt = {
            "role": "user",
            "content": f"Analyze this Python code for edge case issues:\n\n```python\n{code}\n```"
        }
        
        response = self.client.chat(
            [system_prompt, user_prompt],
            model=self.config.get("model"),
            temperature=self.config.get("temperature"),
            max_tokens=self.config.get("max_tokens")
        )
        
        # Check if no issues found
        if "no edge case" in response.lower() or "no issues found" in response.lower():
            return []
        
        # Parse findings from response
        findings = self._parse_llm_response(response, code)
        
        # Ensure all findings have correct category
        for finding in findings:
            finding.category = "Edge Case"
            # Edge case bugs can be critical
            if finding.severity == "low":
                finding.severity = "medium"
        
        return findings
