"""Edge Case Analyzer - Specialized agent for finding edge case vulnerabilities.

This agent focuses on null/None checks, boundary conditions, empty collections,
and other edge cases that could cause runtime errors.
Uses structured prompts with JSON output format.
"""
from typing import List, Optional
import logging
from ..specialized_agent import SpecializedAgent, Finding

# Set up logger
logger = logging.getLogger(__name__)


class EdgeCaseAnalyzer(SpecializedAgent):
    """Specialized agent for analyzing edge case handling using structured prompts."""
    
    def initialize(self) -> None:
        """Initialize LLM client for edge case analysis."""
        cfg = self.config or {}
        
        from ...llm import get_llm_client_from_config
        self.client = get_llm_client_from_config(cfg)
    
    def analyze(self, code: str, context: Optional[str] = None, filename: Optional[str] = None) -> List[Finding]:
        """Analyze code for missing edge case handling using structured prompts.
        
        Args:
            code: Source code to analyze
            context: Optional context
            filename: Optional filename for language detection
            
        Returns:
            List of Finding objects related to edge cases
        """
        logger.info(f"[EdgeCaseAnalyzer] Starting analysis on {len(code)} chars of code")
        
        # Detect language
        language = self._detect_language(filename)
        
        # Few-shot examples for edge cases
        examples = [
            {
                "line": 5,
                "severity": "high",
                "category": "Null Check Missing",
                "description": "Accessing .length on potentially null array without null check",
                "fix_suggestion": "Add null check: if (items && items.length > 0)",
                "confidence": 0.85
            },
            {
                "line": 12,
                "severity": "medium",
                "category": "Empty Collection",
                "description": "Accessing first element of array without checking if empty",
                "fix_suggestion": "Check array length before access: if (arr.length > 0) { return arr[0]; }",
                "confidence": 0.8
            }
        ]
        
        # Build structured prompt
        structured_prompt = self._build_structured_analysis_prompt(
            code=code,
            analysis_type="edge_cases",
            language=language,
            context=context,
            few_shot_examples=examples
        )
        
        messages = [
            {
                "role": "system",
                "content": "You are an edge case detection specialist. Return findings as JSON only."
            },
            {
                "role": "user",
                "content": structured_prompt
            }
        ]
        
        logger.info(f"[EdgeCaseAnalyzer] Sending request to LLM")
        
        response = self.client.chat(
            messages,
            model=self.config.get("model"),
            temperature=0.1,
            max_tokens=self.config.get("max_tokens")
        )
        
        logger.info(f"[EdgeCaseAnalyzer] LLM response length: {len(response)}")
        
        # Try JSON parsing first
        json_findings = self._parse_json_response(response)
        
        if json_findings:
            findings = []
            for jf in json_findings:
                findings.append(Finding(
                    category=jf.get("category", "Edge Case"),
                    severity=jf.get("severity", "medium"),
                    description=jf.get("description", ""),
                    fix_suggestion=jf.get("fix_suggestion", ""),
                    confidence=jf.get("confidence", 0.5),
                    evidence={"line_number": jf.get("line")},
                    location=f"line {jf.get('line', '?')}"
                ))
            logger.info(f"[EdgeCaseAnalyzer] Parsed {len(findings)} findings from JSON")
            return findings
        
        # Fallback to legacy parsing
        logger.info(f"[EdgeCaseAnalyzer] JSON parsing failed, using legacy parser")
        
        if "no edge case" in response.lower() or "no issues found" in response.lower():
            logger.info(f"[EdgeCaseAnalyzer] No edge case issues found")
            return []
        
        findings = self._parse_llm_response(response, code)
        
        # Ensure all findings have correct category
        for finding in findings:
            finding.category = "Edge Case"
            if finding.severity == "low":
                finding.severity = "medium"
        
        logger.info(f"[EdgeCaseAnalyzer] Parsed {len(findings)} findings from legacy format")
        return findings
