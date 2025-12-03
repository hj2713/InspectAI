"""Graceful error handling utilities for agent failures.

Ensures that failures in one agent don't break the entire pipeline.
Provides user-friendly error messages instead of technical stack traces.
"""
from typing import Dict, Any, Optional, Callable
from functools import wraps
import traceback

from .logger import get_logger

logger = get_logger(__name__)


class AgentError(Exception):
    """Base exception for agent-related errors."""
    
    def __init__(self, agent_name: str, message: str, original_error: Optional[Exception] = None):
        self.agent_name = agent_name
        self.message = message
        self.original_error = original_error
        super().__init__(f"[{agent_name}] {message}")


class AgentTimeoutError(AgentError):
    """Agent operation timed out."""
    pass


class AgentLLMError(AgentError):
    """LLM API error (rate limit, timeout, etc.)."""
    pass


class AgentProcessingError(AgentError):
    """General processing error in agent."""
    pass


def safe_agent_execution(agent_name: str, fallback_result: Any = None):
    """Decorator to safely execute agent methods with graceful error handling.
    
    Args:
        agent_name: Name of the agent for logging
        fallback_result: Result to return on failure (default: empty dict with error status)
    
    Returns:
        Decorated function that catches exceptions and returns graceful results
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(f"[{agent_name}] Error during execution: {e}", exc_info=True)
                
                # Determine error type and message
                error_type = type(e).__name__
                user_message = get_user_friendly_error_message(e, agent_name)
                
                # Return graceful fallback result
                default_fallback = {
                    "status": "error",
                    "agent": agent_name,
                    "error_type": error_type,
                    "error_message": user_message,
                    "technical_details": str(e)
                }
                
                return fallback_result if fallback_result is not None else default_fallback
        
        return wrapper
    return decorator


def get_user_friendly_error_message(error: Exception, agent_name: str) -> str:
    """Convert technical error to user-friendly message.
    
    Args:
        error: The exception that occurred
        agent_name: Name of the agent that failed
        
    Returns:
        User-friendly error message
    """
    error_str = str(error).lower()
    
    # Rate limiting errors
    if "rate limit" in error_str or "429" in error_str:
        return f"The {agent_name} is experiencing high demand. Please try again in a minute."
    
    # Timeout errors
    if "timeout" in error_str or "timed out" in error_str:
        return f"The {agent_name} took too long to respond. This might be due to a large file or slow API. Try again or break the PR into smaller changes."
    
    # Authentication errors
    if "authentication" in error_str or "unauthorized" in error_str or "401" in error_str:
        return f"Authentication failed for {agent_name}. Please contact the repository owner to check API credentials."
    
    # API key errors
    if "api key" in error_str or "invalid key" in error_str:
        return f"API key error for {agent_name}. Please contact the repository owner to update credentials."
    
    # Connection errors
    if "connection" in error_str or "network" in error_str or "connect" in error_str:
        return f"Network error while connecting to {agent_name}. Please try again in a moment."
    
    # Model/service unavailable
    if "unavailable" in error_str or "503" in error_str or "502" in error_str:
        return f"The AI service for {agent_name} is temporarily unavailable. Please try again in a few minutes."
    
    # Generic fallback
    return f"The {agent_name} encountered an unexpected error. Our team has been notified. Please try again later."


def create_partial_success_result(
    successful_agents: Dict[str, Any],
    failed_agents: Dict[str, Dict[str, Any]],
    total_agents: int
) -> Dict[str, Any]:
    """Create a result object for partial success (some agents failed).
    
    Args:
        successful_agents: Dict of agent_name -> result for successful agents
        failed_agents: Dict of agent_name -> error_info for failed agents
        total_agents: Total number of agents attempted
        
    Returns:
        Structured result with both successes and failures
    """
    success_count = len(successful_agents)
    failure_count = len(failed_agents)
    
    return {
        "status": "partial_success" if success_count > 0 else "error",
        "success_count": success_count,
        "failure_count": failure_count,
        "total_agents": total_agents,
        "successful_agents": successful_agents,
        "failed_agents": failed_agents,
        "summary": f"{success_count}/{total_agents} agents completed successfully"
    }


def format_error_for_github_comment(
    error_info: Dict[str, Any],
    command: str,
    show_technical_details: bool = False
) -> str:
    """Format error information as a GitHub comment.
    
    Args:
        error_info: Error information from safe_agent_execution
        command: The command that was executed
        show_technical_details: Whether to include technical stack trace
        
    Returns:
        Formatted markdown for GitHub comment
    """
    agent_name = error_info.get("agent", "Unknown Agent")
    user_message = error_info.get("error_message", "An unexpected error occurred")
    
    message_parts = [
        f"## ⚠️ InspectAI Error",
        f"",
        f"**Command:** `{command}`",
        f"**Agent:** {agent_name}",
        f"",
        f"### What Happened",
        f"{user_message}",
        f"",
        f"### What You Can Do",
        f"- Try running the command again",
        f"- If the error persists, try a different command (e.g., `/inspectai_help`)",
        f"- For support, contact the repository maintainer",
        f"",
        f"---",
        f"*InspectAI is still learning. We appreciate your patience!*"
    ]
    
    if show_technical_details:
        message_parts.extend([
            f"",
            f"<details>",
            f"<summary>Technical Details (for debugging)</summary>",
            f"",
            f"```",
            f"Error Type: {error_info.get('error_type', 'Unknown')}",
            f"Technical Message: {error_info.get('technical_details', 'No details available')}",
            f"```",
            f"</details>"
        ])
    
    return "\n".join(message_parts)


def format_partial_success_for_github_comment(
    result: Dict[str, Any],
    command: str,
    successful_content: str
) -> str:
    """Format partial success (some agents succeeded, some failed) as GitHub comment.
    
    Args:
        result: Partial success result from create_partial_success_result
        command: The command that was executed
        successful_content: Content from successful agents
        
    Returns:
        Formatted markdown for GitHub comment
    """
    failed_agents = result.get("failed_agents", {})
    success_count = result.get("success_count", 0)
    failure_count = result.get("failure_count", 0)
    
    message_parts = [
        successful_content,
        f"",
        f"---",
        f"",
        f"### ⚠️ Partial Results",
        f"",
        f"**Completed:** {success_count} agent(s)",
        f"**Failed:** {failure_count} agent(s)",
        f""
    ]
    
    if failed_agents:
        message_parts.append("**Failed Agents:**")
        for agent_name, error_info in failed_agents.items():
            user_message = error_info.get("error_message", "Unknown error")
            message_parts.append(f"- ❌ **{agent_name}**: {user_message}")
        
        message_parts.extend([
            f"",
            f"*Some analysis may be incomplete. Try running `/inspectai_{command.replace('inspectai_', '')}` again.*"
        ])
    
    return "\n".join(message_parts)


class GracefulErrorHandler:
    """Context manager for graceful error handling in critical operations."""
    
    def __init__(self, operation_name: str, on_error: Optional[Callable] = None):
        """Initialize error handler.
        
        Args:
            operation_name: Name of the operation for logging
            on_error: Optional callback to execute on error (receives exception)
        """
        self.operation_name = operation_name
        self.on_error = on_error
        self.error = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            logger.error(
                f"Error in {self.operation_name}: {exc_val}",
                exc_info=(exc_type, exc_val, exc_tb)
            )
            self.error = exc_val
            
            if self.on_error:
                try:
                    self.on_error(exc_val)
                except Exception as callback_error:
                    logger.error(f"Error in error handler callback: {callback_error}")
            
            # Suppress the exception (graceful degradation)
            return True
        
        return False
