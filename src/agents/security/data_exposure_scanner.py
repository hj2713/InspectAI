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
            "content": f"""You are a STRICT security expert analyzing {language} code for REAL data exposure risks.

ONLY report if you find:
1. HARDCODED secrets: Actual passwords, API keys, tokens written directly in code (not env vars)
2. Logging sensitive data: Passwords, tokens, or PII printed to logs
3. Unencrypted storage: Passwords stored in plaintext in databases/files

DO NOT FLAG (these are acceptable patterns):
- Environment variable usage: os.getenv(), process.env, etc. - this is the CORRECT approach
- Sending code/context to LLMs for analysis - this is the app's intended purpose
- Internal data structures being passed between functions
- File paths, repo names, PR numbers in prompts - this is normal application data
- Placeholder/example values in prompts or documentation
- Configuration that references env vars
- Code that handles data properly (encrypted, hashed, tokenized)
- LLM prompt construction with code context - this is EXPECTED behavior for a code review tool

Be VERY conservative. Internal application data flow is NOT data exposure.

For EACH CONFIRMED exposure, respond with:
Category: Data Exposure
Severity: [medium/high/critical]
Description: [what SPECIFIC sensitive data (password/key/PII) is exposed WHERE (logs/response/storage)]
Location: [line X]
Fix: [specific fix]
Confidence: [0.7-1.0 only if certain]

If code is safe, respond with: "No data exposure found."
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
