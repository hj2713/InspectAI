"""Comprehensive tests for the Multi-Agent Code Review System.

Run tests with:
    pytest tests/ -v
    pytest tests/ -v --cov=src --cov-report=html
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def sample_code():
    """Sample Python code for testing."""
    return '''
def calculate_average(numbers):
    total = 0
    for num in numbers:
        total += num
    return total / len(numbers)  # Bug: division by zero if list is empty

def fetch_user(user_id):
    query = f"SELECT * FROM users WHERE id = {user_id}"  # SQL injection vulnerability
    return execute_query(query)
'''


@pytest.fixture
def mock_llm_response():
    """Mock LLM response for testing."""
    return "Analysis: The code has potential issues.\n1. Division by zero risk\n2. SQL injection vulnerability"


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client."""
    mock = Mock()
    mock.chat.return_value = "Test response from LLM"
    return mock


# ============================================================================
# Agent Tests
# ============================================================================

class TestCodeAnalysisAgent:
    """Tests for CodeAnalysisAgent."""
    
    def test_initialization(self):
        """Test agent initializes correctly."""
        with patch('src.agents.code_analysis_agent.LLMClient') as mock_client:
            from src.agents.code_analysis_agent import CodeAnalysisAgent
            
            config = {"provider": "bytez", "model": "test-model"}
            agent = CodeAnalysisAgent(config)
            
            assert agent.config == config
            mock_client.assert_called_once()
    
    def test_process_returns_analysis(self, sample_code):
        """Test process method returns analysis results."""
        with patch('src.agents.code_analysis_agent.LLMClient') as mock_client_class:
            mock_client = Mock()
            mock_client.chat.return_value = "1. Add error handling\n2. Add type hints"
            mock_client_class.return_value = mock_client
            
            from src.agents.code_analysis_agent import CodeAnalysisAgent
            
            agent = CodeAnalysisAgent({"provider": "bytez"})
            result = agent.process(sample_code)
            
            assert result["status"] == "ok"
            assert "analysis" in result
            assert "suggestions" in result
            assert isinstance(result["suggestions"], list)
    
    def test_cleanup(self):
        """Test cleanup method doesn't raise errors."""
        with patch('src.agents.code_analysis_agent.LLMClient'):
            from src.agents.code_analysis_agent import CodeAnalysisAgent
            
            agent = CodeAnalysisAgent({})
            # Should not raise
            agent.cleanup()


class TestBugDetectionAgent:
    """Tests for BugDetectionAgent."""
    
    def test_initialization(self):
        """Test agent initializes correctly."""
        with patch('src.agents.bug_detection_agent.LLMClient') as mock_client:
            from src.agents.bug_detection_agent import BugDetectionAgent
            
            config = {"provider": "bytez"}
            agent = BugDetectionAgent(config)
            
            assert agent.config == config
    
    def test_process_detects_bugs(self, sample_code):
        """Test process method detects bugs."""
        with patch('src.agents.bug_detection_agent.LLMClient') as mock_client_class:
            mock_client = Mock()
            mock_client.chat.return_value = """
BUG 1: high - Division by zero
Location: calculate_average function
Problem: No check for empty list
Fix: Add check for empty list before division
"""
            mock_client_class.return_value = mock_client
            
            from src.agents.bug_detection_agent import BugDetectionAgent
            
            agent = BugDetectionAgent({"provider": "bytez"})
            result = agent.process(sample_code)
            
            assert result["status"] == "ok"
            assert "bugs" in result
            assert "bug_count" in result
    
    def test_parse_bugs(self):
        """Test bug parsing from response."""
        with patch('src.agents.bug_detection_agent.LLMClient'):
            from src.agents.bug_detection_agent import BugDetectionAgent
            
            agent = BugDetectionAgent({})
            
            response = """
BUG 1: critical - Null pointer
Location: line 10
Problem: Variable not checked
Fix: Add null check

BUG 2: medium - Missing validation
Location: line 20
Problem: Input not validated
Fix: Add validation
"""
            bugs = agent._parse_bugs(response)
            
            assert len(bugs) == 2
            assert bugs[0]["severity"] == "critical"
            assert bugs[1]["severity"] == "medium"


