"""Type Error Detector - Specialized agent for finding type-related bugs.

This agent focuses on type mismatches, missing type hints, incorrect type usage,
and type-related bugs in Python code.
"""
from typing import List, Optional
import logging
from ..specialized_agent import SpecializedAgent, Finding

# Set up logger
logger = logging.getLogger(__name__)


class TypeErrorDetector(SpecializedAgent):
    """Specialized agent for detecting type-related errors."""
    
    def initialize(self) -> None:
        """Initialize LLM client for type error detection."""
        cfg = self.config or {}
        
        from ...llm import get_llm_client_from_config
        self.client = get_llm_client_from_config(cfg)
    
    def analyze(self, code: str, context: Optional[str] = None, filename: Optional[str] = None) -> List[Finding]:
        """Analyze code for potential type errors.
        
        Args:
            code: Source code to analyze
            context: Optional context or additional information for analysis.
            filename: Optional filename for language detection
            
        Returns:
            List of Finding objects related to type errors
        """
        logger.info(f"[TypeErrorDetector] Starting analysis on {len(code)} chars of code")
        
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
            "content": f"""You are an expert at finding type errors in {language}. Analyze for type issues ONLY.

Focus on:
1. Type mismatches (passing wrong type to function)
2. Operations on incompatible types
3. Missing or incorrect type hints/annotations (if applicable)
4. Returning wrong type from function
5. Language-specific type coercion issues

For EACH type error found, respond with this EXACT format:
Category: Type Error
Severity: [medium/high/critical]
Description: [explain the type problem]
Location: [line X or function name]
Fix: [correct type usage or add type hints]
Confidence: [0.0-1.0]

Only report actual type errors. If types are correct, respond with "No type errors found."
"""
        }
        
        prompt_content = f"Analyze this {language} code for type errors:\n\n```{language.lower()}\n{code}\n```"
        if context:
            prompt_content += f"\n\nAdditional Context (e.g. type definitions):\n{context}"
            
        user_prompt = {
            "role": "user",
            "content": prompt_content
        }
        
        logger.info(f"[TypeErrorDetector] Sending request to LLM")
        
        response = self.client.chat(
            [system_prompt, user_prompt],
            model=self.config.get("model"),
            temperature=self.config.get("temperature"),
            max_tokens=self.config.get("max_tokens")
        )
        
        logger.info(f"[TypeErrorDetector] LLM response length: {len(response)}")
        logger.info(f"[TypeErrorDetector] LLM response preview:\n{response[:500]}")
        
        # Check if no issues found
        if "no type errors" in response.lower() or "no errors found" in response.lower():
            logger.info(f"[TypeErrorDetector] No type errors found (response contains 'no errors')")
            return []
        
        # Parse findings from response
        findings = self._parse_llm_response(response, code)
        logger.info(f"[TypeErrorDetector] Parsed {len(findings)} findings")
        
        # Ensure all findings have correct category
        for finding in findings:
            finding.category = "Type Error"
            # Type errors can cause runtime crashes
            if finding.severity == "low":
                finding.severity = "medium"
        
        return findings
