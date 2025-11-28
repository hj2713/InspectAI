"""Injection Vulnerability Scanner - Specialized security agent.

This agent focuses on detecting SQL injection, command injection, path traversal,
and other injection vulnerabilities.
"""
from typing import List
from ..specialized_agent import SpecializedAgent, Finding


class InjectionScanner(SpecializedAgent):
    """Specialized agent for detecting injection vulnerabilities."""
    
    def initialize(self) -> None:
        """Initialize LLM client for injection scanning."""
        cfg = self.config or {}
        
        from ...llm import get_llm_client_from_config
        self.client = get_llm_client_from_config(cfg)
    
    def analyze(self, code: str, context: Optional[str] = None) -> List[Finding]:
        """Analyze code for injection vulnerabilities.
        
        Args:
            code: Python source code to analyze
            
        Returns:
            List of Finding objects related to injection vulnerabilities
        """
        system_prompt = {
            "role": "system",
            "content": """You are a security expert specializing in injection attacks. Analyze for injection vulnerabilities ONLY.

Focus on:
1. SQL injection (string concatenation in SQL queries)
2. Command injection (os.system, subprocess with user input)
3. Path traversal (file operations with user-provided paths)
4. LDAP injection
5. NoSQL injection

For EACH injection vulnerability found, respond with this EXACT format:
Category: Injection Vulnerability
Severity: [high/critical]
Description: [explain the injection risk]
Location: [line X or function name]
Fix: [use parameterized queries, input validation, etc.]
Confidence: [0.0-1.0]

Only report actual injection risks. If code is safe, respond with "No injection vulnerabilities found."
"""
        }
        
        user_prompt = {
            "role": "user",
            "content": f"Analyze this Python code for injection vulnerabilities:\n\n```python\n{code}\n```"
        }
        
        response = self.client.chat(
            [system_prompt, user_prompt],
            model=self.config.get("model"),
            temperature=self.config.get("temperature"),
            max_tokens=self.config.get("max_tokens")
        )
        
        # Check if no issues found
        if "no injection" in response.lower() or "no vulnerabilities found" in response.lower():
            return []
        
        # Parse findings from response
        findings = self._parse_llm_response(response, code)
        
        # Ensure all findings have correct category and high severity
        for finding in findings:
            finding.category = "Injection Vulnerability"
            # Injection is always high or critical
            if finding.severity in ["low", "medium"]:
                finding.severity = "high"
        
        return findings
