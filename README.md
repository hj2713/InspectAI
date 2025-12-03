# InspectAI - Expert Code Review System

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Deployed on Render](https://img.shields.io/badge/Deployed%20on-Render-46E3B7.svg)](https://render.com)

A production-grade AI-powered code review system with an expert reviewer agent that analyzes code like a senior software developer. Deployed as a GitHub App for seamless PR reviews with parallel file processing.

---

## 🌟 Features

- **Expert Code Reviewer**: Single specialized agent that reviews code like a 10+ year senior developer
- **Diff-Aware Analysis**: Understands what was added, removed, or changed - provides contextual feedback
- **Multi-Language Support**: Reviews Python, JavaScript, TypeScript, Java, Go, and more
- **Parallel File Processing**: Analyzes multiple files simultaneously for 3-5x faster reviews
- **GitHub App Integration**: Automated PR reviews with inline comments on specific lines
- **Multiple LLM Support**: Google Gemini (default), OpenAI, Bytez
- **Deployed on Render**: 24/7 availability

---

## 🏗️ Architecture

### Agent Hierarchy

```
OrchestratorAgent
├── CodeAnalysisAgent
│   └── CodeReviewExpert - Senior developer-level review for all languages
│       • Detects logic errors & bugs in changed code
│       • Identifies security vulnerabilities
│       • Catches missing error handling
│       • Reviews performance issues
│       • Diff-aware: knows what was added vs removed
│
├── BugDetectionAgent (4 sub-agents)
│   ├── LogicErrorDetector   - Off-by-one, algorithm errors
│   ├── EdgeCaseAnalyzer     - None checks, boundaries
│   ├── TypeErrorDetector    - Type mismatches
│   └── RuntimeIssueDetector - Resource leaks, performance
│
└── SecurityAgent (4 sub-agents)
    ├── InjectionScanner     - SQL/command injection
    ├── AuthScanner          - Auth flaws
    ├── DataExposureScanner  - Hardcoded secrets
    └── DependencyScanner    - Unsafe library usage
```

### Key Improvements

- **Single Expert vs Multiple Sub-Agents**: Replaced 4 generic sub-agents with one comprehensive expert reviewer
- **Parallel Processing**: Files are analyzed concurrently (5 at a time) instead of sequentially
- **Context-Aware**: Expert understands diff context - won't suggest adding docstrings that were intentionally removed

---

## 🚀 GitHub Commands

Comment these in any PR to trigger InspectAI:

| Command | Description |
|---------|-------------|
| `/inspectai_review` | **Quick code review** - Reviews only the changed lines in your PR. Focuses on code quality (style, naming, structure). |
| `/inspectai_bugs` | **Deep bug scan** - Scans for bugs and errors caused by your changes. Finds logic errors, null pointers, race conditions, security issues. |
| `/inspectai_refactor` | **Refactoring suggestions** - Suggests improvements for changed code. Recommends better patterns and cleaner abstractions. |
| `/inspectai_help` | **Show help** - Displays all available commands. |

---

## ⚙️ Setup

### 1. Clone and Install

```bash
git clone https://github.com/hj2713/InspectAI.git
cd InspectAI
pip install -r requirements.txt
```

### 2. Configure Environment

Create a `.env` file:

```env
# LLM Provider (choose one)
GEMINI_API_KEY=your_gemini_key      # Recommended

# GitHub App
GITHUB_APP_ID=your_app_id
GITHUB_PRIVATE_KEY_PATH=path/to/key.pem
GITHUB_WEBHOOK_SECRET=your_secret
```

### 3. Run Locally

```bash
uvicorn src.api.server:app --reload --port 8000
```

---

## 🤖 Supported LLM Providers

| Provider | Model | Best For |
|----------|-------|----------|
| **Gemini** (Default) | `gemini-2.0-flash` | Fast, cost-effective |
| **OpenAI** | `gpt-4`, `gpt-4-turbo` | Highest quality |
| **Bytez** | `ibm-granite/granite-4.0-h-tiny` | Lightweight |

Switch providers in `config/default_config.py`:

```python
DEFAULT_PROVIDER = "gemini"  # Options: "gemini", "openai", "bytez"
```

---

## 📁 Project Structure

```
InspectAI/
├── src/
│   ├── agents/           # All 12 specialized agents
│   │   ├── code_review/  # NamingReviewer, QualityReviewer, etc.
│   │   ├── bug_detection/# LogicErrorDetector, EdgeCaseAnalyzer, etc.
│   │   └── security/     # InjectionScanner, AuthScanner, etc.
│   ├── api/              # FastAPI server & webhooks
│   ├── github/           # GitHub API client
│   ├── llm/              # LLM clients (Gemini, OpenAI, Bytez)
│   ├── memory/           # Vector store for context
│   └── orchestrator/     # Agent coordination
├── config/               # Configuration files
├── docs/                 # Documentation
└── tests/                # Unit tests
```

---

## 🔧 Configuration

Key settings in `config/default_config.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `DEFAULT_PROVIDER` | `gemini` | LLM provider to use |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Gemini model version |
| `max_tokens` | `10000` | Max response tokens |

---

## 📊 How It Works

1. **Webhook Received**: GitHub sends PR event to `/webhook/github`
2. **Command Parsed**: Extracts command from comment (e.g., `/inspectai_review`)
3. **Agents Execute**: Relevant agents analyze the changed code in parallel
4. **Findings Filtered**: Removes duplicates and low-quality findings
5. **Comments Posted**: Inline comments added to specific lines in the PR

---

## 🌐 Deployment

### Render (Current)

The app is deployed on Render with automatic deployments from the `main` branch.

**Webhook URL**: `https://inspectai-f0vx.onrender.com/webhook/github`

### Environment Variables on Render

- `GEMINI_API_KEY`
- `GITHUB_APP_ID`
- `GITHUB_PRIVATE_KEY` (base64 encoded)
- `GITHUB_WEBHOOK_SECRET`

---

## 🤝 Contributing

Areas for improvement:

1. Add more specialized agents (PerformanceReviewer, AccessibilityScanner)
2. Improve agent prompts for better accuracy
3. Add support for more programming languages
4. Enhance filter pipeline

---

## 📚 Documentation

- [GitHub PR Integration](docs/GITHUB_PR_INTEGRATION.md)
- [LLM Provider Guide](docs/LLM_PROVIDER_GUIDE.md)
- [GCP Deployment](docs/GCP_DEPLOYMENT.md)

---

## 🙏 Acknowledgments

- Inspired by [Ellipsis.dev](https://www.ellipsis.dev/blog/how-we-built-ellipsis)
- Powered by [Google Gemini](https://ai.google.dev/)
- Deployed on [Render](https://render.com) & [GCP](https://console.cloud.google.com)
