"""Type Error Detector - Specialized agent for finding type-related bugs.

This agent focuses on type mismatches, missing type hints, incorrect type usage,
and type-related bugs in Python code.
"""
from typing import List
from ..specialized_agent import SpecializedAgent, Finding


class TypeErrorDetector(SpecializedAgent):
    """Specialized agent for detecting type-related errors."""
    
    def initialize(self) -> None:
        """Initialize LLM client for type error detection."""
        cfg = self.config or {}
        provider = cfg.get("provider", "openai")
        
        from ...llm import get_llm_client_from_config
        self.client = get_llm_client_from_config(cfg)
            default_max_tokens=cfg.get("max_tokens", 1024),
            provider=provider
        )
    
    def analyze(self, code: str) -> List[Finding]:
        """Analyze code for type-related errors.
        
        Args:
            code: Python source code to analyze
            
        Returns:
            List of Finding objects related to type errors
        """
        system_prompt = {
            "role": "system",
            "content": """You are an expert at finding type errors in Python. Analyze for type issues ONLY.

Focus on:
1. Type mismatches (passing wrong type to function)
2. Operations on incompatible types (string + int without conversion)
3. Missing or incorrect type hints
4. Returning wrong type from function
5. Mixing bytes and strings

For EACH type error found, respond with this EXACT format:
Category: Type Error
Severity: [medium/high/critical]
Description: [explain the type problem]
Location: [line X or function name]
Fix: [correct type usage or add type hints]
Confidence: [0.0-1.0]

Only report actual type errors. If types are correct, respond with "No type errors found."
"""
        }
        
        user_prompt = {
            "role": "user",
            "content": f"Analyze this Python code for type errors:\n\n```python\n{code}\n```"
        }
        
        response = self.client.chat(
            [system_prompt, user_prompt],
            model=self.config.get("model"),
            temperature=self.config.get("temperature"),
            max_tokens=self.config.get("max_tokens")
        )
        
        # Check if no issues found
        if "no type errors" in response.lower() or "no errors found" in response.lower():
            return []
        
        # Parse findings from response
        findings = self._parse_llm_response(response, code)
        
        # Ensure all findings have correct category
        for finding in findings:
            finding.category = "Type Error"
            # Type errors can cause runtime crashes
            if finding.severity == "low":
                finding.severity = "medium"
        
        return findings
