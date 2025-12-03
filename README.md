# InspectAI - AI Code Review System

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Deployed on Render](https://img.shields.io/badge/Deployed%20on-Render-46E3B7.svg)](https://render.com)

Production-grade multi-agent system for automated code review, bug detection, and security analysis. Deployed as a GitHub App with 7 specialized agents working in parallel to provide comprehensive code analysis.

---

## 🌟 Features

- **7 Specialized Agents**: Research, Code Analysis, Bug Detection, Security, Test Generation, Code Generation, Documentation
- **Expert Code Reviewer**: Reviews code like a senior developer (10+ years experience)
- **Diff-Aware Analysis**: Context-aware feedback on what was added, removed, or changed
- **Parallel Processing**: Multi-file PRs analyzed concurrently (5 files at a time, 3-5x faster)
- **Multi-Language Support**: Python, JavaScript, TypeScript, Java, Go, Ruby, PHP, C++, Rust, and more
- **GitHub App Integration**: Inline PR comments on specific changed lines
- **Multiple LLM Support**: Google Gemini 2.0-flash (default), OpenAI GPT-4, Bytez Granite
- **24/7 Availability**: Deployed on Render with auto-scaling

---

## 🏗️ Architecture

### System Overview

```
GitHub PR → Webhook → FastAPI Server → OrchestratorAgent → 7 Specialized Agents
                                            ↓
                                      Filter Pipeline
                                            ↓
                                  Inline Comments on PR
```

### Agent Hierarchy

```
OrchestratorAgent (Coordinates all agents with ThreadPoolExecutor)
│
├── 1. ResearchAgent
│   └── Searches documentation and best practices
│
├── 2. CodeAnalysisAgent (REVIEW command)
│   └── CodeReviewExpert - Senior developer-level code review
│       • Diff-aware: understands additions vs removals
│       • Detects logic errors & bugs in changed code
│       • Identifies security vulnerabilities
│       • Catches missing error handling
│       • Reviews performance issues
│       • Multi-language: Python, JS, TS, Java, Go, Ruby, PHP, C++, Rust
│       • Practical, not pedantic - real issues only
│
├── 3. BugDetectionAgent (BUGS command - 4 sub-agents in parallel)
│   ├── LogicErrorDetector    - Off-by-one, wrong operators, algorithm errors
│   ├── EdgeCaseAnalyzer      - None/null checks, boundary conditions
│   ├── TypeErrorDetector     - Type mismatches, conversion errors
│   └── RuntimeIssueDetector  - Resource leaks, memory issues, performance
│
├── 4. SecurityAnalysisAgent (SECURITY audit - 4 sub-agents in parallel)
│   ├── InjectionScanner      - SQL/command injection vulnerabilities
│   ├── AuthScanner           - Authentication/authorization flaws
│   ├── DataExposureScanner   - Hardcoded secrets, sensitive data leaks
│   └── DependencyScanner     - Unsafe library usage, outdated packages
│
├── 5. TestGenerationAgent
│   └── Generates unit tests for changed code
│
├── 6. CodeGenerationAgent (REFACTOR command)
│   └── Suggests refactoring and code improvements
│
└── 7. DocumentationAgent
    └── Generates/updates documentation
```

### Key Architectural Improvements

- **Expert Reviewer**: Replaced 4 generic sub-agents (NamingReviewer, QualityReviewer, DuplicationDetector, PEP8Reviewer) with single comprehensive `CodeReviewExpert`
- **Parallel File Processing**: Files analyzed concurrently using `ThreadPoolExecutor` (5 workers) instead of sequential processing
- **Diff-Aware Context**: Expert understands git diffs - won't suggest "add docstring" when you intentionally removed it
- **Filter Pipeline**: Deduplication, confidence thresholds, and hallucination detection for high-quality findings

---

## 🚀 GitHub Commands

Comment these on any Pull Request to trigger InspectAI:

| Command | Agent Used | What It Does |
|---------|-----------|--------------|
| `/inspectai_review` | **CodeReviewExpert** | Reviews **only changed lines** in PR diff. Focuses on bugs, logic errors, security issues in new/modified code. Senior developer perspective. |
| `/inspectai_bugs` | **BugDetectionAgent** | Deep scan of **entire files** with changes. Finds logic errors, edge cases, type errors, runtime issues using 4 specialized sub-agents. |
| `/inspectai_refactor` | **CodeGenerationAgent** | Code improvement suggestions for changed code. Recommends better patterns, cleaner abstractions, performance optimizations. |
| `/inspectai_help` | - | Shows all available commands with descriptions. |

### How It Works

1. **Comment on PR**: Type `/inspectai_review` in a PR comment
2. **Webhook Triggered**: GitHub sends event to `https://inspectai-f0vx.onrender.com/webhook/github`
3. **Parallel Processing**: Files analyzed concurrently (up to 5 at a time)
4. **Expert Analysis**: CodeReviewExpert examines diff with senior developer mindset
5. **Inline Comments**: Specific issues posted on exact lines that need attention
6. **Summary Posted**: Overall PR review summary with findings count

---

## ⚙️ Setup & Installation

### Prerequisites

- Python 3.11+
- GitHub App credentials (for PR integration)
- LLM API key (Gemini recommended)

### 1. Clone Repository

```bash
git clone https://github.com/hj2713/InspectAI.git
cd InspectAI
pip install -r requirements.txt
```

### 2. Environment Variables

Create `.env` file in project root:

```env
# LLM Provider (Gemini recommended - fastest and most cost-effective)
GEMINI_API_KEY=your_gemini_api_key_here

# Alternative providers (optional)
# OPENAI_API_KEY=your_openai_key     # For GPT-4
# BYTEZ_API_KEY=your_bytez_key       # For Bytez Granite

# GitHub App Integration
GITHUB_APP_ID=your_github_app_id
GITHUB_PRIVATE_KEY_PATH=path/to/private-key.pem
GITHUB_WEBHOOK_SECRET=your_webhook_secret

# Optional: Override default provider
# LLM_PROVIDER=gemini  # Options: gemini, openai, bytez
```

### 3. Run Locally

```bash
# Start the webhook server
uvicorn src.api.server:app --reload --port 8000

# Or use the startup script
./scripts/start_webhook_server.sh
```

Server will be available at `http://localhost:8000`

### 4. Expose Webhook (for local testing)

```bash
# Install ngrok
brew install ngrok

# Expose port 8000
ngrok http 8000

# Use the ngrok URL as your GitHub webhook URL:
# https://xxxx.ngrok.io/webhook/github
```

---

## 🤖 LLM Providers

InspectAI supports 3 LLM providers. Configure in `config/default_config.py`:

| Provider | Model | Speed | Cost | Best For |
|----------|-------|-------|------|----------|
| **Gemini** (Default) | `gemini-2.0-flash` | ⚡ Fastest | 💰 Cheapest | Production, high-volume PRs |
| **OpenAI** | `gpt-4` | 🐢 Slower | 💰💰 Expensive | Highest quality analysis |
| **Bytez** | `granite-4.0-h-tiny` | ⚡ Fast | 💰 Cheap | Lightweight tasks |

### Change Provider

Edit `config/default_config.py`:

```python
DEFAULT_PROVIDER = "gemini"  # Options: "gemini", "openai", "bytez"

# Model configurations (auto-selected based on provider)
GEMINI_MODEL = "gemini-2.0-flash"
OPENAI_MODEL = "gpt-4"
BYTEZ_MODEL = "ibm-granite/granite-4.0-h-tiny"
```

All 7 agents automatically use the selected provider and model.

---

## 📁 Project Structure

```
InspectAI/
├── src/
│   ├── agents/                    # 7 specialized agents
│   │   ├── base_agent.py          # Abstract base class for all agents
│   │   ├── code_review_expert.py  # NEW: Expert code reviewer (senior dev level)
│   │   ├── code_analysis_agent.py # Orchestrates CodeReviewExpert
│   │   ├── bug_detection_agent.py # Orchestrates 4 bug detection sub-agents
│   │   ├── security_agent.py      # Orchestrates 4 security sub-agents
│   │   ├── research_agent.py      # Documentation & best practices search
│   │   ├── code_generation_agent.py # Code refactoring suggestions
│   │   ├── test_generation_agent.py # Unit test generation
│   │   ├── documentation_agent.py # Documentation generation
│   │   ├── filter_pipeline.py     # Deduplication & quality filtering
│   │   ├── bug_detection/         # 4 sub-agents for bug detection
│   │   │   ├── logic_error_detector.py
│   │   │   ├── edge_case_analyzer.py
│   │   │   ├── type_error_detector.py
│   │   │   └── runtime_issue_detector.py
│   │   └── security/              # 4 sub-agents for security analysis
│   │       ├── injection_scanner.py
│   │       ├── auth_scanner.py
│   │       ├── data_exposure_scanner.py
│   │       └── dependency_scanner.py
│   │
│   ├── api/                       # FastAPI server & webhooks
│   │   ├── server.py              # Main FastAPI app with health checks
│   │   └── webhooks.py            # GitHub webhook handler (PR comments)
│   │
│   ├── github/                    # GitHub API integration
│   │   └── client.py              # GitHub API wrapper with auth
│   │
│   ├── llm/                       # LLM client implementations
│   │   ├── client.py              # Unified LLM client factory
│   │   ├── local_client.py        # Local model support
│   │   └── device_info.py         # GPU/CPU detection
│   │
│   ├── memory/                    # Context & memory management
│   │   ├── agent_memory.py        # Short-term task memory
│   │   └── vector_store.py        # Long-term vector memory (FAISS)
│   │
│   ├── orchestrator/              # Agent coordination
│   │   └── orchestrator.py        # OrchestratorAgent - coordinates 7 agents
│   │
│   ├── utils/                     # Utilities
│   │   └── logger.py              # Structured logging
│   │
│   └── main.py                    # Entry point for CLI usage
│
├── config/                        # Configuration
│   └── default_config.py          # LLM provider & agent configs
│
├── tests/                         # Unit tests
│   ├── test_agents.py
│   └── test_orchestrator.py
│
├── scripts/                       # Deployment scripts
│   ├── start_webhook_server.sh    # Local webhook server startup
│   └── deploy_gcp.sh              # GCP deployment script
│
├── docs/                          # Documentation
│   └── GCP_DEPLOYMENT.md
│
├── Dockerfile                     # Docker image for deployment
├── requirements.txt               # Python dependencies
├── .env.example                   # Environment variable template
└── README.md                      # This file
```

---

## 🔧 Configuration

### Agent Settings

All agents configured in `config/default_config.py`:

```python
ORCHESTRATOR_CONFIG = {
    "analysis": {
        "temperature": 0.2,        # Low = more focused reviews
        "max_tokens": 10000,       # Max response length
        "confidence_threshold": 0.5 # Min confidence for findings
    },
    "bug_detection": {
        "temperature": 0.1,        # Very low = precise bug detection
        "max_tokens": 10000,
        "confidence_threshold": 0.6 # Higher threshold for bug reports
    },
    "security": {
        "temperature": 0.1,
        "max_tokens": 10000,
        "confidence_threshold": 0.65 # Highest threshold - security critical
    },
    "generation": {
        "temperature": 0.3,        # Medium = creative refactoring
        "max_tokens": 16000        # Larger for code generation
    }
}
```

### Key Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `DEFAULT_PROVIDER` | `gemini` | LLM provider: gemini, openai, bytez |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Gemini model version |
| `max_tokens` | 10000 - 16000 | Max response tokens per agent |
| `temperature` | 0.1 - 0.7 | Creativity (0=focused, 1=creative) |
| `confidence_threshold` | 0.5 - 0.65 | Min confidence for reporting findings |

### Parallel Processing

- **Files per PR**: Up to 5 files processed simultaneously
- **Sub-agents**: Bug detection (4) and security (4) run in parallel
- **ThreadPoolExecutor**: 4 max workers for agent coordination

---

## 📊 How It Works (Step-by-Step)

### `/inspectai_review` Flow

1. **PR Comment**: User comments `/inspectai_review` on GitHub PR
2. **Webhook Received**: GitHub POSTs to `/webhook/github` endpoint
3. **Authentication**: GitHub App installation token obtained
4. **File Fetching**: Changed files retrieved from PR via GitHub API
5. **Parallel Processing**: ThreadPoolExecutor spawns 5 workers
   - Each worker processes one file concurrently
   - Extracts diff patch (what changed)
   - Gets full file content for context
6. **Expert Analysis**: CodeReviewExpert agent analyzes each file
   - Parses git diff to understand additions/removals
   - Detects: logic errors, bugs, security issues, performance problems
   - Senior developer perspective - practical, not pedantic
7. **Finding Generation**: Expert returns structured findings with:
   - Line number, severity, category, description, fix suggestion
8. **Comment Posting**: GitHub API creates inline review comments
   - Posted on exact lines with issues
   - Formatted with emoji, severity, description, fix
9. **Summary**: Overall PR review summary posted as comment

### Performance

- **Sequential (old)**: 5 files × 8s = 40 seconds
- **Parallel (new)**: 5 files / 5 workers = 8 seconds
- **Speed improvement**: **5x faster** for multi-file PRs

---

## 🌐 Deployment

### Production (Render)

Currently deployed on Render with automatic deployments from `main` branch.

**Live Webhook URL**: `https://inspectai-f0vx.onrender.com/webhook/github`

#### Render Configuration

**Environment Variables:**
```
GEMINI_API_KEY=xxx
GITHUB_APP_ID=2371321
GITHUB_PRIVATE_KEY=xxx (base64 encoded)
GITHUB_WEBHOOK_SECRET=xxx
LLM_PROVIDER=gemini
PORT=8080
```

**Build Command:** `pip install -r requirements.txt`  
**Start Command:** `uvicorn src.api.server:app --host 0.0.0.0 --port $PORT`

**Auto-Deploy:** Pushes to `main` branch automatically trigger redeployment

### Local Development

```bash
# Start server
uvicorn src.api.server:app --reload --port 8000

# Expose webhook with ngrok
ngrok http 8000

# Update GitHub webhook URL to ngrok URL
```

### Docker Deployment

```bash
# Build image
docker build -t inspectai .

# Run container
docker run -p 8080:8080 \
  -e GEMINI_API_KEY=xxx \
  -e GITHUB_APP_ID=xxx \
  -e GITHUB_PRIVATE_KEY=xxx \
  -e GITHUB_WEBHOOK_SECRET=xxx \
  inspectai
```

### Google Cloud Platform

See detailed guide: [docs/GCP_DEPLOYMENT.md](docs/GCP_DEPLOYMENT.md)

---

## 🧪 Testing

### Run Tests

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_agents.py

# Run with coverage
pytest --cov=src tests/
```

### Test Coverage

- `tests/test_agents.py`: Agent initialization, processing, error handling
- `tests/test_orchestrator.py`: Task routing, agent coordination, memory management

### Manual Testing

1. Create a test PR with code changes
2. Comment `/inspectai_review` on the PR
3. Check for inline comments on changed lines
4. Verify summary comment is posted

---

## 🤝 Contributing

### Areas for Improvement

1. **More Specialized Agents**
   - PerformanceOptimizer: Analyze algorithmic complexity
   - AccessibilityScanner: Check web accessibility (WCAG)
   - DatabaseQueryOptimizer: SQL query analysis

2. **Enhanced Expert Reviewer**
   - Language-specific best practices (PEP 8 for Python, ESLint rules for JS)
   - Framework-specific patterns (React hooks, Django ORM)
   - Architecture pattern detection (SOLID, DRY violations)

3. **Better Context Understanding**
   - Import dependency analysis across files
   - PR description parsing for intent understanding
   - Historical context from previous PRs

4. **Performance Optimizations**
   - Cache LLM responses for similar code patterns
   - Incremental analysis (only re-analyze changed functions)
   - Streaming responses for faster feedback

### Development Setup

```bash
# Fork and clone
git clone https://github.com/your-username/InspectAI.git

# Install dev dependencies
pip install -r requirements.txt
pip install pytest pytest-cov black flake8

# Run linting
black src/
flake8 src/

# Run tests
pytest tests/ -v
```

---

## 📚 Documentation

- **GitHub PR Integration**: How the GitHub App integration works (coming soon)
- **LLM Provider Guide**: Detailed comparison of Gemini, OpenAI, Bytez (coming soon)
- **GCP Deployment**: [docs/GCP_DEPLOYMENT.md](docs/GCP_DEPLOYMENT.md)

---

## 🎯 Roadmap

- [ ] **Web Dashboard**: View review history, metrics, agent performance
- [ ] **Custom Rules**: Configure project-specific review rules
- [ ] **Multi-Repo Support**: Analyze dependencies across repositories
- [ ] **IDE Integration**: VS Code extension for real-time reviews
- [ ] **Automated Fixes**: Auto-create commits with suggested fixes
- [ ] **Team Analytics**: Track code quality trends over time

---

## 📄 License

MIT License - see LICENSE file for details

---

## 🙏 Acknowledgments

- **Inspired by**: [Ellipsis.dev](https://www.ellipsis.dev/blog/how-we-built-ellipsis) - Multi-agent code review architecture
- **Powered by**: [Google Gemini 2.0-flash](https://ai.google.dev/) - Fast, cost-effective LLM
- **Deployed on**: [Render](https://render.com) - Seamless cloud deployment
- **GitHub Integration**: [GitHub Apps API](https://docs.github.com/en/apps) - PR automation

---

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/hj2713/InspectAI/issues)
- **Discussions**: [GitHub Discussions](https://github.com/hj2713/InspectAI/discussions)
- **Email**: himanshujhawar@example.com

---

**Made with ❤️ for developers who care about code quality**
