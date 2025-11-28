"""Centralized logging configuration for the multi-agent system.

Usage:
    from src.utils.logger import get_logger
    
    logger = get_logger(__name__)
    logger.info("This is an info message")
    logger.debug("Debug message")
    logger.error("Error occurred", exc_info=True)
    
Log files are stored in the 'logs/' directory with the following files:
    - app.log: All logs (INFO level and above)
    - debug.log: All logs including DEBUG
    - error.log: Only ERROR and CRITICAL logs
    
To view logs:
    $ tail -f logs/app.log          # Watch main logs
    $ tail -f logs/debug.log        # Watch all debug logs
    $ cat logs/error.log            # View errors only
    $ grep "ERROR" logs/app.log     # Search for errors
"""
import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


# Create logs directory
LOG_DIR = Path(__file__).parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Log format
DETAILED_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"
SIMPLE_FORMAT = "%(asctime)s | %(levelname)-8s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Global configuration
_configured = False


def setup_logging(
    log_level: str = "INFO",
    log_to_console: bool = True,
    log_to_file: bool = True,
    log_dir: Optional[Path] = None
) -> None:
    """Configure the global logging system.
    
    Args:
        log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_to_console: Whether to output logs to console
        log_to_file: Whether to write logs to files
        log_dir: Directory for log files (defaults to 'logs/')
    """
    global _configured
    
    if _configured:
        return
    
    log_dir = log_dir or LOG_DIR
    log_dir.mkdir(exist_ok=True)
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture all, filter at handler level
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Console handler
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, log_level.upper()))
        console_handler.setFormatter(logging.Formatter(SIMPLE_FORMAT, DATE_FORMAT))
        root_logger.addHandler(console_handler)
    
    if log_to_file:
        # Main application log (INFO+)
        app_handler = RotatingFileHandler(
            log_dir / "app.log",
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8"
        )
        app_handler.setLevel(logging.INFO)
        app_handler.setFormatter(logging.Formatter(DETAILED_FORMAT, DATE_FORMAT))
        root_logger.addHandler(app_handler)
        
        # Debug log (all levels)
        debug_handler = RotatingFileHandler(
            log_dir / "debug.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8"
        )
        debug_handler.setLevel(logging.DEBUG)
        debug_handler.setFormatter(logging.Formatter(DETAILED_FORMAT, DATE_FORMAT))
        root_logger.addHandler(debug_handler)
        
        # Error log (ERROR+)
        error_handler = RotatingFileHandler(
            log_dir / "error.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8"
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(logging.Formatter(DETAILED_FORMAT, DATE_FORMAT))
        root_logger.addHandler(error_handler)
    
    _configured = True
    
    # Log startup
    logger = logging.getLogger(__name__)
    logger.info(f"Logging initialized. Level: {log_level}, Console: {log_to_console}, Files: {log_to_file}")
    if log_to_file:
        logger.info(f"Log directory: {log_dir.absolute()}")


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for the given module name.
    
    Args:
        name: Usually __name__ from the calling module
        
    Returns:
        Configured logger instance
    """
    # Ensure logging is set up
    if not _configured:
        setup_logging(log_level=os.getenv("LOG_LEVEL", "INFO"))
    
    return logging.getLogger(name)


class AgentLogger:
    """Specialized logger for agent activities with structured output."""
    
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.logger = get_logger(f"agent.{agent_name}")
        self.task_id: Optional[str] = None
    
    def set_task_id(self, task_id: str) -> None:
        """Set current task ID for log correlation."""
        self.task_id = task_id
    
    def _format_message(self, message: str) -> str:
        """Format message with agent context."""
        prefix = f"[{self.agent_name}]"
        if self.task_id:
            prefix += f"[task:{self.task_id}]"
        return f"{prefix} {message}"
    
    def info(self, message: str, **kwargs) -> None:
        self.logger.info(self._format_message(message), **kwargs)
    
    def debug(self, message: str, **kwargs) -> None:
        self.logger.debug(self._format_message(message), **kwargs)
    
    def warning(self, message: str, **kwargs) -> None:
        self.logger.warning(self._format_message(message), **kwargs)
    
    def error(self, message: str, exc_info: bool = False, **kwargs) -> None:
        self.logger.error(self._format_message(message), exc_info=exc_info, **kwargs)
    
    def critical(self, message: str, exc_info: bool = True, **kwargs) -> None:
        self.logger.critical(self._format_message(message), exc_info=exc_info, **kwargs)
    
    def task_start(self, task_type: str, input_summary: str = "") -> None:
        """Log the start of a task."""
        self.info(f"Starting task: {task_type}. Input: {input_summary[:100]}...")
    
    def task_complete(self, task_type: str, status: str = "success") -> None:
        """Log task completion."""
        self.info(f"Completed task: {task_type}. Status: {status}")
    
    def llm_call(self, model: str, tokens: Optional[int] = None) -> None:
        """Log an LLM API call."""
        msg = f"LLM call to {model}"
        if tokens:
            msg += f" ({tokens} tokens)"
        self.debug(msg)
