"""Code Quality Reviewer - Specialized agent for code quality analysis.

This agent focuses on code complexity, readability, best practices,
and overall code quality issues.
"""
from typing import List
from ..specialized_agent import SpecializedAgent, Finding


class QualityReviewer(SpecializedAgent):
    """Specialized agent for analyzing code quality and readability."""
    
    def initialize(self) -> None:
        """Initialize LLM client for quality analysis."""
        cfg = self.config or {}
        
        from ...llm import get_llm_client_from_config
        self.client = get_llm_client_from_config(cfg)
    
    def analyze(self, code: str, context: Optional[str] = None) -> List[Finding]:
        """Analyze code for quality issues.
        
        Args:
            code: Python source code to analyze
            context: Optional context or additional information for analysis.
            
        Returns:
            List of Finding objects related to code quality
        """
        system_prompt = {
            "role": "system",
            "content": """You are a code quality expert. Analyze code for quality and best practices ONLY.

Focus on:
1. Code complexity (functions too long, too many nested loops)
2. Readability (unclear logic, missing comments for complex parts)
3. Best practices (using with for file operations, proper exception handling)
4. Code smells (duplicated logic within this code, magic numbers)
5. Pythonic patterns (list comprehensions instead of loops where appropriate)

For EACH quality issue found, respond with this EXACT format:
Category: Code Quality
Severity: [low/medium/high]
Description: [explain the quality issue]
Location: [line X or function name]
Fix: [how to improve]
Confidence: [0.0-1.0]

Only report actual quality problems. If code quality is good, respond with "No quality issues found."
"""
        }
        
        prompt_content = f"Analyze this Python code for quality issues:\n\n```python\n{code}\n```"
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
        if "no quality issues" in response.lower() or "no issues found" in response.lower():
            return []
        
        # Parse findings from response
        findings = self._parse_llm_response(response, code)
        
        # Ensure all findings have correct category
        for finding in findings:
            finding.category = "Code Quality"
        
        return findings
