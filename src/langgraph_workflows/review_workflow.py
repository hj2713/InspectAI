"""LangGraph Workflow Definitions for Code Review.

This module defines the main workflow graphs using LangGraph.
"""
from typing import Dict, Any, Literal
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from .state import CodeReviewWorkflowState
from .agent_nodes import (
    code_analysis_node,
    bug_detection_node,
    security_analysis_node,
    filter_findings_node,
    generate_summary_node,
    error_handler_node,
    should_run_bug_detection,
    should_run_security_analysis,
    should_retry,
    has_errors
)


def create_code_review_workflow(config: Dict[str, Any]):
    """Create a LangGraph workflow for code review.
    
    This workflow:
    1. Runs code analysis (always)
    2. Conditionally runs bug detection (based on task_type)
    3. Conditionally runs security analysis (based on task_type)
    4. Filters all findings
    5. Generates summary
    6. Handles errors with retry logic
    
    Args:
        config: Configuration for agents and filters
        
    Returns:
        Compiled LangGraph workflow
    """
    # Create the graph
    workflow = StateGraph(CodeReviewWorkflowState)
    
    # Add nodes (pass config to each)
    workflow.add_node("code_analysis", lambda state: code_analysis_node(state, config))
    workflow.add_node("bug_detection", lambda state: bug_detection_node(state, config))
    workflow.add_node("security_analysis", lambda state: security_analysis_node(state, config))
    workflow.add_node("filter_findings", lambda state: filter_findings_node(state, config))
    workflow.add_node("generate_summary", lambda state: generate_summary_node(state, config))
    workflow.add_node("error_handler", lambda state: error_handler_node(state, config))
    
    # Set entry point
    workflow.set_entry_point("code_analysis")
    
    # Define edges from code_analysis
    def route_after_code_analysis(state: CodeReviewWorkflowState) -> Literal["bug_detection", "security_analysis", "filter_findings", "error_handler"]:
        """Route after code analysis based on task type and errors."""
        if has_errors(state):
            return "error_handler"
        
        if should_run_bug_detection(state):
            return "bug_detection"
        elif should_run_security_analysis(state):
            return "security_analysis"
        else:
            return "filter_findings"
    
    workflow.add_conditional_edges(
        "code_analysis",
        route_after_code_analysis,
        {
            "bug_detection": "bug_detection",
            "security_analysis": "security_analysis",
            "filter_findings": "filter_findings",
            "error_handler": "error_handler"
        }
    )
    
    # Define edges from bug_detection
    def route_after_bug_detection(state: CodeReviewWorkflowState) -> Literal["security_analysis", "filter_findings", "error_handler"]:
        """Route after bug detection."""
        if has_errors(state):
            return "error_handler"
        
        if should_run_security_analysis(state):
            return "security_analysis"
        else:
            return "filter_findings"
    
    workflow.add_conditional_edges(
        "bug_detection",
        route_after_bug_detection,
        {
            "security_analysis": "security_analysis",
            "filter_findings": "filter_findings",
            "error_handler": "error_handler"
        }
    )
    
    # Define edges from security_analysis
    def route_after_security(state: CodeReviewWorkflowState) -> Literal["filter_findings", "error_handler"]:
        """Route after security analysis."""
        if has_errors(state):
            return "error_handler"
        return "filter_findings"
    
    workflow.add_conditional_edges(
        "security_analysis",
        route_after_security,
        {
            "filter_findings": "filter_findings",
            "error_handler": "error_handler"
        }
    )
    
    # Filter findings always goes to summary
    workflow.add_edge("filter_findings", "generate_summary")
    
    # Summary is the end
    workflow.add_edge("generate_summary", END)
    
    # Error handler can retry or end
    def route_after_error(state: CodeReviewWorkflowState) -> Literal["code_analysis", "generate_summary"]:
        """Route after error handling."""
        if should_retry(state):
            return "code_analysis"  # Retry from beginning
        else:
            return "generate_summary"  # Give up, generate summary with what we have
    
    workflow.add_conditional_edges(
        "error_handler",
        route_after_error,
        {
            "code_analysis": "code_analysis",
            "generate_summary": "generate_summary"
        }
    )
    
    # Compile with checkpointing for state persistence
    checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer)


def create_simple_review_workflow(config: Dict[str, Any]):
    """Create a simplified workflow for basic code review (no conditionals).
    
    This workflow always runs:
    1. Code analysis
    2. Bug detection  
    3. Security analysis
    4. Filter findings
    5. Generate summary
    
    Args:
        config: Configuration for agents and filters
        
    Returns:
        Compiled LangGraph workflow
    """
    workflow = StateGraph(CodeReviewWorkflowState)
    
    # Add nodes
    workflow.add_node("code_analysis", lambda state: code_analysis_node(state, config))
    workflow.add_node("bug_detection", lambda state: bug_detection_node(state, config))
    workflow.add_node("security_analysis", lambda state: security_analysis_node(state, config))
    workflow.add_node("filter_findings", lambda state: filter_findings_node(state, config))
    workflow.add_node("generate_summary", lambda state: generate_summary_node(state, config))
    
    # Linear flow
    workflow.set_entry_point("code_analysis")
    workflow.add_edge("code_analysis", "bug_detection")
    workflow.add_edge("bug_detection", "security_analysis")
    workflow.add_edge("security_analysis", "filter_findings")
    workflow.add_edge("filter_findings", "generate_summary")
    workflow.add_edge("generate_summary", END)
    
    return workflow.compile()


# ==================== Workflow Execution Helpers ====================

def run_code_review(code: str, task_type: str = "full_review", config: Dict[str, Any] = None) -> Dict[str, Any]:
    """Execute code review workflow with LangGraph.
    
    Args:
        code: Source code to review
        task_type: Type of review ("code_improvement", "bug_fix", "security_audit", "full_review")
        config: Agent and filter configuration
        
    Returns:
        Final workflow state with results
    """
    if config is None:
        from ..config.default_config import ORCHESTRATOR_CONFIG, FILTER_CONFIG
        config = {
            "analysis": ORCHESTRATOR_CONFIG.get("analysis", {}),
            "bug_detection": ORCHESTRATOR_CONFIG.get("bug_detection", {}),
            "security": ORCHESTRATOR_CONFIG.get("security", {}),
            "filter": FILTER_CONFIG
        }
    
    # Create workflow
    workflow = create_code_review_workflow(config)
    
    # Initial state
    initial_state: CodeReviewWorkflowState = {
        "code": code,
        "task_type": task_type,
        "analysis_result": None,
        "bug_result": None,
        "security_result": None,
        "all_findings": [],
        "filtered_findings": [],
        "summary": "",
        "suggestions": [],
        "errors": [],
        "retry_count": 0,
        "max_retries": 3,
        "status": "pending"
    }
    
    # Run workflow
    final_state = workflow.invoke(initial_state)
    
    return final_state
