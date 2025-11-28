"""Dependency Vulnerability Scanner - Specialized security agent.

This agent focuses on detecting usage of known vulnerable dependencies
and insecure library usage patterns.
"""
from typing import List, Optional
from ..specialized_agent import SpecializedAgent, Finding


class DependencyScanner(SpecializedAgent):
    """Specialized agent for detecting dependency-related security issues."""
    
    def initialize(self) -> None:
        """Initialize LLM client for dependency scanning."""
        cfg = self.config or {}
        
        from ...llm import get_llm_client_from_config
        self.client = get_llm_client_from_config(cfg)
    
    def analyze(self, code: str, context: Optional[str] = None, filename: Optional[str] = None) -> List[Finding]:
        """Analyze code for insecure dependencies.
        
        Args:
            code: Source code to analyze
            context: Optional[str]: Additional context or description of the code.
            filename: Optional filename for language detection
            
        Returns:
            List of Finding objects related to dependency issues
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
            elif filename.endswith(".json"):
                language = "JSON"

        system_prompt = {
            "role": "system",
            "content": f"""You are a security expert specializing in dependency security for {language}. Analyze for dependency security issues ONLY.

Focus on:
1. Use of deprecated/unsafe functions (e.g., eval, exec, unsafe deserialization)
2. Insecure deserialization patterns
3. Known vulnerable library usage patterns
4. Unsafe parsing (e.g., XML XXE)
5. Use of weak cryptographic functions
6. Language-specific dependency risks (e.g., npm audit issues in package.json)

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
        
        prompt_content = f"Analyze this {language} code for dependency issues:\n\n```{language.lower()}\n{code}\n```"
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
