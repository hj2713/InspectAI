"""LangGraph Agent Nodes for Code Review Workflows.

This module defines all the nodes (functions) that will be used in LangGraph workflows.
Each node corresponds to a step in the review process.
"""
from typing import Dict, Any
import logging

from .state import CodeReviewWorkflowState, FileReviewState, PRReviewState
from ..agents.code_analysis_agent import CodeAnalysisAgent
from ..agents.bug_detection_agent import BugDetectionAgent
from ..agents.security_agent import SecurityAnalysisAgent
from ..agents.filter_pipeline import create_default_pipeline

logger = logging.getLogger(__name__)


# ==================== Code Review Workflow Nodes ====================

def code_analysis_node(state: CodeReviewWorkflowState, config: Dict[str, Any]) -> Dict[str, Any]:
    """Run code analysis with specialized sub-agents.
    
    Args:
        state: Current workflow state
        config: Agent configuration
        
    Returns:
        Updated state with analysis results
    """
    logger.info("Running code analysis node...")
    
    try:
        agent = CodeAnalysisAgent(config.get("analysis", {}))
        result = agent.process(state["code"])
        
        # Extract findings
        findings = []
        for suggestion in result.get("suggestions", []):
            if isinstance(suggestion, dict):
                findings.append(suggestion)
        
        return {
            "analysis_result": result,
            "all_findings": findings,
            "status": "analyzing"
        }
    except Exception as e:
        logger.error(f"Code analysis failed: {e}")
        return {
            "errors": [f"Code analysis error: {str(e)}"],
            "status": "analyzing"
        }


def bug_detection_node(state: CodeReviewWorkflowState, config: Dict[str, Any]) -> Dict[str, Any]:
    """Run bug detection with specialized sub-agents.
    
    Args:
        state: Current workflow state
        config: Agent configuration
        
    Returns:
        Updated state with bug detection results
    """
    logger.info("Running bug detection node...")
    
    try:
        agent = BugDetectionAgent(config.get("bug_detection", {}))
        result = agent.process(state["code"])
        
        # Extract findings
        findings = []
        for bug in result.get("bugs", []):
            if isinstance(bug, dict):
                findings.append(bug)
        
        return {
            "bug_result": result,
            "all_findings": findings,
            "status": "analyzing"
        }
    except Exception as e:
        logger.error(f"Bug detection failed: {e}")
        return {
            "errors": [f"Bug detection error: {str(e)}"],
            "status": "analyzing"
        }


def security_analysis_node(state: CodeReviewWorkflowState, config: Dict[str, Any]) -> Dict[str, Any]:
    """Run security analysis with specialized sub-agents.
    
    Args:
        state: Current workflow state
        config: Agent configuration
        
    Returns:
        Updated state with security analysis results
    """
    logger.info("Running security analysis node...")
    
    try:
        agent = SecurityAnalysisAgent(config.get("security", {}))
        result = agent.process(state["code"])
        
        # Extract findings
        findings = []
        for vuln in result.get("vulnerabilities", []):
            if isinstance(vuln, dict):
                findings.append(vuln)
        
        return {
            "security_result": result,
            "all_findings": findings,
            "status": "analyzing"
        }
    except Exception as e:
        logger.error(f"Security analysis failed: {e}")
        return {
            "errors": [f"Security analysis error: {str(e)}"],
            "status": "analyzing"
        }


