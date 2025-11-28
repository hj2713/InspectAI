"""Data Exposure Scanner - Specialized security agent.

This agent focuses on detecting hardcoded credentials, sensitive data leaks,
and improper data handling that could expose confidential information.
"""
from typing import List
from ..specialized_agent import SpecializedAgent, Finding


class DataExposureScanner(SpecializedAgent):
    """Specialized agent for detecting data exposure risks."""
    
    def initialize(self) -> None:
        """Initialize LLM client for data exposure scanning."""
        cfg = self.config or {}
        provider = cfg.get("provider", "openai")
        
        from ...llm import get_llm_client_from_config
        self.client = get_llm_client_from_config(cfg)
            default_max_tokens=cfg.get("max_tokens", 1024),
            provider=provider
        )
    
    def analyze(self, code: str) -> List[Finding]:
        """Analyze code for data exposure risks.
        
        Args:
            code: Python source code to analyze
            
        Returns:
            List of Finding objects related to data exposure
        """
        system_prompt = {
            "role": "system",
            "content": """You are a security expert specializing in data protection. Analyze for data exposure risks ONLY.

Focus on:
1. Hardcoded passwords, API keys, secrets in code
2. Sensitive data in logs or error messages
3. Unencrypted sensitive data storage
4. Exposing internal paths/structure in responses
5. PII (personally identifiable information) leaks

For EACH data exposure issue found, respond with this EXACT format:
Category: Data Exposure
Severity: [medium/high/critical]
Description: [explain what sensitive data is exposed]
Location: [line X or variable name]
Fix: [use environment variables, encrypt data, etc.]
Confidence: [0.0-1.0]

Only report actual data exposure risks. If data is properly protected, respond with "No data exposure found."
"""
        }
        
        user_prompt = {
            "role": "user",
            "content": f"Analyze this Python code for data exposure risks:\n\n```python\n{code}\n```"
        }
        
        response = self.client.chat(
            [system_prompt, user_prompt],
            model=self.config.get("model"),
            temperature=self.config.get("temperature"),
            max_tokens=self.config.get("max_tokens")
        )
        
        # Check if no issues found
        if "no data exposure" in response.lower() or "no exposure found" in response.lower():
            return []
        
        # Parse findings from response
        findings = self._parse_llm_response(response, code)
        
        # Ensure all findings have correct category
        for finding in findings:
            finding.category = "Data Exposure"
            # Data exposure is serious
            if finding.severity == "low":
                finding.severity = "medium"
        
        return findings
