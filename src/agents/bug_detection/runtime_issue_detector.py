"""Runtime Issue Detector - Specialized agent for performance and resource bugs.

This agent focuses on resource leaks, performance issues, and runtime problems
that don't cause immediate crashes but affect program execution.
"""
from typing import List
from ..specialized_agent import SpecializedAgent, Finding


class RuntimeIssueDetector(SpecializedAgent):
    """Specialized agent for detecting runtime and performance issues."""
    
    def initialize(self) -> None:
        """Initialize LLM client for runtime issue detection."""
        cfg = self.config or {}
        provider = cfg.get("provider", "openai")
        
        from ...llm import get_llm_client_from_config
        self.client = get_llm_client_from_config(cfg)
            default_max_tokens=cfg.get("max_tokens", 1024),
            provider=provider
        )
    
    def analyze(self, code: str) -> List[Finding]:
        """Analyze code for runtime and performance issues.
        
        Args:
            code: Python source code to analyze
            
        Returns:
            List of Finding objects related to runtime issues
        """
        system_prompt = {
            "role": "system",
            "content": """You are an expert at finding runtime and performance issues. Analyze for runtime problems ONLY.

Focus on:
1. Resource leaks (files not closed, connections not released)
2. Memory inefficiency (unnecessary copies, large data in memory)
3. Performance issues (O(n²) when O(n) possible)
4. Blocking operations without timeouts
5. Inefficient loops or data structures

For EACH runtime issue found, respond with this EXACT format:
Category: Runtime Issue
Severity: [low/medium/high]
Description: [explain the runtime problem]
Location: [line X or function name]
Fix: [how to fix the performance/resource issue]
Confidence: [0.0-1.0]

Only report actual runtime issues. If code is efficient, respond with "No runtime issues found."
"""
        }
        
        user_prompt = {
            "role": "user",
            "content": f"Analyze this Python code for runtime issues:\n\n```python\n{code}\n```"
        }
        
        response = self.client.chat(
            [system_prompt, user_prompt],
            model=self.config.get("model"),
            temperature=self.config.get("temperature"),
            max_tokens=self.config.get("max_tokens")
        )
        
        # Check if no issues found
        if "no runtime issues" in response.lower() or "no issues found" in response.lower():
            return []
        
        # Parse findings from response
        findings = self._parse_llm_response(response, code)
        
        # Ensure all findings have correct category
        for finding in findings:
            finding.category = "Runtime Issue"
        
        return findings
