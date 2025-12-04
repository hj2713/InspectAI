# 📚 InspectAI - Complete Project Structure Guide

## 🎯 Overview
**InspectAI** is a **production-grade multi-agent AI code review system** that automatically analyzes GitHub pull requests using 12 specialized AI agents working in parallel.

**What it does:**
- 🤖 Automatically reviews code in GitHub PRs
- 🐛 Detects bugs, security issues, and code quality problems
- 💡 Provides intelligent suggestions and fixes
- ⚡ Runs 12 agents in parallel for speed
- 🔒 Works with multiple LLM providers (Gemini, OpenAI, Bytez)

---

## 📁 Root-Level Files & Directories

### Files in Root Directory

| File | Purpose |
|------|---------|
| **README.md** | Project overview with features, setup, and commands |
| **requirements.txt** | Python dependencies (FastAPI, LangChain, LLaMA, etc.) |
| **requirements-prod.txt** | Production-ready dependencies |
| **.env.example** | Template for environment configuration |
| **.env** | (created by you) Contains API keys and secrets |
| **Dockerfile** | Docker container configuration for deployment |
| **render.yaml** | Configuration for Render.com deployment |
| **.gitignore** | Git ignore patterns |
| **config/default_config.py** | Central configuration hub |
| **test_local_review.py** | Local testing script |

### Root Directories

