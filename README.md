# Multi-Agent Code Review and Debugging Network

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A sophisticated multi-agent system powered by Large Language Models (LLMs) for automated code review, bug detection, security analysis, and code improvement.

## 🚀 Features

- **Multi-Agent Architecture**: 7 specialized agents working together
- **Code Analysis**: Comprehensive code quality review
- **Bug Detection**: Automatic identification of bugs and issues
- **Security Audit**: Vulnerability detection and remediation suggestions
- **Test Generation**: Automatic test case generation
- **Documentation**: Auto-generate docstrings and documentation
- **GitHub PR Review**: Review Pull Requests directly
- **Multiple LLM Providers**: OpenAI, Bytez, and local models (HuggingFace)
- **Async Support**: Parallel agent execution for faster results
- **CLI & Web API**: Multiple interfaces for integration

## 📋 Project Structure

```
├── src/
│   ├── agents/              # Agent implementations
│   │   ├── base_agent.py           # Abstract base class
│   │   ├── code_analysis_agent.py  # Code quality analysis
│   │   ├── code_generation_agent.py # Code improvement
│   │   ├── bug_detection_agent.py  # Bug detection
│   │   ├── security_agent.py       # Security analysis
│   │   ├── test_generation_agent.py # Test generation
│   │   ├── documentation_agent.py  # Documentation generation
│   │   └── research_agent.py       # Research/information gathering
│   ├── orchestrator/        # Task orchestration
│   │   └── orchestrator.py         # Main orchestrator
│   ├── github/              # GitHub integration
│   │   └── client.py               # GitHub API client
│   ├── llm/                 # LLM providers
│   │   ├── client.py               # OpenAI/Bytez client
│   │   └── local_client.py         # Local HuggingFace client
│   ├── langchain/           # LangChain integration
│   │   └── agents.py               # LangChain-powered agents
│   ├── memory/              # Agent memory system
│   │   └── agent_memory.py         # Conversation history
│   ├── api/                 # REST API
│   │   └── server.py               # FastAPI server
│   ├── utils/               # Utilities
│   │   └── logger.py               # Logging system
│   ├── cli.py               # Command-line interface
│   └── main.py              # Main entry point
├── tests/                   # Test suite
├── config/                  # Configuration
├── logs/                    # Log files (auto-created)
└── requirements.txt
```

## 🛠️ Installation

### 1. Clone the repository

```bash
git clone https://github.com/Yeshitha-co/COMSE6998-015-Fall-2025-Multi-Agent-Code-Review-and-Debugging-Network.git
cd COMSE6998-015-Fall-2025-Multi-Agent-Code-Review-and-Debugging-Network
```

### 2. Create virtual environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the project root:

```env
# LLM Provider (openai, bytez, or local)
LLM_PROVIDER=bytez

# API Keys (use the one matching your provider)
OPENAI_API_KEY=your-openai-key
BYTEZ_API_KEY=your-bytez-key

# GitHub (for PR reviews)
GITHUB_TOKEN=your-github-token

# Logging
LOG_LEVEL=INFO
```

## 📖 Usage

### Command Line Interface

```bash
# Review a file
python -m src.cli review path/to/file.py --type full_review

# Review inline code
python -m src.cli review "def add(a,b): return a+b" --type code_improvement

# Review a GitHub PR
python -m src.cli pr owner/repo 123 --post-comment

# Start the web server
python -m src.cli server --port 8000
```

### Python API

```python
from src.orchestrator.orchestrator import OrchestratorAgent
from config.default_config import ORCHESTRATOR_CONFIG

# Initialize
orchestrator = OrchestratorAgent(ORCHESTRATOR_CONFIG)

# Code Improvement
result = orchestrator.process_task({
    "type": "code_improvement",
    "input": {
        "code": "def add(a, b): return a + b",
        "requirements": ["Add type hints", "Add docstring"]
    }
})

# Full Review (all agents)
result = orchestrator.process_task({
    "type": "full_review",
    "input": {"code": your_code}
})

# Bug Detection
result = orchestrator.process_task({
    "type": "bug_fix",
    "input": {"code": buggy_code}
})

# Security Audit
result = orchestrator.process_task({
    "type": "security_audit",
    "input": {"code": code_to_audit}
})

# Cleanup
orchestrator.cleanup()
```

### REST API

Start the server:

```bash
python -m src.cli server --port 8000
```

Endpoints:

- `POST /review` - Review code
- `POST /pr-review` - Review GitHub PR
- `GET /tasks` - List available task types
- `GET /health` - Health check
- `GET /docs` - API documentation (Swagger UI)

Example request:

```bash
curl -X POST http://localhost:8000/review \
  -H "Content-Type: application/json" \
  -d '{"code": "def add(a,b): return a+b", "task_type": "code_improvement"}'
```

## 🤖 Supported Task Types

| Task Type          | Description                       |
| ------------------ | --------------------------------- |
| `code_improvement` | General code quality improvements |
| `bug_fix`          | Bug detection and fixing          |
| `security_audit`   | Security vulnerability analysis   |
| `test_generation`  | Generate test cases               |
| `documentation`    | Generate documentation            |
| `full_review`      | Comprehensive review (all agents) |
| `pr_review`        | GitHub Pull Request review        |

## 📊 Logging

Logs are stored in the `logs/` directory:

- `app.log` - Main application logs (INFO+)
- `debug.log` - Detailed debug logs
- `error.log` - Errors only

View logs:

```bash
# Watch main logs
tail -f logs/app.log

# View errors
cat logs/error.log

# Search for specific patterns
grep "ERROR" logs/app.log
```

## 🧪 Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=src --cov-report=html

# Run specific test file
pytest tests/test_agents.py -v
```

## 🔧 Configuration

Edit `config/default_config.py` to customize:

- Model selection per agent
- Temperature settings
- Token limits
- Provider defaults

## 📄 License

This project is part of COMSE6998-015 Fall 2025 coursework.

## 👥 Team

- Himanshu Jhawar
