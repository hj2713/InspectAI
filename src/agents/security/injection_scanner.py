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
        from ...utils.language_detection import detect_language
        language = detect_language(filename)

        system_prompt = {
            "role": "system",
            "content": f"""You are a STRICT security expert analyzing {language} code for REAL injection vulnerabilities.

ONLY report if you find code that:
1. SQL Injection: Raw SQL strings built with user input via string concatenation/formatting AND executed directly
2. Command Injection: User input passed to os.system(), subprocess.call(), exec(), or eval()
3. Path Traversal: User-controlled paths in file operations without sanitization

DO NOT FLAG (these are safe patterns):
- Supabase/Firebase client library calls (they use parameterized queries internally)
- ORM queries (SQLAlchemy, Django ORM, Prisma) - they parameterize automatically
- RPC function calls like `.rpc("function_name", params)` - these are parameterized
- String formatting for search/filter text (not SQL execution)
- f-strings used for logging, display text, or API calls (not database queries)
- Vector store search queries (semantic search, not SQL)
- Internal variable concatenation (not from user input)

Be VERY conservative. If unsure whether user input reaches the vulnerable sink, DO NOT report.

For EACH CONFIRMED vulnerability, respond with:
Category: Injection Vulnerability
Severity: [high/critical]
Description: [explain what user input reaches what dangerous function]
Location: [line X]
Fix: [specific fix]
Confidence: [0.7-1.0 only if certain]

If code is safe, respond with: "No injection vulnerabilities found."
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