class TestSecurityAnalysisAgent:
    """Tests for SecurityAnalysisAgent."""
    
    def test_initialization(self):
        """Test agent initializes correctly."""
        with patch('src.agents.security_agent.LLMClient'):
            from src.agents.security_agent import SecurityAnalysisAgent
            
            agent = SecurityAnalysisAgent({})
            assert agent.VULNERABILITY_CATEGORIES is not None
    
    def test_calculate_risk_score(self):
        """Test risk score calculation."""
        with patch('src.agents.security_agent.LLMClient'):
            from src.agents.security_agent import SecurityAnalysisAgent
            
            agent = SecurityAnalysisAgent({})
            
            # No vulnerabilities
            assert agent._calculate_risk_score([]) == 0.0
            
            # Critical vulnerability
            vulns = [{"severity": "critical"}]
            score = agent._calculate_risk_score(vulns)
            assert score == 10.0
            
            # Mixed severities
            vulns = [
                {"severity": "high"},
                {"severity": "low"}
            ]
            score = agent._calculate_risk_score(vulns)
            assert 0 < score < 10


class TestTestGenerationAgent:
    """Tests for TestGenerationAgent."""
    
    def test_extract_code(self):
        """Test code extraction from markdown."""
        with patch('src.agents.test_generation_agent.LLMClient'):
            from src.agents.test_generation_agent import TestGenerationAgent
            
            agent = TestGenerationAgent({})
            
            response = """
Here are the tests:
```python
def test_example():
    assert True
```
"""
            code = agent._extract_code(response)
            assert "def test_example" in code
            assert "assert True" in code


class TestDocumentationAgent:
    """Tests for DocumentationAgent."""
    
    def test_process_docstring(self, sample_code):
        """Test docstring generation."""
        with patch('src.agents.documentation_agent.LLMClient') as mock_client_class:
            mock_client = Mock()
            mock_client.chat.return_value = """
```python
def calculate_average(numbers):
    \"\"\"Calculate the average of a list of numbers.\"\"\"
    pass
```
"""
            mock_client_class.return_value = mock_client
            
            from src.agents.documentation_agent import DocumentationAgent
            
            agent = DocumentationAgent({})
            result = agent.process({
                "code": sample_code,
                "doc_type": "docstring",
                "style": "google"
            })
            
            assert result["status"] == "ok"
            assert result["doc_type"] == "docstring"


# ============================================================================
# Orchestrator Tests
# ============================================================================

