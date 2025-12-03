"""Data Exposure Scanner - Specialized security agent.

This agent focuses on detecting hardcoded credentials, sensitive data leaks,
and improper data handling that could expose confidential information.
"""
from typing import List, Optional
from ..specialized_agent import SpecializedAgent, Finding


class DataExposureScanner(SpecializedAgent):
    """Specialized agent for detecting data exposure risks."""
    
    def initialize(self) -> None:
        """Initialize LLM client for data exposure scanning."""
        cfg = self.config or {}
        
        from ...llm import get_llm_client_from_config
        self.client = get_llm_client_from_config(cfg)
    
    def analyze(self, code: str, context: Optional[str] = None, filename: Optional[str] = None) -> List[Finding]:
        """Analyze code for sensitive data exposure.
        
        Args:
            code: Source code to analyze
            context: Optional additional context for the analysis
            filename: Optional filename for language detection
            
        Returns:
            List of Finding objects related to data exposure
        """
        from ...utils.language_detection import detect_language
        language = detect_language(filename)

        system_prompt = {
            "role": "system",
            "content": f"""You are a STRICT security expert analyzing {language} code for REAL data exposure.

ONLY report if you SEE IN THE CODE:
1. HARDCODED secrets: Literal strings that ARE passwords/keys (e.g., password="abc123", api_key="sk-xxx")
2. Logging secrets: print(password), logger.info(token), console.log(apiKey)
3. Secrets in responses: return {{"password": user.password}}

NEVER FLAG (even if code "could be" risky):
- Classes/functions that MIGHT use credentials internally (don't speculate)
- Environment variable usage (os.getenv, process.env) - this is CORRECT
- API client classes without seeing their implementation
- Code that REFERENCES tokens/keys abstractly without hardcoding them
- Any speculation like "if the token is hardcoded" - you must SEE the hardcoded value
- Context managers, HTTP clients, database connections - implementation is elsewhere
- Configuration loading from files/env (this is proper secret management)

CRITICAL: Do NOT speculate about what MIGHT be in other files or classes.
Only report what you can ACTUALLY SEE hardcoded in THIS code snippet.

For CONFIRMED exposures (you see the actual secret value), respond with:
Category: Data Exposure
Severity: [medium/high/critical]
Description: [the actual hardcoded value or logged secret you found]
Location: [line X]
Fix: [use env vars instead]
Confidence: [0.8-1.0]

If no hardcoded secrets visible, respond with: "No data exposure found."
"""
        }
        
        prompt_content = f"Analyze this {language} code for data exposure:\n\n```{language.lower()}\n{code}\n```"
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
