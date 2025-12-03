"""Specialized Agent Base Class for sub-agents with confidence scoring and evidence.

This module provides the base class for all specialized sub-agents that analyze
specific aspects of code (e.g., naming, security, bugs). Each sub-agent returns
structured findings with confidence scores and evidence.

Enhanced with structured prompt support for better LLM output quality.
Now integrates with PromptBuilder and LANGUAGE_INSTRUCTIONS for language-specific rules.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
import logging
import json
import re

# Set up logger for specialized agents
logger = logging.getLogger(__name__)

# Import language-specific instructions from PromptBuilder
try:
    from ..prompts.prompt_builder import LANGUAGE_INSTRUCTIONS
    LANGUAGE_RULES_AVAILABLE = True
except ImportError:
    logger.warning("Could not import LANGUAGE_INSTRUCTIONS from prompt_builder")
    LANGUAGE_INSTRUCTIONS = {}
    LANGUAGE_RULES_AVAILABLE = False


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
    
    def analyze(self, code: str, context: Optional[str] = None, filename: Optional[str] = None) -> List[Finding]:
        """Analyze code and return a list of findings.
        
        Args:
            code: Source code to analyze
            context: Optional context from vector store
            filename: Optional filename for language detection
            
        Returns:
            List of Finding objects
        """
        # This base method doesn't implement analysis, but subclasses should use 
        # the filename to detect language if needed.
        pass
    
    def _extract_code_snippet(self, code: str, line_number: Optional[int] = None, 
                             context_lines: int = 2) -> str:
        """Extract a code snippet with context for evidence.
        
        Args:
            code: Full source code (string or tuple - handles both)
            line_number: Line number to extract (1-indexed)
            context_lines: Number of context lines before/after
            
        Returns:
            Code snippet with context
        """
        # Handle tuple case (sometimes code comes as (filename, content) tuple)
        if isinstance(code, tuple):
            code = code[1] if len(code) > 1 else str(code[0]) if code else ""
        
        # Ensure code is a string
        if not isinstance(code, str):
            code = str(code) if code else ""
        
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
    
    def _parse_json_response(self, response: str) -> List[Dict[str, Any]]:
        """Parse JSON response from LLM.
        
        Enhanced method for parsing structured JSON output from prompts.
        
        Args:
            response: Raw LLM response
            
        Returns:
            List of finding dictionaries
        """
        if not response:
            return []
        
        # Try to extract JSON from response
        try:
            # Try direct JSON parse
            data = json.loads(response)
            return data.get("findings", [])
        except json.JSONDecodeError:
            pass
        
        # Try to find JSON block in response
        json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                return data.get("findings", [])
            except json.JSONDecodeError:
                pass
        
        # Try to find raw JSON object
        json_match = re.search(r'\{[\s\S]*"findings"[\s\S]*\}', response)
        if json_match:
            try:
                data = json.loads(json_match.group(0))
                return data.get("findings", [])
            except json.JSONDecodeError:
                pass
        
        return []
    
    def _detect_language(self, filename: Optional[str]) -> str:
        """Detect language from filename.
        
        Args:
            filename: File path or name
            
        Returns:
            Language name
        """
        if not filename:
            return "code"
        
        ext_map = {
            '.py': 'python',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.tsx': 'typescript',
            '.jsx': 'javascript',
            '.java': 'java',
            '.go': 'go',
            '.rb': 'ruby',
            '.php': 'php',
            '.rs': 'rust',
            '.cpp': 'cpp',
            '.c': 'c',
            '.cs': 'csharp',
            '.swift': 'swift',
            '.kt': 'kotlin'
        }
        
        for ext, lang in ext_map.items():
            if filename.endswith(ext):
                return lang
        
        return "code"
    
    def _build_structured_analysis_prompt(
        self,
        code: str,
        analysis_type: str,
        language: str,
        context: Optional[str] = None,
        few_shot_examples: Optional[List[Dict]] = None
    ) -> str:
        """Build a structured prompt for analysis.
        
        Args:
            code: Code to analyze
            analysis_type: Type of analysis (e.g., "logic_errors", "security")
            language: Programming language
            context: Optional additional context
            few_shot_examples: Optional list of examples
            
        Returns:
            Structured prompt string
        """
        sections = []
        
        # Instructions based on analysis type
        instructions = self._get_analysis_instructions(analysis_type, language)
        sections.append(f"## Instructions\n\n{instructions}")
        
        # Code to analyze
        sections.append(f"## Code to Analyze\n\n```{language}\n{code}\n```")
        
        # Additional context
        if context:
            sections.append(f"## Additional Context\n\n{context}")
        
        # Few-shot examples
        if few_shot_examples:
            sections.append("## Examples of Expected Output\n")
            for i, ex in enumerate(few_shot_examples[:2], 1):
                sections.append(f"### Example {i}\n```json\n{json.dumps(ex, indent=2)}\n```\n")
        
        # Output format
        sections.append("""## Required Output Format

