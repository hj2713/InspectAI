"""Specialized Agent Base Class for sub-agents with confidence scoring and evidence.

This module provides the base class for all specialized sub-agents that analyze
specific aspects of code (e.g., naming, security, bugs). Each sub-agent returns
structured findings with confidence scores and evidence.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
import logging

# Set up logger for specialized agents
logger = logging.getLogger(__name__)


@dataclass
class Finding:
    """Represents a single finding from a specialized agent.
    
    Attributes:
        category: Category of the finding (e.g., "Naming Convention", "SQL Injection")
        severity: Severity level ("critical", "high", "medium", "low")
        description: Human-readable description of the issue
        fix_suggestion: Suggested fix or remediation
        confidence: Confidence score 0.0-1.0 (how certain the agent is)
        evidence: Evidence supporting this finding (code snippets, line numbers)
        location: Where in the code (line number, function name, etc.)
    """
    category: str
    severity: str
    description: str
    fix_suggestion: str
    confidence: float = 0.5
    evidence: Dict[str, Any] = field(default_factory=dict)
    location: str = ""
    
    def __post_init__(self):
        """Validate the finding after initialization."""
        # Normalize severity
        self.severity = self.severity.lower()
        if self.severity not in ["critical", "high", "medium", "low"]:
            self.severity = "medium"
        
        # Ensure confidence is in valid range
        self.confidence = max(0.0, min(1.0, self.confidence))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert finding to dictionary."""
        return {
            "category": self.category,
            "severity": self.severity,
            "description": self.description,
            "fix_suggestion": self.fix_suggestion,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "location": self.location
        }


class SpecializedAgent(ABC):
    """Base class for all specialized sub-agents.
    
    Each specialized agent focuses on one specific aspect of code analysis
    (e.g., naming conventions, type errors, SQL injection).
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the specialized agent.
        
        Args:
            config: Configuration dictionary containing model settings, etc.
        """
        self.config = config or {}
        self.client = None
        self.initialize()
    
    
    def initialize(self) -> None:
        """Initialize LLM client using centralized factory.
        
        Override this if agent needs custom initialization logic,
        but still use get_llm_client() for LLM client creation.
        """
        from ..llm import get_llm_client_from_config
        
        cfg = self.config or {}
        logger.info(f"[{self.__class__.__name__}] Initializing with config: {cfg}")
        self.client = get_llm_client_from_config(cfg)
        logger.info(f"[{self.__class__.__name__}] LLM client initialized: {type(self.client).__name__}")
    
    @abstractmethod
    def analyze(self, code: str) -> List[Finding]:
        """Analyze code and return a list of findings.
        
        Args:
            code: Source code to analyze
            
        Returns:
            List of Finding objects
        """
        pass
    
    def _extract_code_snippet(self, code: str, line_number: Optional[int] = None, 
                             context_lines: int = 2) -> str:
        """Extract a code snippet with context for evidence.
        
        Args:
            code: Full source code
            line_number: Line number to extract (1-indexed)
            context_lines: Number of context lines before/after
            
        Returns:
            Code snippet with context
        """
        if line_number is None:
            return code[:200]  # Return first 200 chars as fallback
        
        lines = code.splitlines()
        if line_number < 1 or line_number > len(lines):
            return ""
        
        start = max(0, line_number - 1 - context_lines)
        end = min(len(lines), line_number + context_lines)
        
        snippet_lines = []
        for i in range(start, end):
            marker = ">>> " if i == line_number - 1 else "    "
            snippet_lines.append(f"{marker}{i+1:4d}: {lines[i]}")
        
        return "\n".join(snippet_lines)
    
    def _parse_llm_response(self, response: str, code: str) -> List[Finding]:
        """Parse LLM response into structured findings.
        
        This is a helper method that subclasses can override or use.
        
        Args:
            response: Raw LLM response text
            code: Original code (for extracting evidence)
            
        Returns:
            List of Finding objects
        """
        logger.info(f"[{self.__class__.__name__}] Parsing LLM response, length={len(response)}")
        logger.info(f"[{self.__class__.__name__}] LLM response (first 1000 chars):\n{response[:1000]}")
        
        findings = []
        current_finding = {}
        
        for line in response.splitlines():
            line = line.strip()
            if not line:
                if current_finding and "category" in current_finding:
                    logger.debug(f"[{self.__class__.__name__}] Creating finding from: {current_finding}")
                    findings.append(self._create_finding_from_dict(current_finding, code))
                    current_finding = {}
                continue
            
            # Parse structured output
            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip().lower()
                value = value.strip()
                
                logger.debug(f"[{self.__class__.__name__}] Parsed line - key='{key}', value='{value[:50] if len(value) > 50 else value}'")
                
                if key in ["category", "type"]:
                    current_finding["category"] = value
                elif key == "severity":
                    current_finding["severity"] = value
                elif key in ["description", "issue", "problem"]:
                    current_finding["description"] = value
                elif key in ["fix", "remediation", "suggestion"]:
                    current_finding["fix_suggestion"] = value
                elif key in ["location", "line"]:
                    current_finding["location"] = value
                elif key == "confidence":
                    try:
                        current_finding["confidence"] = float(value)
                    except ValueError:
                        current_finding["confidence"] = 0.5
        
        # Don't forget last finding
        if current_finding and "category" in current_finding:
            logger.debug(f"[{self.__class__.__name__}] Creating last finding from: {current_finding}")
            findings.append(self._create_finding_from_dict(current_finding, code))
        
        logger.info(f"[{self.__class__.__name__}] Parsing complete. Found {len(findings)} findings")
        if not findings:
            logger.warning(f"[{self.__class__.__name__}] NO FINDINGS PARSED! Full response:\n{response}")
        
        return findings
    
    def _create_finding_from_dict(self, data: Dict[str, Any], code: str) -> Finding:
        """Create a Finding object from parsed dictionary.
        
        Args:
            data: Dictionary with finding data
            code: Original code for extracting evidence
            
        Returns:
            Finding object
        """
        # Extract line number from location if possible
        line_number = None
        location = data.get("location", "")
        if location:
            try:
                # Try to extract number from strings like "line 42", "L42", etc.
                import re
                match = re.search(r'\d+', location)
                if match:
                    line_number = int(match.group())
            except:
                pass
        
        # Create evidence with code snippet
        evidence = {
            "line_number": line_number,
            "code_snippet": self._extract_code_snippet(code, line_number) if line_number else ""
        }
        
        return Finding(
            category=data.get("category", "Unknown"),
            severity=data.get("severity", "medium"),
            description=data.get("description", ""),
            fix_suggestion=data.get("fix_suggestion", ""),
            confidence=data.get("confidence", 0.5),
            evidence=evidence,
            location=location
        )
    
    def cleanup(self) -> None:
        """Cleanup resources. Override if needed."""
        pass
