"""Code Analysis Agent for understanding and analyzing code.

Uses an expert code reviewer that reviews code like a senior software developer.
"""
from typing import Any, Dict, List
import re

from .base_agent import BaseAgent
from .code_review_expert import CodeReviewExpert


class CodeAnalysisAgent(BaseAgent):
    """Agent that uses an expert code reviewer."""
    
    def initialize(self) -> None:
        """Initialize expert code reviewer."""
        cfg = self.config or {}
        self.expert_reviewer = CodeReviewExpert(cfg)
    
    def process(self, code: str, context: str = None, filename: str = None) -> Dict[str, Any]:
        """Analyze code using expert reviewer.
        
        Args:
            code: Source code or diff_context string to analyze
            context: Optional context from vector store (unused now)
            filename: Optional filename for language detection
            
        Returns:
            Dict containing findings from expert reviewer
        """
        # Parse the diff context if it's in the expected format
        file_path = filename or "unknown"
        diff_patch = ""
        full_content = code
        
        # Check if code contains our formatted diff context
        if "FILE:" in code and "DIFF PATCH" in code and "FULL FILE CONTEXT" in code:
            # Extract file path
            file_match = re.search(r'FILE:\s*(.+)', code)
            if file_match:
                file_path = file_match.group(1).strip()
            
            # Extract diff patch
            diff_match = re.search(r'DIFF PATCH.*?```diff\n(.*?)```', code, re.DOTALL)
            if diff_match:
                diff_patch = diff_match.group(1).strip()
            
            # Extract full file content
            content_match = re.search(r'FULL FILE CONTEXT:\n```[^\n]*\n(.*?)```', code, re.DOTALL)
            if content_match:
                full_content = content_match.group(1).strip()
        
        # Use expert reviewer
        findings = self.expert_reviewer.review(file_path, diff_patch, full_content)
        
        return {
            "status": "ok",
            "analysis": self._generate_summary(findings),
            "suggestions": findings,
            "findings_count": len(findings)
        }
    
    def _generate_summary(self, findings: List[Dict[str, Any]]) -> str:
        """Generate a text summary of findings."""
        if not findings:
            return "Code analysis complete. No significant issues found."
        
        summary_parts = [f"Found {len(findings)} issues"]
        
        # Group by severity
        by_severity = {}
        for finding in findings:
            severity = finding.get("severity", "medium")
            by_severity[severity] = by_severity.get(severity, 0) + 1
        
        for severity, count in by_severity.items():
            summary_parts.append(f"{severity}: {count}")
        
        return ", ".join(summary_parts)
    
    def cleanup(self) -> None:
        """Cleanup resources."""
        pass