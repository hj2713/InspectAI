import unittest
from unittest.mock import MagicMock, patch
import sys

# Mock openai module before importing agents
sys.modules["openai"] = MagicMock()
sys.modules["langchain"] = MagicMock()
sys.modules["langchain_openai"] = MagicMock()
sys.modules["chromadb"] = MagicMock()

import logging

# Import agents
from src.agents.code_review.naming_reviewer import NamingReviewer
from src.agents.code_review.pep8_reviewer import PEP8Reviewer
from src.agents.bug_detection.logic_error_detector import LogicErrorDetector
from src.agents.security.injection_scanner import InjectionScanner

class TestPolyglotSupport(unittest.TestCase):
    def setUp(self):
        # Mock config
        self.config = {
            "model": "test-model",
            "temperature": 0.0,
            "max_tokens": 100,
            "provider": "gemini"
        }
        # Mock environment variable
        self.env_patcher = patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key'})
        self.env_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()
        
    def test_naming_reviewer_js(self):
        """Test NamingReviewer with JavaScript file."""
        agent = NamingReviewer(self.config)
        agent.client = MagicMock()
        agent.client.chat.return_value = "No issues found"
        
        code = "function my_function() { return 1; }"
        filename = "test.js"
        
        agent.analyze(code, filename=filename)
        
        # Verify prompt contains "JavaScript"
        call_args = agent.client.chat.call_args
        system_prompt = call_args[0][0][0]["content"]
        self.assertIn("JavaScript", system_prompt)
        
    def test_naming_reviewer_python(self):
        """Test NamingReviewer with Python file."""
        agent = NamingReviewer(self.config)
        agent.client = MagicMock()
        agent.client.chat.return_value = "No issues found"
        
        code = "def my_function(): return 1"
        filename = "test.py"
        
        agent.analyze(code, filename=filename)
        
        # Verify prompt contains "Python"
        call_args = agent.client.chat.call_args
        system_prompt = call_args[0][0][0]["content"]
        self.assertIn("Python", system_prompt)

    def test_pep8_reviewer_skip_js(self):
        """Test PEP8Reviewer skips non-Python files."""
        agent = PEP8Reviewer(self.config)
        agent.client = MagicMock()
        
        code = "function my_function() { return 1; }"
        filename = "test.js"
        
        findings = agent.analyze(code, filename=filename)
        
        # Should return empty list and NOT call LLM
        self.assertEqual(findings, [])
        agent.client.chat.assert_not_called()

    def test_logic_error_detector_html(self):
        """Test LogicErrorDetector with HTML file."""
        agent = LogicErrorDetector(self.config)
        agent.client = MagicMock()
        agent.client.chat.return_value = "No issues found"
        
        code = "<div></div>"
        filename = "test.html"
        
        agent.analyze(code, filename=filename)
        
        # Verify prompt contains "HTML"
        call_args = agent.client.chat.call_args
        system_prompt = call_args[0][0][0]["content"]
        self.assertIn("HTML", system_prompt)

    def test_injection_scanner_sql(self):
        """Test InjectionScanner with SQL file (simulated via extension or content)."""
        # Note: We didn't explicitly add .sql to the list in InjectionScanner, 
        # but it defaults to "code" and accepts filename. 
        # Let's test with .php which we added.
        agent = InjectionScanner(self.config)
        agent.client = MagicMock()
        agent.client.chat.return_value = "No issues found"
        
        code = "$query = 'SELECT * FROM users WHERE id = ' . $id;"
        filename = "test.php"
        
        agent.analyze(code, filename=filename)
        
        # Verify prompt contains "PHP"
        call_args = agent.client.chat.call_args
        system_prompt = call_args[0][0][0]["content"]
        self.assertIn("PHP", system_prompt)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    unittest.main()
