"""Edge Case Analyzer - Specialized agent for finding edge case vulnerabilities.

This agent focuses on null/None checks, boundary conditions, empty collections,
and other edge cases that could cause runtime errors.
"""
from typing import List, Optional
import logging
from ..specialized_agent import SpecializedAgent, Finding

# Set up logger
logger = logging.getLogger(__name__)


class EdgeCaseAnalyzer(SpecializedAgent):
    """Specialized agent for analyzing edge case handling."""
    
    def initialize(self) -> None:
        """Initialize LLM client for edge case analysis."""
        cfg = self.config or {}
        
        from ...llm import get_llm_client_from_config
        self.client = get_llm_client_from_config(cfg)
    
    def analyze(self, code: str, context: Optional[str] = None, filename: Optional[str] = None) -> List[Finding]:
        """Analyze code for missing edge case handling.
        
        Args:
            code: Source code to analyze
            context: Optional context
            filename: Optional filename for language detection
            
        Returns:
            List of Finding objects related to edge cases
        """
        logger.info(f"[EdgeCaseAnalyzer] Starting analysis on {len(code)} chars of code")
        
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
            "content": f"""You are an expert at finding edge case bugs in {language}. Analyze for edge case issues ONLY.

Focus on:
1. Missing null/undefined checks
2. Division by zero possibilities
3. Empty collection access without checking
4. Index out of bounds risks
5. String operations on empty strings
6. Missing error handling for external calls
7. Language-specific edge cases

For EACH edge case issue found, respond with this EXACT format:
Category: Edge Case
Severity: [medium/high/critical]
Description: [explain the edge case problem]
Location: [line X or function name]
Fix: [add check/handling for edge case]
Confidence: [0.0-1.0]

Only report actual edge case vulnerabilities. If edge cases are handled, respond with "No edge case issues found."
"""
        }
        
        prompt_content = f"Analyze this {language} code for missing edge cases:\n\n```{language.lower()}\n{code}\n```"
        if context:
            prompt_content += f"\n\nAdditional Context:\n{context}"
            
        user_prompt = {
            "role": "user",
            "content": prompt_content
        }
        
        logger.info(f"[EdgeCaseAnalyzer] Sending request to LLM")
        
        response = self.client.chat(
            [system_prompt, user_prompt],
            model=self.config.get("model"),
            temperature=self.config.get("temperature"),
            max_tokens=self.config.get("max_tokens")
        )
        
        logger.info(f"[EdgeCaseAnalyzer] LLM response length: {len(response)}")
        logger.info(f"[EdgeCaseAnalyzer] LLM response preview:\n{response[:500]}")
        
        # Check if no issues found
        if "no edge case" in response.lower() or "no issues found" in response.lower():
            logger.info(f"[EdgeCaseAnalyzer] No edge case issues found (response contains 'no issues')")
            return []
        
        # Parse findings from response
        findings = self._parse_llm_response(response, code)
        logger.info(f"[EdgeCaseAnalyzer] Parsed {len(findings)} findings")
        
        # Ensure all findings have correct category
        for finding in findings:
            finding.category = "Edge Case"
            # Edge case bugs can be critical
            if finding.severity == "low":
                finding.severity = "medium"
        
        return findings
