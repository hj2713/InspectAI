"""Logic Error Detector - Specialized agent for detecting logical bugs.

This agent focuses on off-by-one errors, infinite loops, incorrect algorithms,
and flawed logic in code.
"""
from typing import List, Optional
import logging
from ..specialized_agent import SpecializedAgent, Finding

# Set up logger
logger = logging.getLogger(__name__)


class LogicErrorDetector(SpecializedAgent):
    """Specialized agent for detecting logic errors."""
    
    def initialize(self) -> None:
        """Initialize LLM client for logic error detection."""
        cfg = self.config or {}
        
        from ...llm import get_llm_client_from_config
        self.client = get_llm_client_from_config(cfg)
    
    def analyze(self, code: str, context: Optional[str] = None, filename: Optional[str] = None) -> List[Finding]:
        """Analyze code for logic errors.
        
        Args:
            code: Source code to analyze
            context: Optional context string for analysis (e.g., related code, problem description)
            filename: Optional filename for language detection
            
        Returns:
            List of Finding objects related to logic errors
        """
        logger.info(f"[LogicErrorDetector] Starting analysis on {len(code)} chars of code")
        
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
        
        system_prompt = {
            "role": "system",
            "content": f"""You are an expert at finding logic errors in {language} code. Analyze for logic bugs ONLY.

Focus on:
1. Off-by-one errors (range issues, indexing)
2. Infinite loops or incorrect loop conditions
3. Wrong comparison operators
4. Incorrect algorithm logic
5. Inverted conditions
6. Language-specific logic pitfalls

For EACH logic error found, respond with this EXACT format:
Category: Logic Error
Severity: [medium/high/critical]
Description: [explain the logic bug]
Location: [line X or function name]
Fix: [correct logic]
Confidence: [0.0-1.0]

Only report actual logic errors. If logic appears correct, respond with "No logic errors found."
"""
        }
        
        prompt_content = f"Analyze this {language} code for logic errors:\n\n```{language.lower()}\n{code}\n```"
        if context:
            prompt_content += f"\n\nAdditional Context (e.g. requirements, related code):\n{context}"
            
        user_prompt = {
            "role": "user",
            "content": prompt_content
        }
        
        logger.info(f"[LogicErrorDetector] Sending request to LLM")
        
        response = self.client.chat(
            [system_prompt, user_prompt],
            model=self.config.get("model"),
            temperature=self.config.get("temperature"),
            max_tokens=self.config.get("max_tokens")
        )
        
        logger.info(f"[LogicErrorDetector] LLM response length: {len(response)}")
        logger.info(f"[LogicErrorDetector] LLM response preview:\n{response[:500]}")
        
        # Check if no issues found
        if "no logic errors" in response.lower() or "no errors found" in response.lower():
            logger.info(f"[LogicErrorDetector] No logic errors found (response contains 'no errors')")
            return []
        
        # Parse findings from response
        findings = self._parse_llm_response(response, code)
        logger.info(f"[LogicErrorDetector] Parsed {len(findings)} findings")
        
        # Ensure all findings have correct category and severity
        for finding in findings:
            finding.category = "Logic Error"
            # Logic errors are at least medium severity
            if finding.severity == "low":
                finding.severity = "medium"
        
        return findings