class TestOrchestratorAgent:
    """Tests for OrchestratorAgent."""
    
    @pytest.fixture
    def mock_orchestrator(self):
        """Create orchestrator with mocked agents."""
        with patch('src.orchestrator.orchestrator.ResearchAgent'), \
             patch('src.orchestrator.orchestrator.CodeAnalysisAgent'), \
             patch('src.orchestrator.orchestrator.CodeGenerationAgent'), \
             patch('src.orchestrator.orchestrator.BugDetectionAgent'), \
             patch('src.orchestrator.orchestrator.SecurityAnalysisAgent'), \
             patch('src.orchestrator.orchestrator.TestGenerationAgent'), \
             patch('src.orchestrator.orchestrator.DocumentationAgent'):
            
            from src.orchestrator.orchestrator import OrchestratorAgent
            
            orchestrator = OrchestratorAgent({})
            
            # Set up mock agent responses
            for name, agent in orchestrator.agents.items():
                agent.process.return_value = {
                    "status": "ok",
                    "result": f"Mock result from {name}"
                }
            
            # Special setup for specific agents
            orchestrator.agents["analysis"].process.return_value = {
                "status": "ok",
                "analysis": "Test analysis",
                "suggestions": ["suggestion1", "suggestion2"]
            }
            orchestrator.agents["bug_detection"].process.return_value = {
                "status": "ok",
                "bugs": [],
                "bug_count": 0
            }
            orchestrator.agents["security"].process.return_value = {
                "status": "ok",
                "vulnerabilities": [],
                "vulnerability_count": 0,
                "risk_score": 0
            }
            orchestrator.agents["generation"].process.return_value = {
                "status": "ok",
                "generated_code": "# improved code"
            }
            orchestrator.agents["test_generation"].process.return_value = {
                "status": "ok",
                "test_code": "def test(): pass"
            }
            
            yield orchestrator
            orchestrator.cleanup()
    
    def test_supported_tasks(self, mock_orchestrator):
        """Test that all supported tasks are defined."""
        expected_tasks = [
            "code_improvement",
            "bug_fix",
            "security_audit",
            "test_generation",
            "documentation",
            "full_review",
            "pr_review"
        ]
        assert mock_orchestrator.SUPPORTED_TASKS == expected_tasks
    
    def test_code_improvement_task(self, mock_orchestrator):
        """Test code improvement task execution."""
        task = {
            "type": "code_improvement",
            "input": {
                "code": "def add(a, b): return a + b",
                "requirements": ["Add type hints"]
            }
        }
        
        result = mock_orchestrator.process_task(task)
        
        assert result["status"] == "ok"
        assert "analysis" in result
        assert "generation" in result
    
    def test_bug_fix_task(self, mock_orchestrator):
        """Test bug fix task execution."""
        task = {
            "type": "bug_fix",
            "input": {"code": "def divide(a, b): return a / b"}
        }
        
        result = mock_orchestrator.process_task(task)
        
        assert result["status"] == "ok"
        assert "bug_report" in result
    
    def test_security_audit_task(self, mock_orchestrator):
        """Test security audit task execution."""
        task = {
            "type": "security_audit",
            "input": {"code": "query = f'SELECT * FROM users WHERE id = {user_id}'"}
        }
        
        result = mock_orchestrator.process_task(task)
        
        assert result["status"] == "ok"
        assert "security_report" in result
        assert "risk_score" in result
    
    def test_full_review_task(self, mock_orchestrator):
        """Test full review task execution."""
        task = {
            "type": "full_review",
            "input": {"code": "def hello(): print('Hello')"}
        }
        
        result = mock_orchestrator.process_task(task)
        
        assert result["status"] == "ok"
        assert "analysis" in result
        assert "bug_report" in result
        assert "security_report" in result
        assert "tests" in result
        assert "improved_code" in result
    
    def test_unknown_task_type(self, mock_orchestrator):
        """Test handling of unknown task type."""
        task = {
            "type": "unknown_task",
            "input": {}
        }
        
        result = mock_orchestrator.process_task(task)
        
        assert result["status"] == "error"
        assert "Unknown task type" in result["error"]
    
    def test_memory_storage(self, mock_orchestrator):
        """Test that task results are stored in memory."""
        task = {
            "type": "code_improvement",
            "input": {"code": "x = 1"}
        }
        
        result = mock_orchestrator.process_task(task)
        task_id = result.get("task_id")
        
        memory = mock_orchestrator.get_memory()
        context = memory.get_task_context(task_id)
        
        assert context is not None
        assert context.task_type == "code_improvement"


# ============================================================================
# Memory Tests
# ============================================================================

class TestAgentMemory:
    """Tests for AgentMemory."""
    
    def test_add_and_get_messages(self):
        """Test adding and retrieving messages."""
        from src.memory.agent_memory import AgentMemory
        
        memory = AgentMemory(max_history=10)
        
        memory.add_message("user", "Hello")
        memory.add_message("assistant", "Hi there!")
        
        history = memory.get_history()
        
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"
    
    def test_max_history_limit(self):
        """Test that history respects max limit."""
        from src.memory.agent_memory import AgentMemory
        
        memory = AgentMemory(max_history=3)
        
        for i in range(5):
            memory.add_message("user", f"Message {i}")
        
        history = memory.get_history()
        
        assert len(history) == 3
        assert "Message 2" in history[0]["content"]
    
    def test_task_context(self):
        """Test task context management."""
        from src.memory.agent_memory import AgentMemory
        
        memory = AgentMemory()
        
        context = memory.start_task("task-1", "code_improvement", {"code": "x = 1"})
        
        assert context.task_id == "task-1"
        assert context.task_type == "code_improvement"
        
        memory.add_task_result("task-1", "analysis", {"result": "ok"})
        
        retrieved = memory.get_task_context("task-1")
        assert "analysis" in retrieved.intermediate_results


