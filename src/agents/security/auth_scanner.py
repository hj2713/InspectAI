"""Authentication/Authorization Scanner - Specialized security agent.

This agent focuses on detecting authentication and authorization issues,
access control problems, and session management flaws.
"""
from typing import List
from ..specialized_agent import SpecializedAgent, Finding


class AuthScanner(SpecializedAgent):
    """Specialized agent for detecting authentication/authorization issues."""
    
    def initialize(self) -> None:
        """Initialize LLM client for auth scanning."""
        cfg = self.config or {}
        
        from ...llm import get_llm_client_from_config
        self.client = get_llm_client_from_config(cfg)
    
    def analyze(self, code: str, context: Optional[str] = None) -> List[Finding]:
        """Analyze code for authentication/authorization issues.
        
        Args:
            code: Python source code to analyze
            context: Optional additional context for the analysis (e.g., related code, configuration)
            
        Returns:
            List of Finding objects related to auth issues
        """
        system_prompt = {
            "role": "system",
            "content": """You are a security expert specializing in authentication/authorization. Analyze for auth issues ONLY.

Focus on:
1. Missing authentication checks before sensitive operations
2. Weak password policies or storage
3. Authorization bypass (accessing resources without permission checks)
4. Insecure session management
5. Missing access control checks

For EACH auth issue found, respond with this EXACT format:
Category: Authentication/Authorization
Severity: [medium/high/critical]
Description: [explain the auth security issue]
Location: [line X or function name]
Fix: [add auth checks, improve password handling, etc.]
Confidence: [0.0-1.0]

Only report actual auth issues. If auth is properly handled, respond with "No auth issues found."
"""
        }
        
        prompt_content = f"Analyze this Python code for authentication issues:\n\n```python\n{code}\n```"
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
        if "no auth issues" in response.lower() or "no issues found" in response.lower():
            return []
        
        # Parse findings from response
        findings = self._parse_llm_response(response, code)
        
        # Ensure all findings have correct category
        for finding in findings:
            finding.category = "Authentication/Authorization"
            # Auth issues are at least medium severity
            if finding.severity == "low":
                finding.severity = "medium"
        
        return findings