Return findings as JSON:
```json
{
  "findings": [
    {
      "line": <line_number>,
      "severity": "critical|high|medium|low",
      "category": "<issue_category>",
      "description": "<clear description>",
      "fix_suggestion": "<how to fix>",
      "confidence": <0.0-1.0>
    }
  ]
}
```

If no issues found, return: `{"findings": []}`
Return ONLY valid JSON, no markdown or explanations.""")
        
        return "\n\n".join(sections)
    
    def _get_analysis_instructions(self, analysis_type: str, language: str) -> str:
        """Get analysis instructions based on type and language-specific rules.
        
        Now integrates with LANGUAGE_INSTRUCTIONS from PromptBuilder for
        detailed, language-specific code review rules.
        
        Args:
            analysis_type: Type of analysis
            language: Programming language
            
        Returns:
            Instruction text with language-specific rules
        """
        # Get language-specific rules from PromptBuilder
        lang_key = language.lower() if language.lower() in LANGUAGE_INSTRUCTIONS else "default"
        lang_rules = LANGUAGE_INSTRUCTIONS.get(lang_key, [])
        
        # Format language-specific rules for prompt
        lang_rules_text = ""
        if lang_rules and LANGUAGE_RULES_AVAILABLE:
            relevant_rules = self._filter_rules_by_analysis_type(lang_rules, analysis_type)
            if relevant_rules:
                lang_rules_text = "\n\n### Language-Specific Rules for " + language.capitalize() + ":\n"
                lang_rules_text += "\n".join(f"- {rule}" for rule in relevant_rules[:10])
        
        base_instructions = {
            "logic_errors": f"""You are an expert at finding logic errors in {language} code.

Focus on:
1. Off-by-one errors in loops and array indexing
2. Infinite loops or incorrect loop conditions
3. Wrong comparison operators (< vs <=, == vs ===)
4. Incorrect algorithm logic
5. Inverted or wrong conditions
6. Division by zero risks
7. Integer overflow/underflow
{lang_rules_text}

Only report ACTUAL logic errors that would cause incorrect behavior.""",

            "edge_cases": f"""You are an expert at finding edge case bugs in {language} code.

Focus on:
1. Null/None/undefined handling
2. Empty array/string/collection handling
3. Boundary conditions (first/last element, max/min values)
4. Type mismatches and implicit conversions
5. Missing input validation
{lang_rules_text}

Only report edge cases that could cause runtime errors or incorrect behavior.""",

            "type_errors": f"""You are an expert at finding type-related bugs in {language} code.

Focus on:
1. Type mismatches in function calls
2. Incorrect type conversions
3. Missing type checks
4. Wrong return types
5. Attribute/method access on wrong types
{lang_rules_text}

Only report issues that would cause TypeError or similar runtime errors.""",

            "runtime_issues": f"""You are an expert at finding runtime issues in {language} code.

Focus on:
1. Resource leaks (unclosed files, connections)
2. Memory issues
3. Deadlocks and race conditions
4. Performance problems (N+1 queries, inefficient algorithms)
5. Unhandled exceptions
{lang_rules_text}

Only report issues that would cause runtime failures or severe performance degradation.""",

            "security": f"""You are a security expert analyzing {language} code for vulnerabilities.

Focus on:
1. SQL/NoSQL injection
2. Command injection
3. XSS vulnerabilities
4. Path traversal
5. Hardcoded credentials/secrets
6. Authentication/authorization flaws
7. Insecure deserialization
8. SSRF vulnerabilities
{lang_rules_text}

Only report EXPLOITABLE security vulnerabilities."""
        }
        
        return base_instructions.get(analysis_type, base_instructions["logic_errors"])
    
    def _filter_rules_by_analysis_type(self, rules: List[str], analysis_type: str) -> List[str]:
        """Filter language rules to only those relevant to the analysis type.
        
        Args:
            rules: List of language-specific rules
            analysis_type: Type of analysis (logic_errors, security, etc.)
            
        Returns:
            Filtered list of relevant rules
        """
        if not rules:
            return []
        
        # Keywords that indicate relevance to each analysis type
        type_keywords = {
            "logic_errors": ["logic", "condition", "loop", "comparison", "boolean", "off-by-one", "range", "index"],
            "edge_cases": ["null", "none", "undefined", "empty", "boundary", "default", "optional", "check"],
            "type_errors": ["type", "coercion", "conversion", "cast", "any", "assertion", "typeof", "instanceof"],
            "runtime_issues": ["resource", "leak", "close", "memory", "concurrent", "thread", "exception", "error"],
            "security": ["injection", "xss", "sql", "credential", "secret", "auth", "sanitize", "escape", "validate"]
        }
        
        keywords = type_keywords.get(analysis_type, [])
        if not keywords:
            return rules[:5]  # Return first 5 if no keywords match
        
        filtered = []
        for rule in rules:
            rule_lower = rule.lower()
            if any(kw in rule_lower for kw in keywords):
                filtered.append(rule)
        
        return filtered if filtered else rules[:5]