| Directory | Purpose |
|-----------|---------|
| **src/** | Main source code |
| **config/** | Configuration files |
| **docs/** | Documentation and guides |
| **examples/** | Example scripts |
| **scripts/** | Deployment and setup scripts |
| **tests/** | Unit tests |

---

## 🔧 Configuration Directory: `config/`

### `config/default_config.py` - THE CENTRAL HUB ⭐

This is the **single source of truth** for all configuration:

```python
DEFAULT_PROVIDER = "gemini"  # Choose: "openai", "bytez", or "gemini"

ORCHESTRATOR_CONFIG = {
    "analysis": {...},           # Code style & quality review
    "bug_detection": {...},      # Finding bugs
    "security": {...},           # Security vulnerabilities
    "test_generation": {...},    # Creating tests
    "documentation": {...},      # Generating docs
    "research": {...},           # Research/understanding code
    "generation": {...},         # Code generation
}
```

**Key Settings:**
- `temperature`: How creative (0.1=focused, 0.7=creative)
- `max_tokens`: Response length limit
- `confidence_threshold`: How certain the AI must be
- `similarity_threshold`: For deduplication (85%)

---

## 📝 Documentation: `docs/`

| File | Contains |
|------|----------|
| **GITHUB_PR_INTEGRATION.md** | How agents post GitHub PR comments |
| **GCP_DEPLOYMENT.md** | Deploy to Google Cloud |
| **LLM_PROVIDER_GUIDE.md** | Setup OpenAI/Gemini/Bytez |
| **LANGGRAPH_GUIDE.md** | LangGraph workflow architecture |
| **enhanced_pr_review_example.py** | Example PR review code |

---

## 🚀 Main Source Code: `src/`

### `src/main.py` - Entry Point
Provides the main CLI interface:
```python
python -m src.main review myfile.py          # Review a file
python -m src.main pr owner/repo 123         # Review a PR
python -m src.main server --port 8000        # Start server
```

---

## 🤖 Agents: `src/agents/`

### Architecture: Hierarchical Multi-Agent System

```
OrchestratorAgent (main coordinator)
├── CodeAnalysisAgent (4 sub-agents)
├── BugDetectionAgent (4 sub-agents)
├── SecurityAnalysisAgent (4 sub-agents)
├── TestGenerationAgent
├── DocumentationAgent
├── ResearchAgent
└── CodeGenerationAgent
```

### Core Files

| File | Purpose |
|------|---------|
| **base_agent.py** | Abstract base class for all agents |
| **code_analysis_agent.py** | Orchestrator for code quality |
| **bug_detection_agent.py** | Orchestrator for bug finding |
| **security_agent.py** | Orchestrator for security scanning |
| **test_generation_agent.py** | Creates unit tests |
| **documentation_agent.py** | Generates documentation |
| **research_agent.py** | Context research and understanding |
| **code_generation_agent.py** | Code generation suggestions |
| **specialized_agent.py** | Generic specialized agent |
| **filter_pipeline.py** | Deduplicates and validates findings |

### Sub-Agents Explained

#### Code Review Sub-Agents (`code_review/`)

| Agent | Detects |
|-------|---------|
| **NamingReviewer** | Poor variable/function names, PEP 8 naming |
| **QualityReviewer** | Complexity, best practices, anti-patterns |
| **DuplicationDetector** | Repeated code patterns |
| **PEP8Reviewer** | Style violations, formatting issues |

#### Bug Detection Sub-Agents (`bug_detection/`)

| Agent | Detects |
|-------|---------|
| **LogicErrorDetector** | Off-by-one errors, algorithm mistakes |
| **EdgeCaseAnalyzer** | None checks, boundary conditions |
| **TypeErrorDetector** | Type mismatches, type safety issues |
| **RuntimeIssueDetector** | Resource leaks, performance issues |

#### Security Sub-Agents (`security/`)

| Agent | Detects |
|-------|---------|
| **InjectionScanner** | SQL injection, command injection |
| **AuthScanner** | Authentication flaws |
| **DataExposureScanner** | Hardcoded secrets, data leaks |
| **DependencyScanner** | Unsafe library versions |

---

## 🌐 API Server: `src/api/`

### `src/api/server.py` - FastAPI Web Server

Provides REST endpoints:

```
POST /review              - Code review task
POST /pr-review           - GitHub PR review
POST /webhook/github      - GitHub webhook (automatic PR reviews)
GET  /health              - Health check
POST /analyze             - Generic analysis
```

**Request Models:**
```python
ReviewRequest         # Code + task type
PRReviewRequest       # Repo + PR number
TaskResponse          # Status, results
```

### `src/api/webhooks.py` - GitHub Integration 🔗

Handles GitHub webhooks for **automatic PR reviews**:

**Commands you can use in PR comments:**
```
/inspectai_review       # Quick review of changed lines
/inspectai_bugs         # Deep bug scan
/inspectai_refactor     # Refactoring suggestions
/inspectai_help         # Show all commands
```

**What happens:**
1. Developer opens PR
2. GitHub sends webhook to your server
3. Server processes all changed files
4. AI agents analyze the code
5. Comments posted on the PR

---

## 🎭 Orchestrator: `src/orchestrator/`

### `src/orchestrator/orchestrator.py` - Main Coordinator

Coordinates all agents for different task types:

```python
SUPPORTED_TASKS = [
    "code_improvement",      # CodeAnalysisAgent
    "bug_fix",              # BugDetectionAgent
    "security_audit",       # SecurityAnalysisAgent
    "test_generation",      # TestGenerationAgent
    "documentation",        # DocumentationAgent
    "full_review",          # All agents
    "pr_review"             # PR-specific review
]
```

**Workflow:**
1. Receive code + task type
2. Select appropriate agents
3. Run agents in parallel
4. Aggregate and filter results
5. Return structured findings

---

## 🧠 LLM Management: `src/llm/`

### `src/llm/factory.py` - Provider Factory ⭐

**Single point for LLM configuration:**
```python
def get_llm_client(temperature=0.2, max_tokens=2048):
    # Returns appropriate client based on provider
    # Handles OpenAI, Gemini, or Bytez
```

### `src/llm/client.py` - LLM Client

Base class for all LLM interactions:
```python
response = client.generate(prompt, temperature=0.2)
tokens = client.count_tokens(text)
```

### `src/llm/local_client.py` - Local Model Support

Run LLMs locally without API calls:
```python
from src.llm.local_client import LocalLLMClient
client = LocalLLMClient(model="mistral")
```

---

## 💾 Memory System: `src/memory/`

### `src/memory/agent_memory.py` - Conversation Memory

Maintains conversation history:
```python
memory = AgentMemory(max_history=10)
memory.add_message("user", "Analyze this")
memory.add_message("assistant", "Analysis...")
history = memory.get_history()
```

### `src/memory/pr_memory.py` - PR-Specific Context

Stores PR findings and context:
```python
pr_memory = get_pr_memory(owner, repo, pr_number)
pr_memory.add_finding(finding)
bugs = pr_memory.get_bugs()
```

### `src/memory/vector_store.py` - Semantic Search

Vector database for code context:
```python
vector_store.add_documents(code_chunks)
similar = vector_store.search("authentication", top_k=5)
```

---

## 🔐 GitHub Integration: `src/github/`

### `src/github/client.py` - GitHub API Wrapper

Functions:
```python
client.clone_repo(owner/repo)           # Clone repository
files = client.get_pr_files(owner, repo, pr_num)
client.post_review_comment(owner, repo, pr_num, comment)
client.post_inline_comment(owner, repo, pr_num, comment, file, line)
```

---

## 🛠️ Utilities: `src/utils/`

| File | Purpose |
|------|---------|
| **logger.py** | Structured logging system |
| **language_detection.py** | Detect code language (Python, JS, etc.) |

---

## 📊 LangGraph Workflows: `src/langgraph_workflows/`

Advanced workflow orchestration using LangGraph:

| File | Purpose |
|------|---------|
| **review_workflow.py** | Main PR review workflow |
| **state.py** | Workflow state management |
| **agent_nodes.py** | Agent nodes for workflow |

---

## 🧪 Tests: `tests/`

| File | Tests |
|------|-------|
| **test_agents.py** | Individual agent tests |
| **test_imports.py** | Import validation |
| **test_orchestrator.py** | Orchestrator coordination |
| **test_vector_store.py** | Vector database |
| **test_polyglot.py** | Multi-language support |
| **sample_code_with_issues.py** | Sample buggy code |

---

## 📜 Scripts: `scripts/`

| Script | Purpose |
|--------|---------|
| **deploy_gcp.sh** | Deploy to Google Cloud Run |
| **setup_gcp.sh** | Setup GCP environment |
| **start_webhook_server.sh** | Start webhook server |

---

## 🎯 Examples: `examples/`

| File | Example |
|------|---------|
| **langgraph_workflow_example.py** | LangGraph workflow |
| **enhanced_pr_review_example.py** | PR review workflow |

---

## 📦 Deployment Files

| File | Purpose |
|------|---------|
| **Dockerfile** | Docker container |
| **render.yaml** | Render.com deployment config |
| **.gcloudignore** | Google Cloud ignore patterns |

---

## 🔄 Data Flow Diagram

```
GitHub PR Opened
       ↓
[GitHub Webhook] → Server
       ↓
[Orchestrator] selects agents
       ↓
┌─────────────────────────────┐
│ Parallel Agent Execution    │
├─────────────────────────────┤
│ CodeAnalysisAgent           │
│ BugDetectionAgent           │
│ SecurityAnalysisAgent       │
│ TestGenerationAgent         │
└─────────────────────────────┘
       ↓
[Filter Pipeline] - Dedup & Validate
       ↓
[Aggregate Findings]
       ↓
[Format Report]
       ↓
[GitHub Client] - Post Comments
       ↓
PR Comment Posted ✅
```

---

## 🚀 Quick Start

1. **Setup Environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

2. **Test Locally:**
   ```bash
   python test_local_review.py
   ```

3. **Run Server:**
   ```bash
   uvicorn src.api.server:app --reload --port 8000
   ```

4. **Deploy:**
   ```bash
   ./scripts/deploy_gcp.sh
   ```

---

## 📋 Configuration Priority

```
1. Environment Variables (.env)
2. Command-line Arguments
3. config/default_config.py
4. Built-in defaults
```

---

## 🎓 Key Concepts

| Concept | Meaning |
|---------|---------|
| **Agent** | AI component that performs specific task |
| **Sub-Agent** | Specialized agent that handles one aspect |
| **Orchestrator** | Coordinates multiple agents |
| **Filter Pipeline** | Removes duplicate/low-quality findings |
| **Vector Store** | Semantic search database |
| **Webhook** | GitHub notifies server of events |
| **LLM** | Large Language Model (AI) |

---

## 🔍 How to Find Things

| Want to... | Look in... |
|-----------|-----------|
| Add a new agent | `src/agents/` |
| Change API response | `src/api/server.py` |
| Modify PR comments | `src/api/webhooks.py` |
| Adjust confidence threshold | `config/default_config.py` |
| Fix GitHub auth | `src/github/client.py` |
| Add LLM provider | `src/llm/factory.py` |
| Update memory logic | `src/memory/` |

---

## ⚙️ Environment Variables Explained

```env
# LLM Provider
GEMINI_API_KEY=your_key           # Google Gemini API
OPENAI_API_KEY=your_key           # OpenAI GPT-4
BYTEZ_API_KEY=your_key            # Bytez API

# GitHub
GITHUB_TOKEN=your_token           # Personal Access Token
GITHUB_WEBHOOK_SECRET=random      # Webhook verification

# Server
PORT=8000                          # Server port
LOG_LEVEL=INFO                     # Logging verbosity
```

---

Generated: 2025-12-02