def filter_findings_node(state: CodeReviewWorkflowState, config: Dict[str, Any]) -> Dict[str, Any]:
    """Apply filter pipeline to all collected findings.
    
    Args:
        state: Current workflow state
        config: Filter configuration
        
    Returns:
        Updated state with filtered findings
    """
    logger.info("Running filter pipeline node...")
    
    try:
        all_findings = state.get("all_findings", [])
        
        if not all_findings:
            return {
                "filtered_findings": [],
                "status": "filtering"
            }
        
        # Create filter pipeline
        filter_config = config.get("filter", {})
        pipeline = create_default_pipeline(
            confidence_threshold=filter_config.get("confidence_threshold", 0.5),
            similarity_threshold=filter_config.get("similarity_threshold", 85),
            strict_evidence=filter_config.get("strict_evidence", False)
        )
        
        # Convert dicts to Finding objects if needed
        from ..agents.filter_pipeline import Finding
        finding_objects = []
        for f in all_findings:
            if isinstance(f, dict):
                finding_objects.append(Finding(
                    category=f.get("category", "Unknown"),
                    severity=f.get("severity", "medium"),
                    description=f.get("description", ""),
                    fix_suggestion=f.get("fix_suggestion", ""),
                    confidence=f.get("confidence", 0.5),
                    evidence=f.get("evidence", {}),
                    location=f.get("location", "")
                ))
            else:
                finding_objects.append(f)
        
        # Apply filters
        filtered = pipeline.process(finding_objects)
        
        logger.info(f"Filtered {len(all_findings)} → {len(filtered)} findings")
        
        # Convert back to dicts
        filtered_dicts = [f.to_dict() if hasattr(f, 'to_dict') else f for f in filtered]
        
        return {
            "filtered_findings": filtered_dicts,
            "status": "filtering"
        }
    except Exception as e:
        logger.error(f"Filtering failed: {e}")
        return {
            "errors": [f"Filtering error: {str(e)}"],
            "filtered_findings": state.get("all_findings", []),  # Fallback to unfiltered
            "status": "filtering"
        }


def generate_summary_node(state: CodeReviewWorkflowState, config: Dict[str, Any]) -> Dict[str, Any]:
    """Generate summary and suggestions from filtered findings.
    
    Args:
        state: Current workflow state
        config: Configuration
        
    Returns:
        Updated state with summary and suggestions
    """
    logger.info("Generating summary node...")
    
    findings = state.get("filtered_findings", [])
    
    if not findings:
        return {
            "summary": "Code review complete. No significant issues found.",
            "suggestions": [],
            "status": "complete"
        }
    
    # Group by severity
    by_severity = {}
    for f in findings:
        sev = f.get("severity", "medium")
        by_severity[sev] = by_severity.get(sev, 0) + 1
    
    # Group by category
    by_category = {}
    for f in findings:
        cat = f.get("category", "Unknown")
        by_category[cat] = by_category.get(cat, 0) + 1
    
    # Generate summary
    summary_parts = [f"Code review found {len(findings)} issues:\n"]
    
    for sev in ["critical", "high", "medium", "low"]:
        if sev in by_severity:
            summary_parts.append(f"- {sev.capitalize()}: {by_severity[sev]}")
    
    summary_parts.append("\nBy category:")
    for cat, count in sorted(by_category.items(), key=lambda x: x[1], reverse=True):
        summary_parts.append(f"- {cat}: {count}")
    
    summary = "\n".join(summary_parts)
    
    # Extract top suggestions
    suggestions = [
        f"{f.get('category', 'Issue')}: {f.get('description', '')}"
        for f in findings[:10]  # Top 10
    ]
    
    return {
        "summary": summary,
        "suggestions": suggestions,
        "status": "complete"
    }


# ==================== Error Handling & Retry Nodes ====================

def error_handler_node(state: CodeReviewWorkflowState, config: Dict[str, Any]) -> Dict[str, Any]:
    """Handle errors and decide whether to retry.
    
    Args:
        state: Current workflow state
        config: Configuration
        
    Returns:
        Updated state with retry decision
    """
    errors = state.get("errors", [])
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)
    
    if errors and retry_count < max_retries:
        logger.warning(f"Errors detected, retry {retry_count + 1}/{max_retries}")
        return {
            "retry_count": retry_count + 1,
            "status": "retrying"
        }
    elif errors:
        logger.error(f"Max retries reached, marking as failed")
        return {
            "status": "failed"
        }
    else:
        return {
            "status": state.get("status", "complete")
        }


# ==================== Routing Functions ====================

def should_run_bug_detection(state: CodeReviewWorkflowState) -> bool:
    """Determine if bug detection should run based on task type."""
    task_type = state.get("task_type", "full_review")
    return task_type in ["bug_fix", "full_review"]


def should_run_security_analysis(state: CodeReviewWorkflowState) -> bool:
    """Determine if security analysis should run based on task type."""
    task_type = state.get("task_type", "full_review")
    return task_type in ["security_audit", "full_review"]


def should_retry(state: CodeReviewWorkflowState) -> bool:
    """Determine if workflow should retry."""
    return state.get("status") == "retrying"


def has_errors(state: CodeReviewWorkflowState) -> bool:
    """Check if there are any errors."""
    return len(state.get("errors", [])) > 0