class TestSharedMemory:
    """Tests for SharedMemory."""
    
    def test_set_and_get(self):
        """Test setting and getting values."""
        from src.memory.agent_memory import SharedMemory
        
        memory = SharedMemory()
        
        memory.set("key1", "value1")
        
        assert memory.get("key1") == "value1"
        assert memory.get("nonexistent") is None
        assert memory.get("nonexistent", "default") == "default"
    
    def test_subscribe(self):
        """Test subscription to key changes."""
        from src.memory.agent_memory import SharedMemory
        
        memory = SharedMemory()
        callback_values = []
        
        def callback(key, value):
            callback_values.append((key, value))
        
        memory.subscribe("key1", callback)
        memory.set("key1", "value1")
        memory.set("key1", "value2")
        
        assert len(callback_values) == 2
        assert callback_values[0] == ("key1", "value1")
        assert callback_values[1] == ("key1", "value2")


# ============================================================================
# GitHub Client Tests
# ============================================================================

class TestGitHubClient:
    """Tests for GitHubClient."""
    
    def test_parse_repo_url_formats(self):
        """Test parsing various repo URL formats."""
        from src.github.client import GitHubClient
        
        client = GitHubClient()
        
        # owner/repo format
        assert client._parse_repo_url("owner/repo") == ("owner", "repo")
        
        # HTTPS URL
        assert client._parse_repo_url("https://github.com/owner/repo") == ("owner", "repo")
        assert client._parse_repo_url("https://github.com/owner/repo.git") == ("owner", "repo")
        
        # Invalid URL should raise
        with pytest.raises(ValueError):
            client._parse_repo_url("invalid")
    
    def test_cleanup(self):
        """Test cleanup of temporary directories."""
        from src.github.client import GitHubClient
        import tempfile
        from pathlib import Path
        
        client = GitHubClient()
        
        # Create a temp dir and add to tracking
        temp = Path(tempfile.mkdtemp())
        client._temp_dirs.append(temp)
        
        assert temp.exists()
        
        client.cleanup()
        
        assert not temp.exists()
        assert len(client._temp_dirs) == 0


# ============================================================================
# Logger Tests
# ============================================================================

class TestLogger:
    """Tests for logging system."""
    
    def test_get_logger(self):
        """Test getting a logger instance."""
        from src.utils.logger import get_logger
        
        logger = get_logger("test_module")
        
        assert logger is not None
        assert logger.name == "test_module"
    
    def test_agent_logger(self):
        """Test AgentLogger functionality."""
        from src.utils.logger import AgentLogger
        
        agent_logger = AgentLogger("test_agent")
        
        agent_logger.set_task_id("task-123")
        
        # Should not raise
        agent_logger.info("Test message")
        agent_logger.debug("Debug message")
        agent_logger.task_start("test_task", "input summary")
        agent_logger.task_complete("test_task", "success")


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests (require mocking)."""
    
    @pytest.mark.asyncio
    async def test_async_task_processing(self):
        """Test async task processing."""
        with patch('src.orchestrator.orchestrator.ResearchAgent'), \
             patch('src.orchestrator.orchestrator.CodeAnalysisAgent'), \
             patch('src.orchestrator.orchestrator.CodeGenerationAgent'), \
             patch('src.orchestrator.orchestrator.BugDetectionAgent'), \
             patch('src.orchestrator.orchestrator.SecurityAnalysisAgent'), \
             patch('src.orchestrator.orchestrator.TestGenerationAgent'), \
             patch('src.orchestrator.orchestrator.DocumentationAgent'):
            
            from src.orchestrator.orchestrator import OrchestratorAgent
            
            orchestrator = OrchestratorAgent({})
            
            # Set up mock responses
            orchestrator.agents["analysis"].process.return_value = {
                "status": "ok",
                "suggestions": []
            }
            orchestrator.agents["generation"].process.return_value = {
                "status": "ok",
                "generated_code": "# code"
            }
            
            task = {
                "type": "code_improvement",
                "input": {"code": "x = 1"}
            }
            
            result = await orchestrator.process_task_async(task)
            
            assert result["status"] == "ok"
            orchestrator.cleanup()
