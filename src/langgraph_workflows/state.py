"""LangGraph State Definitions for Code Review Workflows.

This module defines the state schema used across all workflow nodes.
"""
from typing import List, Dict, Any, Optional, TypedDict, Annotated
from operator import add


class Finding(TypedDict):
    """Individual finding from an agent."""
    category: str
    severity: str
    description: str
    fix_suggestion: str
    confidence: float
    evidence: Dict[str, Any]
    location: str


class FileReviewState(TypedDict):
    """State for reviewing a single file."""
    # Input
    file_path: str
    file_content: str
    
    # Intermediate results
    code_review_findings: List[Finding]
    bug_findings: List[Finding]
    security_findings: List[Finding]
    
    # Aggregated results
    all_findings: Annotated[List[Finding], add]  # Accumulate findings
    filtered_findings: List[Finding]
    
    # Metadata
    errors: Annotated[List[str], add]  # Accumulate errors
    retry_count: int
    status: str  # "pending", "analyzing", "filtering", "complete", "failed"


class PRReviewState(TypedDict):
    """State for reviewing an entire Pull Request."""
    # Input
    repo_url: str
    pr_number: int
    
    # PR metadata
    pr_title: str
    pr_author: str
    pr_files: List[str]
    
    # Results per file
    file_reviews: Annotated[List[Dict[str, Any]], add]
    
    # Aggregated results
    total_findings: int
    findings_by_severity: Dict[str, int]
    findings_by_category: Dict[str, int]
    
    # GitHub integration
    summary_comment: str
    inline_comments: List[Dict[str, Any]]
    comment_posted: bool
    
    # Metadata
    errors: Annotated[List[str], add]
    status: str  # "fetching", "reviewing", "filtering", "posting", "complete", "failed"


class CodeReviewWorkflowState(TypedDict):
    """Generic state for code review workflows."""
    # Input
    code: str
    task_type: str  # "code_improvement", "bug_fix", "security_audit", "full_review"
    
    # Agent results
    analysis_result: Optional[Dict[str, Any]]
    bug_result: Optional[Dict[str, Any]]
    security_result: Optional[Dict[str, Any]]
    
    # Aggregated
    all_findings: Annotated[List[Finding], add]
    filtered_findings: List[Finding]
    
    # Output
    summary: str
    suggestions: List[str]
    
    # Control flow
    errors: Annotated[List[str], add]
    retry_count: int
    max_retries: int
    status: str
