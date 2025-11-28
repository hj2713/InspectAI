"""PEP 8 Compliance Reviewer - Specialized agent for style guide compliance.

This agent focuses on PEP 8 style guide violations beyond just naming,
including formatting, imports, and documentation.
"""
from typing import List
from ..specialized_agent import SpecializedAgent, Finding


class PEP8Reviewer(SpecializedAgent):
    """Specialized agent for analyzing PEP 8 compliance."""
    
    def initialize(self) -> None:
        """Initialize LLM client for PEP 8 analysis."""
        cfg = self.config or {}
        
        from ...llm import get_llm_client_from_config
        self.client = get_llm_client_from_config(cfg)
    
        """
        system_prompt = {
            "role": "system",
            "content": """You are a PEP 8 style guide expert. Analyze code for style violations ONLY.

Focus on:
1. Missing docstrings for modules, classes, functions
2. Import organization (stdlib, third-party, local)
3. Line length issues (over 79-100 characters)
4. Whitespace issues (spaces around operators, after commas)
5. Blank lines (2 before classes/functions at module level)

For EACH PEP 8 violation found, respond with this EXACT format:
Category: PEP 8 Style
Severity: [low/medium]
Description: [explain the PEP 8 violation]
Location: [line X or import section]
Fix: [how to fix per PEP 8]
Confidence: [0.0-1.0]

Only report actual PEP 8 violations. If code follows PEP 8, respond with "No PEP 8 violations found."
"""
        }
        
        prompt_content = f"Analyze this Python code for PEP 8 violations:\n\n```python\n{code}\n```"
        if context:
            prompt_content += f"\n\nAdditional Context:\n{context}"
            
        user_prompt = {
            "role": "user",
            "content": prompt_content
        }
        
        response = self.client.chat(
            [system_prompt, user_prompt],
            model=self.config.get("model"),
            temperature=self.config.get("temperature"),
            max_tokens=self.config.get("max_tokens")
        )
        
        # Check if no issues found
        if "no pep 8" in response.lower() or "no violations" in response.lower():
            return []
        
        # Parse findings from response
        findings = self._parse_llm_response(response, code)
        
        # Ensure all findings have correct category and low severity
        for finding in findings:
            finding.category = "PEP 8 Style"
            # Style issues are typically low severity
            if finding.severity in ["high", "critical"]:
                finding.severity = "low"
        
        return findings
