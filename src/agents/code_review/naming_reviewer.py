"""Naming Convention Reviewer - Specialized agent for PEP 8 naming analysis.

This agent focuses specifically on naming conventions, variable clarity,
and identifier quality in Python code.
"""
from typing import List, Optional
from ..specialized_agent import SpecializedAgent, Finding


class NamingReviewer(SpecializedAgent):
    """Specialized agent for analyzing naming conventions and variable clarity."""
    
    def initialize(self) -> None:
        """Initialize LLM client for naming analysis."""
        from ...llm import get_llm_client_from_config
        
        cfg = self.config or {}
        self.client = get_llm_client_from_config(cfg)
    
    def analyze(self, code: str, context: Optional[str] = None, filename: Optional[str] = None) -> List[Finding]:
        """Analyze code for naming convention violations.
        
        Args:
            code: Source code to analyze
            context: Optional context from vector store
            filename: Optional filename for language detection
            
        Returns:
            List of Finding objects related to naming
        """
        language = "code"
        if filename:
            if filename.endswith(".py"):
                language = "Python"
            elif filename.endswith(".js"):
                language = "JavaScript"
            elif filename.endswith(".ts"):
                language = "TypeScript"
            elif filename.endswith(".html"):
                language = "HTML"
            elif filename.endswith(".css"):
                language = "CSS"
        
        system_prompt = {
            "role": "system",
            "content": f"""You are a {language} naming convention expert. Analyze code ONLY for naming issues.

Focus on:
1. Standard naming conventions for {language} (e.g., snake_case vs camelCase)
2. Variable name clarity and descriptiveness  
3. Avoiding single-letter names (except loop counters)
4. Boolean names should be clear (is_, has_, can_, etc.)
5. Constant names should be appropriate for the language

For EACH naming issue found, respond with this EXACT format:
Category: Naming Convention
Severity: [low/medium/high]
Description: [what's wrong with the name]
Location: [line X or function/variable name]
Fix: [specific suggestion for better name]
Confidence: [0.0-1.0]

Only report actual naming problems. If names are fine, respond with "No naming issues found."
"""
        }
        
        prompt_content = f"Analyze this {language} code for naming convention issues:\n\n```{language.lower()}\n{code}\n```"
        if context:
            prompt_content += f"\n\nAdditional Context (e.g. project standards, related files):\n{context}"
            
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
        if "no naming issues" in response.lower() or "no issues found" in response.lower():
            return []
        
        # Parse findings from response
        findings = self._parse_llm_response(response, code)
        
        # Ensure all findings have correct category
        for finding in findings:
            finding.category = "Naming Convention"
        
        return findings
