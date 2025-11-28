"""Dependency Vulnerability Scanner - Specialized security agent.

This agent focuses on detecting usage of known vulnerable dependencies
and insecure library usage patterns.
"""
from typing import List
from ..specialized_agent import SpecializedAgent, Finding


class DependencyScanner(SpecializedAgent):
    """Specialized agent for detecting dependency-related security issues."""
    
    def initialize(self) -> None:
        """Initialize LLM client for dependency scanning."""
        cfg = self.config or {}
        provider = cfg.get("provider", "openai")
        
        from ...llm.client import LLMClient
        self.client = LLMClient(
            default_temperature=cfg.get("temperature", 0.1),
            default_max_tokens=cfg.get("max_tokens", 1024),
            provider=provider
        )
    
    def analyze(self, code: str) -> List[Finding]:
        """Analyze code for dependency security issues.
        
        Args:
            code: Python source code to analyze
            
        Returns:
            List of Finding objects related to dependency issues
        """
        system_prompt = {
            "role": "system",
            "content": """You are a security expert specializing in dependency security. Analyze for dependency security issues ONLY.

Focus on:
1. Use of deprecated/unsafe functions (e.g., pickle.loads, eval, exec)
2. Insecure deserialization patterns
3. Known vulnerable library usage patterns
4. Unsafe XML parsing (XXE vulnerabilities)
5. Use of weak cryptographic functions (MD5, SHA1 for security)

For EACH dependency security issue found, respond with this EXACT format:
Category: Dependency/Library Security
Severity: [medium/high/critical]
Description: [explain the security risk with this library/function usage]
Location: [line X or import statement]
Fix: [use safer alternative or updated version]
Confidence: [0.0-1.0]

Only report actual dependency security issues. If dependencies are used safely, respond with "No dependency issues found."
"""
        }
        
        user_prompt = {
            "role": "user",
            "content": f"Analyze this Python code for dependency security issues:\n\n```python\n{code}\n```"
        }
        
        response = self.client.chat(
            [system_prompt, user_prompt],
            model=self.config.get("model"),
            temperature=self.config.get("temperature"),
            max_tokens=self.config.get("max_tokens")
        )
        
        # Check if no issues found
        if "no dependency issues" in response.lower() or "no issues found" in response.lower():
            return []
        
        # Parse findings from response
        findings = self._parse_llm_response(response, code)
        
        # Ensure all findings have correct category
        for finding in findings:
            finding.category = "Dependency/Library Security"
            # Dependency issues can be critical
            if finding.severity == "low":
                finding.severity = "medium"
        
        return findings
