"""Code Duplication Detector - Specialized agent for finding repeated patterns.

This agent focuses on detecting duplicated code patterns and suggesting refactoring
opportunities.
"""
from typing import List
from ..specialized_agent import SpecializedAgent, Finding


class DuplicationDetector(SpecializedAgent):
    """Specialized agent for detecting code duplication."""
    
    def initialize(self) -> None:
        """Initialize LLM client for duplication detection."""
        cfg = self.config or {}
        
        from ...llm import get_llm_client_from_config
        self.client = get_llm_client_from_config(cfg)
    
    def analyze(self, code: str, context: Optional[str] = None) -> List[Finding]:
        """Analyze code for duplication.
        
        Args:
            code: Python source code to analyze
            context: Optional additional context for the analysis
            
        Returns:
            List of Finding objects related to code duplication
        """
        system_prompt = {
            "role": "system",
            "content": """You are a code refactoring expert. Analyze code for duplication ONLY.

Focus on:
1. Repeated code blocks that could be extracted into functions
2. Similar logic patterns that could be unified
3. Duplicate string literals that should be constants
4. Repeated error handling that could be centralized

For EACH duplication issue found, respond with this EXACT format:
Category: Code Duplication
Severity: [low/medium/high]
Description: [describe the duplication]
Location: [locations where code is duplicated]
Fix: [suggest how to refactor/extract]
Confidence: [0.0-1.0]

Only report actual duplication. If there's no duplication, respond with "No duplication found."
"""
        }
        
        prompt_content = f"Analyze this Python code for duplication:\n\n```python\n{code}\n```"
        if context:
            prompt_content += f"\n\nAdditional Context (check against this for duplication):\n{context}"
            
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
        if "no duplication" in response.lower() or "no issues found" in response.lower():
            return []
        
        # Parse findings from response
        findings = self._parse_llm_response(response, code)
        
        # Ensure all findings have correct category
        for finding in findings:
            finding.category = "Code Duplication"
            # Duplication is typically medium severity
            if finding.severity == "critical":
                finding.severity = "medium"
        
        return findings
