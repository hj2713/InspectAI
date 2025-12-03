"""Authentication/Authorization Scanner - Specialized security agent.

This agent focuses on detecting authentication and authorization issues,
access control problems, and session management flaws.
"""
from typing import List, Optional
from ..specialized_agent import SpecializedAgent, Finding


class AuthScanner(SpecializedAgent):
    """Specialized agent for detecting authentication/authorization issues."""
    
    def initialize(self) -> None:
        """Initialize LLM client for auth scanning."""
        cfg = self.config or {}
        
        from ...llm import get_llm_client_from_config
        self.client = get_llm_client_from_config(cfg)
    
    def analyze(self, code: str, context: Optional[str] = None, filename: Optional[str] = None) -> List[Finding]:
        """Analyze code for authentication/authorization issues.
        
        Args:
            code: Source code to analyze
            context: Optional additional context for the analysis
            filename: Optional filename for language detection
            
        Returns:
            List of Finding objects related to auth issues
        """
        from ...utils.language_detection import detect_language
        language = detect_language(filename)

        system_prompt = {
            "role": "system",
            "content": f"""You are a STRICT security expert analyzing {language} code for REAL authentication/authorization issues.

ONLY report if you find:
1. Missing auth: Sensitive operations (delete, admin actions) with NO auth check before them
2. Weak passwords: Hardcoded passwords, or accepting passwords < 8 chars
3. Auth bypass: Code that skips auth checks (e.g., if user.is_admin always returns true)
4. Insecure sessions: Session tokens stored in localStorage, no expiry, predictable IDs

DO NOT FLAG (these are acceptable):
- Internal function calls that assume caller already authenticated
- Backend services communicating with each other (service-to-service)
- Webhook handlers (GitHub validates webhooks separately)
- CLI tools or scripts (not web-exposed)
- Code that checks auth elsewhere (middleware, decorators, guards)
- Helper functions that don't handle user requests directly
- Installation ID based auth (GitHub App pattern) - this is valid auth

Be VERY conservative. Only flag if you see CLEAR auth problems in web-exposed endpoints.

For EACH CONFIRMED issue, respond with:
Category: Authentication/Authorization
Severity: [medium/high/critical]
Description: [explain what sensitive action lacks what auth check]
Location: [line X]
Fix: [specific fix]
Confidence: [0.7-1.0 only if certain]

If code is safe, respond with: "No auth issues found."
"""
        }
        
        prompt_content = f"Analyze this {language} code for authentication issues:\n\n```{language.lower()}\n{code}\n```"
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
        if "no auth issues" in response.lower() or "no issues found" in response.lower():
            return []
        
        # Parse findings from response
        findings = self._parse_llm_response(response, code)
        
        # Ensure all findings have correct category
        for finding in findings:
            finding.category = "Authentication/Authorization"
            # Auth issues are at least medium severity
            if finding.severity == "low":
                finding.severity = "medium"
        
        return findings
