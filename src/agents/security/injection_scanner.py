"""Injection Vulnerability Scanner - Specialized security agent.

This agent focuses on detecting SQL injection, command injection, path traversal,
and other injection vulnerabilities.
"""
from typing import List, Optional
from ..specialized_agent import SpecializedAgent, Finding


class InjectionScanner(SpecializedAgent):
    """Specialized agent for detecting injection vulnerabilities."""
    
    def initialize(self) -> None:
        """Initialize LLM client for injection scanning."""
        cfg = self.config or {}
        
        from ...llm import get_llm_client_from_config
        self.client = get_llm_client_from_config(cfg)
    
    def analyze(self, code: str, context: Optional[str] = None, filename: Optional[str] = None) -> List[Finding]:
        """Analyze code for injection vulnerabilities.
        
        Args:
            code: Source code to analyze
            context: Optional context
            filename: Optional filename for language detection
            
        Returns:
            List of Finding objects related to injection vulnerabilities
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
            elif filename.endswith(".php"):
                language = "PHP"

        system_prompt = {
            "role": "system",
            "content": f"""You are a security expert specializing in injection attacks in {language}. Analyze for injection vulnerabilities ONLY.

Focus on:
1. SQL injection (string concatenation in queries)
2. Command injection (executing system commands with user input)
3. Path traversal (file operations with user-provided paths)
4. LDAP/NoSQL injection
5. XSS (Cross-Site Scripting) if applicable
6. Template injection

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
        
        prompt_content = f"Analyze this {language} code for injection vulnerabilities:\n\n```{language.lower()}\n{code}\n```"
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
