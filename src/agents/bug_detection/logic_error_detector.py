"""Logic Error Detector - Specialized agent for detecting logical bugs.

This agent focuses on off-by-one errors, infinite loops, incorrect algorithms,
and flawed logic in code. Uses structured prompts with few-shot examples.
"""
from typing import List, Optional
import logging
from ..specialized_agent import SpecializedAgent, Finding

# Set up logger
logger = logging.getLogger(__name__)


class LogicErrorDetector(SpecializedAgent):
    """Specialized agent for detecting logic errors using structured prompts."""
    
    def initialize(self) -> None:
        """Initialize LLM client for logic error detection."""
        cfg = self.config or {}
        
        from ...llm import get_llm_client_from_config
        self.client = get_llm_client_from_config(cfg)
    
    def analyze(self, code: str, context: Optional[str] = None, filename: Optional[str] = None) -> List[Finding]:
        """Analyze code for logic errors using structured prompts.
        
        Args:
            code: Source code to analyze
            context: Optional context string for analysis
            filename: Optional filename for language detection
            
        Returns:
            List of Finding objects related to logic errors
        """
        logger.info(f"[LogicErrorDetector] Starting analysis on {len(code)} chars of code")
        
        # Detect language
        language = self._detect_language(filename)
        
        # Few-shot examples for logic errors
        examples = [
            {
                "line": 3,
                "severity": "high",
                "category": "Off-by-one Error",
                "description": "Loop iterates one too many times causing IndexError",
                "fix_suggestion": "Change range(len(items) + 1) to range(len(items))",
                "confidence": 0.9
            },
            {
                "line": 7,
                "severity": "medium",
                "category": "Wrong Comparison",
                "description": "Using = instead of == in condition causes assignment instead of comparison",
                "fix_suggestion": "Change 'if x = 5:' to 'if x == 5:'",
                "confidence": 0.95
            }
        ]
        
        # Build structured prompt
        structured_prompt = self._build_structured_analysis_prompt(
            code=code,
            analysis_type="logic_errors",
            language=language,
            context=context,
            few_shot_examples=examples
        )
        
        messages = [
            {
                "role": "system",
                "content": "You are a logic error detection specialist. Return findings as JSON only."
            },
            {
                "role": "user",
                "content": structured_prompt
            }
        ]
        
        logger.info(f"[LogicErrorDetector] Sending request to LLM")
        
        response = self.client.chat(
            messages,
            model=self.config.get("model"),
            temperature=0.1,  # Very low for precise detection
            max_tokens=self.config.get("max_tokens")
        )
        
        logger.info(f"[LogicErrorDetector] LLM response length: {len(response)}")
        
        # Try JSON parsing first
        json_findings = self._parse_json_response(response)
        
        if json_findings:
            findings = []
            for jf in json_findings:
                findings.append(Finding(
                    category=jf.get("category", "Logic Error"),
                    severity=jf.get("severity", "medium"),
                    description=jf.get("description", ""),
                    fix_suggestion=jf.get("fix_suggestion", ""),
                    confidence=jf.get("confidence", 0.5),
                    evidence={"line_number": jf.get("line")},
                    location=f"line {jf.get('line', '?')}"
                ))
            logger.info(f"[LogicErrorDetector] Parsed {len(findings)} findings from JSON")
            return findings
        
        # Fallback to legacy parsing
        logger.info(f"[LogicErrorDetector] JSON parsing failed, using legacy parser")
        
        if "no logic errors" in response.lower() or "no errors found" in response.lower():
            logger.info(f"[LogicErrorDetector] No logic errors found")
            return []
        
        findings = self._parse_llm_response(response, code)
        logger.info(f"[LogicErrorDetector] Parsed {len(findings)} findings from legacy format")
        return findings
        
        # Ensure all findings have correct category and severity
        for finding in findings:
            finding.category = "Logic Error"
            # Logic errors are at least medium severity
            if finding.severity == "low":
                finding.severity = "medium"
        
        return findings
