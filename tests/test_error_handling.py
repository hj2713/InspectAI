"""Test error handling and graceful degradation.

Tests that failures in one agent don't break the pipeline and that
graceful exit messages are provided to users.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from src.orchestrator.orchestrator import OrchestratorAgent
from src.utils.error_handler import (
    safe_agent_execution,
    get_user_friendly_error_message,
    format_error_for_github_comment,
    create_partial_success_result,
    GracefulErrorHandler
)


def test_safe_agent_execution_success():
    """Test that safe_agent_execution works for successful operations."""
    @safe_agent_execution("test_agent")
    def successful_operation():
        return {"status": "ok", "result": "success"}
    
    result = successful_operation()
    assert result["status"] == "ok"
    assert result["result"] == "success"


def test_safe_agent_execution_handles_errors():
    """Test that safe_agent_execution catches errors and returns graceful results."""
    @safe_agent_execution("test_agent")
    def failing_operation():
        raise ValueError("Test error")
    
    result = failing_operation()
    assert result["status"] == "error"
    assert result["agent"] == "test_agent"
    assert result["error_type"] == "ValueError"
    assert "error_message" in result
    assert "technical_details" in result


def test_user_friendly_error_messages():
    """Test that technical errors are converted to user-friendly messages."""
    # Rate limit error
    error = Exception("429 rate limit exceeded")
    msg = get_user_friendly_error_message(error, "CodeReviewer")
    assert "high demand" in msg.lower()
    assert "minute" in msg.lower()
    
    # Timeout error
    error = Exception("Request timed out after 30s")
    msg = get_user_friendly_error_message(error, "BugDetector")
    assert "too long" in msg.lower()
    
    # Authentication error
    error = Exception("401 Unauthorized")
    msg = get_user_friendly_error_message(error, "SecurityAgent")
    assert "authentication" in msg.lower()
    
    # Generic error
    error = Exception("Unknown failure")
    msg = get_user_friendly_error_message(error, "TestAgent")
    assert "unexpected error" in msg.lower()


def test_partial_success_result():
    """Test creating partial success results."""
    successful = {
        "agent1": {"status": "ok", "result": "good"},
        "agent2": {"status": "ok", "result": "also good"}
    }
    failed = {
        "agent3": {"status": "error", "error_message": "Failed"}
    }
    
    result = create_partial_success_result(successful, failed, total_agents=3)
    
    assert result["status"] == "partial_success"
    assert result["success_count"] == 2
    assert result["failure_count"] == 1
    assert result["total_agents"] == 3
    assert "agent1" in result["successful_agents"]
    assert "agent3" in result["failed_agents"]


def test_format_error_for_github_comment():
    """Test formatting errors as GitHub comments."""
    error_info = {
        "agent": "CodeAnalyzer",
        "error_type": "TimeoutError",
        "error_message": "The analysis took too long",
        "technical_details": "Timeout after 60 seconds"
    }
    
    comment = format_error_for_github_comment(error_info, "/inspectai_review")
    
    assert "⚠️" in comment
    assert "InspectAI Error" in comment
    assert "/inspectai_review" in comment
    assert "CodeAnalyzer" in comment
    assert "too long" in comment
    assert "try again" in comment.lower()


def test_graceful_error_handler_suppresses_exceptions():
    """Test that GracefulErrorHandler suppresses exceptions."""
    executed = False
    
    with GracefulErrorHandler("test_operation") as handler:
        executed = True
        raise ValueError("Test error")
    
    assert executed
    assert handler.error is not None
    assert isinstance(handler.error, ValueError)


def test_orchestrator_continues_on_agent_failure():
    """Test that orchestrator continues when one agent fails."""
    config = {
        "analysis": {},
        "bug_detection": {},
        "security": {},
        "test_generation": {},
        "generation": {}
    }
    
    # Mock the agents
    with patch('src.orchestrator.orchestrator.CodeAnalysisAgent') as MockAnalysis, \
         patch('src.orchestrator.orchestrator.BugDetectionAgent') as MockBugs, \
         patch('src.orchestrator.orchestrator.SecurityAnalysisAgent') as MockSecurity, \
         patch('src.orchestrator.orchestrator.TestGenerationAgent') as MockTests, \
         patch('src.orchestrator.orchestrator.CodeGenerationAgent') as MockGen, \
         patch('src.orchestrator.orchestrator.ResearchAgent') as MockResearch, \
         patch('src.orchestrator.orchestrator.DocumentationAgent') as MockDocs:
        
        # Setup mock agents
        mock_analysis = Mock()
        mock_analysis.process.return_value = {"status": "ok", "suggestions": []}
        MockAnalysis.return_value = mock_analysis
        
        # This agent will fail
        mock_bugs = Mock()
        mock_bugs.process.side_effect = Exception("Bug detection failed")
        MockBugs.return_value = mock_bugs
        
        mock_security = Mock()
        mock_security.process.return_value = {"status": "ok", "vulnerabilities": []}
        MockSecurity.return_value = mock_security
        
        mock_tests = Mock()
        mock_tests.process.return_value = {"status": "ok", "tests": []}
        MockTests.return_value = mock_tests
        
        mock_gen = Mock()
        mock_gen.process.return_value = {"status": "ok", "code": "improved"}
        MockGen.return_value = mock_gen
        
        mock_research = Mock()
        MockResearch.return_value = mock_research
        
        mock_docs = Mock()
        MockDocs.return_value = mock_docs
        
        orchestrator = OrchestratorAgent(config)
        
        # Run full review - bug_detection will fail but others should continue
        result = orchestrator._handle_full_review({"code": "test code"}, "task123")
        
        # Should get partial success
        assert result["status"] == "partial_success"
        assert result["success_count"] == 4  # analysis, security, tests, generation
        assert result["failure_count"] == 1  # bug_detection
        assert "analysis" in result["successful_agents"]
        assert "security" in result["successful_agents"]
        assert "test_generation" in result["successful_agents"]
        assert "generation" in result["successful_agents"]
        assert "bug_detection" in result["failed_agents"]


def test_orchestrator_safe_execute_agent():
    """Test that _safe_execute_agent handles errors gracefully."""
    config = {
        "analysis": {},
        "bug_detection": {}
    }
    
    with patch('src.orchestrator.orchestrator.CodeAnalysisAgent') as MockAnalysis, \
         patch('src.orchestrator.orchestrator.BugDetectionAgent') as MockBugs, \
         patch('src.orchestrator.orchestrator.ResearchAgent') as MockResearch, \
         patch('src.orchestrator.orchestrator.SecurityAnalysisAgent') as MockSecurity, \
         patch('src.orchestrator.orchestrator.TestGenerationAgent') as MockTests, \
         patch('src.orchestrator.orchestrator.CodeGenerationAgent') as MockGen, \
         patch('src.orchestrator.orchestrator.DocumentationAgent') as MockDocs:
        
        # Setup failing agent
        mock_analysis = Mock()
        mock_analysis.process.side_effect = ValueError("LLM API error")
        MockAnalysis.return_value = mock_analysis
        
        # Setup other agents
        MockBugs.return_value = Mock()
        MockResearch.return_value = Mock()
        MockSecurity.return_value = Mock()
        MockTests.return_value = Mock()
        MockGen.return_value = Mock()
        MockDocs.return_value = Mock()
        
        orchestrator = OrchestratorAgent(config)
        
        # Execute failing agent
        result = orchestrator._safe_execute_agent("analysis", "test code")
        
        # Should return error dict instead of raising exception
        assert result["status"] == "error"
        assert result["agent"] == "analysis"
        assert result["error_type"] == "ValueError"
        assert "error_message" in result
        assert "LLM API error" in result["technical_details"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
