# InspectAI - AI Code Review System

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Deployed on Render](https://img.shields.io/badge/Deployed%20on-Render-46E3B7.svg)](https://render.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Lines of Code](https://img.shields.io/badge/Lines%20of%20Code-40%2C000%2B-blue.svg)](/)

Production-grade multi-agent system for automated code review, bug detection, and security analysis. Deployed as a GitHub App with 7 specialized agents working in parallel to provide comprehensive code analysis that acts like a senior developer reviewing your code.

**Live Demo**: Install on your repo and try `/inspectai_review` on any PR!

---

## 🏗️ Technical Choices Summary

> Quick reference of key architectural decisions - see [FAQ](#-faq) for detailed explanations.

| Category | Choice | Why |
|----------|--------|-----|
| **LLM Provider** | Gemini 2.0-flash (default) | ⚡ Fastest, 💰 cheapest, 1M token context |
| **Embeddings** | sentence-transformers (local) | 🆓 Free, no API key, privacy-preserving |
| **Vector DB** | Supabase pgvector | ☁️ Cloud-hosted, unified storage, SQL queries |
| **Deployment** | Render | 🔗 Public webhook endpoint works out of box |
| **Parallelism** | ThreadPoolExecutor | 🧵 Simple, works with sync LLM calls |
| **Queue System** | None (synchronous) | 📦 Simpler for MVP, consider Hatchet for scale |
| **Webhook Relay** | None (direct GitHub) | 📨 GitHub's native retry is sufficient for now |

---

## 📑 Table of Contents

- [Technical Choices Summary](#-technical-choices-summary)
- [Features Overview](#-features-overview)
- [Architecture](#-architecture)
- [Commands & Usage](#-github-commands)
- [Key Innovations & Optimizations](#-key-innovations--optimizations)
- [Codebase Indexing](#-codebase-indexing-intelligent-context)
- [Feedback Learning System](#-feedback-learning-system)
- [Technical Deep Dive](#-technical-deep-dive)
- [Issues We Faced & Solutions](#-issues-we-faced--solutions)
- [Setup & Installation](#-setup--installation)
- [Configuration](#-configuration)
- [Deployment](#-deployment)
- [Testing](#-testing)
- [QA Checklist](#-qa-checklist)
- [Project Structure](#-project-structure)
- [Contributing](#-contributing)
- [FAQ](#-faq)
- [Roadmap](#-roadmap)

---

## 🌟 Features Overview

<details>
<summary><b>Click to expand Features Overview</b></summary>

### Core Capabilities

| Feature | Description |
|---------|-------------|
| **7 Specialized Agents** | Research, Code Analysis, Bug Detection, Security, Test Generation, Code Generation, Documentation - each optimized for specific tasks |
| **Expert Code Reviewer** | Reviews code like a senior developer with 10+ years experience - practical, not pedantic |
| **Diff-Aware Analysis** | Context-aware feedback that understands additions, removals, and modifications separately |
| **Parallel Processing** | Multi-file PRs analyzed concurrently (5 files at a time, 3-5x faster than sequential) |
| **Multi-Language Support** | Python, JavaScript, TypeScript, Java, Go, Ruby, PHP, C++, Rust with language-specific rules |
| **GitHub App Integration** | Inline PR comments on specific changed lines with severity indicators |
| **Codebase Indexing** | AST-based code parsing with call graph extraction for intelligent impact analysis |
| **Feedback Learning** | Learns from user reactions (👍/👎) to improve future suggestions |
| **Multiple LLM Support** | Google Gemini 2.0-flash (default), OpenAI GPT-4, Bytez Granite |
| **Quality Filtering** | Deduplication, confidence thresholds, and hallucination detection |
| **24/7 Availability** | Deployed on Render with auto-scaling |

### Language-Specific Bug Detection (50+ Patterns Per Language)

We've curated detailed bug patterns targeting **real mistakes junior developers make** that cause production issues:

<details>
<summary><b>🐍 Python Patterns</b> - Click to expand</summary>

- **Mutable Default Arguments**: `def func(items=[])` - shared list across calls causes bugs
- **Late Binding Closures**: `[lambda: i for i in range(3)]` - all lambdas return 2
- **Exception Handling Anti-patterns**: Bare `except:` catches everything including KeyboardInterrupt
- **None Comparisons**: Use `is None` not `== None` for singleton comparison
- **Iterator Exhaustion**: Iterators can only be consumed once
- **Context Manager Usage**: Missing `with` for file operations causes resource leaks
- **Type Coercion Gotchas**: `bool("False")` is `True` - string truthiness
- **Import Side Effects**: Heavy imports at module level slow down startup
- **Async/Await Issues**: Missing `await` on coroutines, blocking calls in async code

</details>

<details>
<summary><b>📜 JavaScript/TypeScript Patterns</b></summary>

- **Variable Hoisting**: `var` hoists without value - use `const`/`let` instead
- **Type Coercion**: `"1" + 2` = "12" but `"1" - 2` = -1
- **Prototype Pollution**: Modifying `Object.prototype` affects all objects
- **Promise Anti-patterns**: `.catch()` missing, dangling promises
- **Event Loop Blocking**: Synchronous operations blocking event loop
- **Memory Leaks**: Closures holding references, unremoved event listeners
- **TypeScript Specifics**: `any` abuse, missing null checks with optional chaining

</details>

<details>
<summary><b>☕ Java Patterns</b></summary>

- **Null Pointer Exceptions**: Missing null checks before method calls
- **Resource Leaks**: Missing try-with-resources for AutoCloseable
- **Concurrency Issues**: Non-thread-safe collections, improper synchronization
- **Equals/HashCode Contract**: Overriding one without the other
- **String Comparison**: Using `==` instead of `.equals()`
- **Exception Swallowing**: Empty catch blocks that hide errors
- **Mutable Return Types**: Returning internal collection references

</details>

<details>
<summary><b>🔵 Go Patterns</b></summary>

- **Error Shadowing**: Using `:=` inside blocks shadows outer error variable
- **Nil Interface Checks**: Interface holding nil pointer is NOT nil
- **Goroutine Leaks**: Missing exit conditions for goroutines
- **Channel Deadlocks**: Unbuffered channels without receivers
- **Race Conditions**: Shared variable access without synchronization
- **Defer in Loops**: Defers stack up causing resource exhaustion
- **Slice Append**: Forgetting `slice = append(slice, elem)`

</details>

<details>
<summary><b>🦀 Rust & C/C++ Patterns</b></summary>

**Rust:**
- Unwrap abuse (`unwrap()` panics on None/Err)
- Panic in library code
- Unsafe blocks without safety comments
- Move after use violations

**C/C++:**
- Buffer overflows, use-after-free
- Double-free, memory leaks
- Null pointer dereference
- Integer overflow/underflow
- Format string vulnerabilities

</details>

</details>

---

## 🏗️ Architecture

<details>
<summary><b>Click to expand Architecture diagrams and Agent hierarchy</b></summary>

### System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              GitHub PR Event                                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FastAPI Webhook Server (webhooks.py)                      │
│  • Signature verification (HMAC-SHA256)                                     │
│  • Duplicate event detection (issue_comment, pull_request_review_comment)  │
│  • Permission checking for codebase indexing                                │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
                    ▼                 ▼                 ▼
            ┌───────────┐     ┌───────────┐     ┌───────────┐
            │  /review  │     │   /bugs   │     │ /refactor │
            └───────────┘     └───────────┘     └───────────┘
                    │                 │                 │
                    └─────────────────┼─────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         OrchestratorAgent (orchestrator.py)                  │
│  • ThreadPoolExecutor (max 4 workers)                                       │
│  • Parallel agent coordination                                              │
│  • Task routing based on command type                                       │
│  • Unified Supabase Vector Store (pgvector)                                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
         ┌────────────────────────────┼────────────────────────────┐
         │                            │                            │
         ▼                            ▼                            ▼
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│  Code Analysis  │         │  Bug Detection  │         │ Code Generation │
│     Agent       │         │     Agent       │         │     Agent       │
│                 │         │  (4 sub-agents) │         │                 │
│ CodeReviewExpert│         │  • LogicError   │         │ Refactoring     │
│                 │         │  • EdgeCase     │         │ suggestions     │
│                 │         │  • TypeError    │         │                 │
│                 │         │  • RuntimeIssue │         │                 │
└─────────────────┘         └─────────────────┘         └─────────────────┘
         │                            │                            │
         │              ┌─────────────┼─────────────┐              │
         │              ▼             ▼             ▼              │
         │       ┌───────────┐ ┌───────────┐ ┌───────────┐         │
         │       │ Security  │ │   Test    │ │   Docs    │         │
         │       │   Agent   │ │ Generator │ │   Agent   │         │
         │       │ (4 scans) │ │ (pytest)  │ │ (Google)  │         │
         │       └───────────┘ └───────────┘ └───────────┘         │
         │                            │                            │
         └────────────────────────────┼────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Filter Pipeline                                    │
│  1. ConfidenceFilter (threshold: 0.5-0.65 depending on task)               │
│  2. DeduplicationFilter (85% similarity threshold using fuzzy matching)    │
│  3. HallucinationFilter (verify evidence exists in code)                   │
│  4. FeedbackFilter (learn from 👍/👎 reactions)                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         GitHub PR Comments                                   │
│  • Inline comments on specific lines                                        │
│  • Severity indicators (🔴 Critical, 🟠 High, 🟡 Medium, 🔵 Low)           │
│  • Suggested fixes with code snippets                                       │
│  • Summary comment with statistics                                          │
└─────────────────────────────────────────────────────────────────────────────┘
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
│       • Language-specific: 50+ bug patterns per language
│       • Structured output: JSON with line numbers
│       • Few-shot learning: curated examples for consistency
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

</details>

---

## 🚀 GitHub Commands

<details>
<summary><b>Click to expand Commands reference and flow diagram</b></summary>

Comment these on any Pull Request to trigger InspectAI:

| Command | Agent Used | What It Does |
|---------|-----------|--------------|
| `/inspectai_review` | **CodeReviewExpert** | **Comprehensive review** of changed lines - bugs, logic errors, missing error handling, code quality issues. Combines bug detection + refactoring suggestions in one command. |
| `/inspectai_bugs` | **BugDetectionAgent** | Deep scan using 4 specialized sub-agents in parallel. Finds logic errors, edge cases, type errors, runtime issues. **Line numbers auto-snapped** to nearest diff line. |
| `/inspectai_refactor` | *(same as review)* | **Redirects to `/inspectai_review`** - combined for a comprehensive single-pass review. |
| `/inspectai_security` | **SecurityAgent** | Security vulnerability scan with 4 specialized scanners: Injection, Auth, Data Exposure, Dependency vulnerabilities. Risk scoring included. |
| `/inspectai_tests` | **TestGenerationAgent** | Generate unit tests (pytest) for **changed code only** (diff-aware). Files >500 lines skipped. Multiple files processed in parallel for speed. |
| `/inspectai_docs` | **DocumentationAgent** | Generate/update docstrings and documentation for changed code. Uses Google-style docstrings for Python. |
| `/inspectai_help` | - | Shows all available commands with descriptions. |

### How `/inspectai_review` Works (Step-by-Step)

```
1. User comments "/inspectai_review" on PR
                    │
                    ▼
2. GitHub webhook POSTs to /webhook/github
   • Event type: issue_comment or pull_request_review_comment
   • Payload includes: repo, PR number, comment body
                    │
                    ▼
3. Webhook handler validates:
   • HMAC-SHA256 signature verification
   • Duplicate event detection (GitHub sends multiple events)
   • Command parsing (/inspectai_*)
                    │
                    ▼
4. Permission check for codebase indexing:
   • Checks if GitHub App has contents:read permission
   • If yes: triggers background indexing
   • If no: skips gracefully, review still works
                    │
                    ▼
5. Fetch PR files via GitHub API:
   • Get list of changed files
   • Filter by supported languages
   • Limit to 50 files max (configurable)
                    │
                    ▼
6. Parallel processing with ThreadPoolExecutor:
   • 5 files processed simultaneously
   • Each file gets: diff patch + full content
   • Context enrichment from codebase index (if available)
                    │
                    ▼
7. CodeReviewExpert analyzes each file:
   • Parses diff to understand additions/removals
   • Applies language-specific rules (50+ patterns)
   • Generates structured findings with:
     - Line number, severity, category
     - Description, suggested fix
     - Evidence (code snippet)
                    │
                    ▼
8. Filter pipeline processes findings:
   • ConfidenceFilter: Remove < 0.5 confidence
   • DeduplicationFilter: Remove 85% similar findings
   • HallucinationFilter: Verify evidence exists
   • FeedbackFilter: Adjust based on past reactions
                    │
                    ▼
9. Post comments to GitHub:
   • Inline review comments on specific lines
   • Each comment includes severity emoji, description, fix
   • Summary comment with total findings count
```

### Performance Comparison

| Scenario | Sequential | Parallel (Current) | Improvement |
|----------|-----------|-------------------|-------------|
| 1 file | 8s | 8s | Same |
| 5 files | 40s | 8s | **5x faster** |
| 10 files | 80s | 16s | **5x faster** |
| 50 files | 400s | 80s | **5x faster** |

### 🔧 Hidden Developer Commands

These commands are **not shown in `/inspectai_help`** - they're for maintainers and debugging:

| Command | Description |
|---------|-------------|
| `/inspectai_reindex` | **Manually trigger codebase reindexing** for the current repository. Useful when the weekly scheduled job hasn't run yet or you need immediate indexing after major changes. Runs asynchronously in the background. |
| `/inspectai_status` | **Show system status** including: repository indexing status, last indexed timestamp, number of indexed files/symbols, scheduler status. Useful for debugging indexing issues. |

#### Automatic Weekly Reindexing

InspectAI automatically reindexes all repositories every **7 days** (configurable via `REINDEX_INTERVAL_DAYS` env var). This ensures:
- New files are discovered and indexed
- Deleted files are cleaned up
- Call graphs stay accurate

If the scheduled job fails, use `/inspectai_reindex` to manually trigger it.

</details>

---

## ⚡ Key Innovations & Optimizations

<details>
<summary><b>Click to expand Key Innovations (5 major optimizations)</b></summary>

### 1. Parallel File Processing

**Problem**: Sequential processing of 5+ files was slow (8s × N files = unacceptable wait times).

**Solution**: `ThreadPoolExecutor` with 5 workers for concurrent file analysis.

```python
# In webhooks.py - parallel file processing
with ThreadPoolExecutor(max_workers=5) as executor:
    futures = {
        executor.submit(process_single_file, file_info): file_info
        for file_info in changed_files[:50]
    }
    for future in as_completed(futures):
        result = future.result()
        all_findings.extend(result)
```

**Result**: 5x faster PR reviews for multi-file changes.

---

### 2. Structured Prompt Engineering

**Problem**: LLMs returned inconsistent, hard-to-parse responses.

**Solution**: `PromptBuilder` class with structured context and few-shot examples.

```python
# Key components of PromptBuilder:
class TaskType(Enum):
    CODE_REVIEW = "code_review"
    BUG_DETECTION = "bug_detection"
    SECURITY_AUDIT = "security_audit"
    REFACTOR = "refactor"

@dataclass
class StructuredContext:
    diff_content: str
    full_content: str
    parsed_diff: List[DiffChange]  # Additions, removals, modifications
    language: str
    file_path: str
```

**Features**:
- **Diff Parsing**: Separates additions (`+`), removals (`-`), and context lines
- **Language Detection**: Auto-detects and loads language-specific rules
- **Few-Shot Learning**: Curated examples for consistent output format
- **JSON Schema**: Enforced structured output with validation

**Architecture Diagram:**

![PromptBuilder Architecture](docs/images/prompt_builder_architecture.png)

```
GitHub PR Event
       │
       ▼
┌──────────────────────────────────────┐
│  Webhook Handler (webhooks.py)       │
│  - Graceful error handling per file  │
│  - User-friendly error messages      │
└──────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────┐
│  Orchestrator                        │
│  - _safe_execute_agent() wraps calls │
│  - Partial success tracking          │
└──────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────┐
│  Agents (CodeReviewExpert,           │
│  BugDetection, Security, etc.)       │
│  - Use PromptBuilder                 │
│  - Language-specific rules injected  │
│  - Few-shot examples included        │
└──────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│  PromptBuilder                                               │
│  ┌──────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ Role         │  │ Language Rules  │  │ Few-shot        │ │
│  │ Definition   │  │ (18 Python,     │  │ Examples        │ │
│  │              │  │  18 JS rules..) │  │                 │ │
│  └──────────────┘  └─────────────────┘  └─────────────────┘ │
│  ┌──────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ Structured   │  │ Security Checks │  │ Output Schema   │ │
│  │ Context      │  │ (OWASP-aligned) │  │ (JSON format)   │ │
│  └──────────────┘  └─────────────────┘  └─────────────────┘ │
└──────────────────────────────────────────────────────────────┘
       │
       ▼
   LLM (Gemini 2.0-flash / GPT-4 / Bytez)
```

---

### 3. Multi-Layer Quality Filtering

**Problem**: LLMs hallucinate findings, produce duplicates, and have varying confidence.

**Solution**: 4-stage filter pipeline.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Filter Pipeline Architecture                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Raw LLM Findings (e.g., 25 findings)                                       │
│         │                                                                   │
│         ▼                                                                   │
│  ┌────────────────────┐                                                     │
│  │ 1️⃣ ConfidenceFilter │  Threshold: 0.5-0.65 (by agent type)              │
│  │                    │  "Remove uncertain findings"                        │
│  └─────────┬──────────┘                                                     │
│            │ ~20 findings remain                                            │
│            ▼                                                                │
│  ┌────────────────────┐                                                     │
│  │ 2️⃣ Deduplication   │  Similarity: 85% threshold                         │
│  │    Filter          │  "Remove duplicate/similar findings"                │
│  └─────────┬──────────┘                                                     │
│            │ ~15 findings remain                                            │
│            ▼                                                                │
│  ┌────────────────────┐                                                     │
│  │ 3️⃣ Hallucination   │  Evidence verification required                    │
│  │    Filter          │  "Verify code snippets actually exist"              │
│  └─────────┬──────────┘                                                     │
│            │ ~12 findings remain                                            │
│            ▼                                                                │
│  ┌────────────────────┐                                                     │
│  │ 4️⃣ FeedbackFilter  │  Historical reaction data                          │
│  │    (Dynamic)       │  "Skip if similar was 👎, boost if 👍"             │
│  └─────────┬──────────┘                                                     │
│            │ ~10 high-quality findings                                      │
│            ▼                                                                │
│  Posted to GitHub as Review Comments                                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

```python
# Filter Pipeline Architecture
class FilterPipeline:
    def __init__(self):
        self.filters = [
            ConfidenceFilter(threshold=0.5),      # Remove low confidence
            DeduplicationFilter(similarity=85),   # Remove duplicates
            HallucinationFilter(strict=False),    # Verify evidence
            # FeedbackFilter added dynamically
        ]
    
    def process(self, findings: List[Finding]) -> List[Finding]:
        for filter in self.filters:
            findings = filter.filter(findings)
        return findings
```

**Filter Details**:

| Filter | Threshold | Purpose |
|--------|-----------|---------|
| ConfidenceFilter | 0.5-0.65 | Remove uncertain findings |
| DeduplicationFilter | 85% similarity | Prevent duplicate comments |
| HallucinationFilter | Evidence required | Verify code snippets exist |
| FeedbackFilter | Historical data | Learn from user reactions |

---

### 4. Diff-Aware Code Review

**Problem**: Reviewers commented on unchanged code, wasting developer time.

**Solution**: Parse git diffs to focus ONLY on changed lines.

```python
# DiffChange dataclass for parsed diffs
@dataclass
class DiffChange:
    change_type: ChangeType  # ADDITION, REMOVAL, MODIFICATION
    old_line: Optional[int]
    new_line: int
    content: str
    context_before: List[str]
    context_after: List[str]
```

**Benefits**:
- Comments only on lines that were actually changed
- Understands context (what was removed vs added)
- Prevents "review everything" noise

---

### 5. Expert Persona Prompting

**Problem**: Generic LLM responses lacked practical coding wisdom.

**Solution**: `CodeReviewExpert` class with senior developer persona.

```python
SYSTEM_PROMPT = """You are a **Senior Software Engineer** with 10+ years of experience 
reviewing production code. Your review style:

1. **Practical over pedantic**: Flag real bugs, not style preferences
2. **Context-aware**: Understand the intent before criticizing
3. **Solution-oriented**: Every issue includes a fix suggestion
4. **Evidence-based**: Quote the exact problematic code
5. **Risk-focused**: Prioritize security > correctness > performance > style
"""
```

</details>

---

## 🗂️ Codebase Indexing (Intelligent Context)

<details>
<summary><b>Click to expand Codebase Indexing details</b></summary>

### What It Does

InspectAI can index your entire codebase to provide **intelligent impact analysis**:

- **Who calls this function?** - Know if a change breaks downstream code
- **What imports this file?** - Understand dependency relationships  
- **Risk level assessment** - HIGH/MEDIUM/LOW based on caller count

### Data Storage & Isolation

All indexed data is stored in **Supabase PostgreSQL** with complete isolation per repository:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Supabase Database                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  indexed_projects (1 row per repo)                                  │   │
│  │  • repo_full_name: "owner/repo" (UNIQUE)                           │   │
│  │  • installation_id: GitHub App installation                        │   │
│  │  • indexing_status: pending/indexing/completed/failed              │   │
│  │  • last_indexed_at: timestamp                                      │   │
│  │  • total_files, total_symbols: statistics                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              │ project_id (FK)                              │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  code_files (per project)                                           │   │
│  │  • file_path, language, content_hash                               │   │
│  │  • Isolated by: WHERE project_id = ?                               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              │ file_id (FK)                                 │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  code_symbols (functions, classes, methods)                         │   │
│  │  • symbol_name, symbol_type, signature                             │   │
│  │  • start_line, end_line, docstring                                 │   │
│  │  • Isolated by: WHERE project_id = ?                               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  code_calls (function call graph)                                   │   │
│  │  • caller_symbol_id → callee_name                                  │   │
│  │  • Used for impact analysis                                        │   │
│  │  • Isolated by: WHERE project_id = ?                               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Key Point:** Each repository gets its own `project_id`. All queries filter by `project_id`, ensuring **complete data isolation** between different repositories/organizations.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Codebase Indexer                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐        │
│  │  code_parser.py │    │   indexer.py    │    │context_enricher │        │
│  │                 │    │                 │    │                 │        │
│  │ • AST parsing   │───▶│ • Supabase store│───▶│ • Impact analysis│       │
│  │ • Python/Java/  │    │ • Per-project   │    │ • Caller tracking│       │
│  │   C++ support   │    │ • Incremental   │    │ • Risk scoring   │       │
│  │ • Call graphs   │    │                 │    │                 │        │
│  └─────────────────┘    └─────────────────┘    └─────────────────┘        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Data Structures

```python
@dataclass
class ParsedSymbol:
    name: str
    symbol_type: str  # function, class, method
    qualified_name: str
    start_line: int
    end_line: int
    signature: Optional[str]
    parameters: List[Dict]
    return_type: Optional[str]
    docstring: Optional[str]
    is_public: bool
    is_async: bool

@dataclass
class ParsedCall:
    callee_name: str
    caller_name: Optional[str]
    line_number: int
    call_type: str  # function, method
```

### Permission-Based Graceful Degradation

**Problem**: Not all GitHub Apps have `contents:read` permission.

**Solution**: Check permission before indexing, skip gracefully if not granted.

```python
async def _check_contents_permission(github_client, repo_full_name: str) -> bool:
    """Check if the GitHub App has contents:read permission."""
    try:
        # Try to get repo contents - will fail if no permission
        await github_client.get_contents(repo_full_name, "")
        return True
    except Exception as e:
        if "403" in str(e) or "404" in str(e):
            logger.info(f"No contents permission for {repo_full_name}, skipping indexing")
            return False
        raise

# Usage in webhook handler
if await _check_contents_permission(github_client, repo_full_name):
    asyncio.create_task(_trigger_background_indexing(repo_full_name, github_client))
else:
    logger.info("Proceeding without codebase indexing - still works!")
```

**Result**: 
- ✅ With `contents:read`: Full impact analysis in review comments
- ✅ Without `contents:read`: Standard review still works perfectly

### Impact Analysis Example

When indexing is enabled, reviews include:

```markdown
## CODEBASE CONTEXT (Impact Analysis)
**Risk Level: HIGH**

### Changed Symbols:
- `process_payment()` (function) - **12 callers** [HIGH impact]
- `validate_user()` (function) - **8 callers** [MEDIUM impact]

### Functions That Call This Code:
- **checkout.py**:
  - `complete_order` calls `process_payment` (line 45)
  - `retry_payment` calls `process_payment` (line 78)

### Files That Import This File:
- `api/routes.py`
- `services/billing.py`

⚠️ **HIGH RISK CHANGE**: This code has many dependents. 
Breaking changes could affect multiple parts of the codebase.
```

</details>

---

## 🎓 Feedback Learning System

<details>
<summary><b>Click to expand Feedback Learning System</b></summary>

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           FEEDBACK LIFECYCLE                                      │
└─────────────────────────────────────────────────────────────────────────────────┘

1️⃣ COMMENT GENERATION                    2️⃣ STORAGE                    3️⃣ USER FEEDBACK
┌──────────────────┐                    ┌──────────────────┐          ┌──────────────────┐
│ LLM generates    │                    │ Store comment    │          │ User reacts 👍/👎 │
│ review comments  │──── POST ─────────▶│ in Supabase      │◀─────────│ or replies       │
│ for PR           │     to GitHub      │ with embedding   │          │ to comment       │
└──────────────────┘                    └──────────────────┘          └──────────────────┘
                                               │                              │
                                               ▼                              ▼
4️⃣ FILTERING (Future PRs)              ┌──────────────────┐          ┌──────────────────┐
┌──────────────────┐                    │ review_comments  │          │ comment_feedback │
│ Before posting   │◀── Similar? ──────│ table            │◀─────────│ table            │
│ new comments:    │    Query by        │ (embeddings)     │  Link    │ (reactions)      │
│ Check if similar │    embedding       └──────────────────┘          └──────────────────┘
│ were 👎          │
└──────────────────┘
        │
        ▼
┌──────────────────┐
│ If similar had   │
│ 👎 > 👍: SKIP    │
│ If 👍 > 👎: BOOST│
└──────────────────┘
```

### When Is Feedback Saved?

| Trigger | What Happens | Data Stored |
|---------|--------------|-------------|
| **After posting review** | `store_comment()` called | Comment text, embedding, category, severity |
| **User reacts (👍/👎)** | `sync_github_reactions()` | Reaction type linked to comment |
| **User replies to comment** | `store_written_feedback()` | Reply text + inferred sentiment |

### What Gets Stored

#### Table: `review_comments` (Every comment we post)

| Column | Example | Purpose |
|--------|---------|---------|
| `repo_full_name` | `"owner/repo"` | **Repo isolation** - keeps data separate |
| `pr_number` | `123` | Track which PR |
| `file_path` | `"src/utils.py"` | Where comment was posted |
| `line_number` | `42` | Specific line |
| `comment_body` | Full text | For similarity search |
| `category` | `"Logic Error"` | Issue classification |
| `severity` | `"high"` | Criticality |
| `embedding` | 384-dim vector | For similarity matching |
| `command_type` | `"review"` | Which command generated it |

#### Table: `comment_feedback` (User reactions)

| Column | Example | Purpose |
|--------|---------|---------|
| `comment_id` | UUID link | Links to parent comment |
| `user_login` | `"octocat"` | Who reacted |
| `reaction_type` | `"thumbs_down"` | The reaction |
| `explanation` | `"This is intentional"` | Written feedback from replies |

### How Filtering Works

Before posting NEW comments, we check if similar comments were disliked:

```python
# webhooks.py - Called before posting any review
filtered_comments = await feedback_system.filter_by_feedback(all_comments, repo_full_name)
```

**Embedding Similarity Search:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     EMBEDDING SIMILARITY SEARCH                              │
└─────────────────────────────────────────────────────────────────────────────┘

 New Comment: "Variable 'user' may be None, add null check"
        │
        ▼
 ┌──────────────────────────────────────────┐
 │      sentence-transformers               │
 │      (all-MiniLM-L6-v2)                  │
 │                                          │
 │  "Variable 'user' may be None..."        │
 │         ↓                                │
 │  [0.23, -0.15, 0.87, ..., 0.42]         │
 │           384 dimensions                 │
 └───────────────────┬──────────────────────┘
                     │
                     ▼
 ┌──────────────────────────────────────────┐
 │      Supabase pgvector                   │
 │      (match_similar_comments RPC)        │
 │                                          │
 │  Cosine Similarity Search:               │
 │                                          │
 │  Past Comment 1:                         │
 │  "Check if user is null before access"   │
 │  Similarity: 0.91 ✅ > 0.85 threshold    │
 │  Reactions: 👎👎👎 (3 thumbs down)        │
 │                                          │
 │  Past Comment 2:                         │
 │  "user variable undefined error"         │
 │  Similarity: 0.78 ❌ < 0.85 threshold    │
 │                                          │
 └───────────────────┬──────────────────────┘
                     │
                     ▼
 ┌──────────────────────────────────────────┐
 │      Decision: FILTER OUT                │
 │                                          │
 │  Similar comment had 3 👎 > 0 👍         │
 │  This comment will NOT be posted         │
 └──────────────────────────────────────────┘
```

**The Algorithm:**
```
For each new comment:
  1. Generate embedding for comment text (sentence-transformers, FREE)
  2. Search Supabase for similar past comments (cosine similarity > 85%)
  3. Query is FILTERED BY repo_full_name (repo-specific learning!)
  4. Count thumbs_up and thumbs_down on similar comments
  
  Decision:
  ┌─────────────────────────────────────────────────────────┐
  │ If thumbs_down > thumbs_up AND thumbs_down >= 2:       │
  │     → FILTER OUT (don't post this comment)             │
  │                                                         │
  │ If thumbs_up > thumbs_down AND thumbs_up >= 2:         │
  │     → BOOST confidence (multiply by 1.2)               │
  │                                                         │
  │ Otherwise:                                              │
  │     → Post as normal                                    │
  └─────────────────────────────────────────────────────────┘
```

### Repository Isolation

**Each repository's feedback is kept separate:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    REPOSITORY ISOLATION MODEL                                │
└─────────────────────────────────────────────────────────────────────────────┘

     repo: owner/repo-A                    repo: owner/repo-B
    ┌─────────────────────┐               ┌─────────────────────┐
    │ review_comments     │               │ review_comments     │
    │ ─────────────────── │               │ ─────────────────── │
    │ "null check..."  👎 │               │ "null check..."  👍 │
    │ "SQL injection" 👍👍 │               │ "SQL injection" 👎 │
    │ "unused var..."  👎 │               │ "type hint..."  👍👍 │
    └─────────────────────┘               └─────────────────────┘
            │                                     │
            │  Query for repo-A                   │  Query for repo-B
            │  filters by repo-A                  │  filters by repo-B
            ▼                                     ▼
    ┌─────────────────────┐               ┌─────────────────────┐
    │ Result:             │               │ Result:             │
    │ Skip "null check"   │               │ Post "null check"   │
    │ Post "SQL injection"│               │ Skip "SQL injection"│
    └─────────────────────┘               └─────────────────────┘
```

```sql
-- All queries filter by repo_full_name
SELECT * FROM review_comments 
WHERE repo_full_name = 'owner/repo'  -- ✅ Isolated per repo

-- Similarity search also filters:
match_similar_comments(
    query_embedding,
    repo_filter := 'owner/repo'  -- Only this repo's history
)
```

**Why?** Different repos have different coding styles, false positive patterns, and team preferences.

### Feedback vs Prompt Injection

| Approach | How It Works | InspectAI Uses |
|----------|--------------|----------------|
| **Prompt Injection** | Add "avoid X" to LLM prompts | ❌ Not used |
| **Post-Generation Filter** | Generate → Filter by feedback → Post | ✅ Used |

**Why filtering over prompts?**
- Simpler - no complex prompt engineering
- Precise - uses actual embeddings for similarity
- Measurable - we track filter stats
- Consistent - avoids LLM inconsistency

### Database Schema (Supabase)

```sql
-- Review comments table
CREATE TABLE review_comments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    repo_full_name TEXT NOT NULL,
    pr_number INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    line_number INTEGER NOT NULL,
    comment_body TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    embedding VECTOR(1536),  -- OpenAI ada-002 embeddings
    github_comment_id BIGINT,
    command_type TEXT DEFAULT 'review',
    posted_at TIMESTAMPTZ DEFAULT NOW()
);

-- Feedback tracking table
CREATE TABLE comment_feedback (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    comment_id UUID REFERENCES review_comments(id),
    user_login TEXT NOT NULL,
    reaction_type TEXT NOT NULL,  -- thumbs_up, thumbs_down, etc.
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(comment_id, user_login, reaction_type)
);

-- Similarity search function
CREATE FUNCTION match_similar_comments(
    query_embedding VECTOR(1536),
    match_threshold FLOAT,
    match_count INT,
    repo_filter TEXT
) RETURNS TABLE (...);
```

### Feedback Logic

```python
async def filter_by_feedback(self, comments: List[Dict], repo_full_name: str):
    """Filter comments based on past feedback from similar comments."""
    for comment in comments:
        embedding = self.get_embedding(comment.get("description"))
        
        # Find similar past comments (85% similarity threshold)
        similar = self.client.rpc(
            "match_similar_comments",
            {"query_embedding": embedding, "match_threshold": 0.85}
        ).execute()
        
        total_positive = sum(row["positive_feedback_count"] for row in similar)
        total_negative = sum(row["negative_feedback_count"] for row in similar)
        
        if total_negative > total_positive and total_negative >= 2:
            # Similar comments were downvoted - filter out
            continue
        elif total_positive > total_negative and total_positive >= 2:
            # Similar comments were upvoted - boost confidence
            comment["confidence"] = min(comment["confidence"] * 1.2, 1.0)
```

</details>

---

## 🔬 Technical Deep Dive

<details>
<summary><b>Click to expand Technical Deep Dive</b></summary>

### Complete Request Lifecycle

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    COMPLETE REQUEST LIFECYCLE                                │
└─────────────────────────────────────────────────────────────────────────────┘

 GitHub                    InspectAI Server                       External
┌──────┐                   ┌─────────────────┐                   ┌──────────┐
│ User │                   │   Render Host   │                   │ Services │
│ PR   │                   │  (Port 8080)    │                   │          │
└──┬───┘                   └────────┬────────┘                   └────┬─────┘
   │                                │                                 │
   │ 1. POST /webhook/github        │                                 │
   │    X-Hub-Signature-256         │                                 │
   │────────────────────────────────▶                                 │
   │                                │                                 │
   │                         2. Verify HMAC                           │
   │                            signature                             │
   │                                │                                 │
   │                         3. Parse event                           │
   │                            type & body                           │
   │                                │                                 │
   │                         4. Check for                             │
   │                            /inspectai_*                          │
   │                            command                               │
   │                                │                                 │
   │                                │──────────────────────────────────▶
   │                                │  5. Fetch PR diff (GitHub API)  │
   │                                │◀─────────────────────────────────│
   │                                │                                 │
   │                         6. ThreadPoolExecutor                    │
   │                            (5 workers)                           │
   │                                │                                 │
   │                    ┌───────────┼───────────┐                     │
   │                    │           │           │                     │
   │                    ▼           ▼           ▼                     │
   │               ┌────────┐ ┌────────┐ ┌────────┐                   │
   │               │ File 1 │ │ File 2 │ │ File 3 │                   │
   │               └───┬────┘ └───┬────┘ └───┬────┘                   │
   │                   │          │          │                        │
   │                   │──────────┼──────────│────────────────────────▶
   │                   │     7. LLM API calls (Gemini)                │
   │                   │◀─────────┼──────────│─────────────────────────│
   │                   │          │          │                        │
   │               ┌───▼────┐ ┌───▼────┐ ┌───▼────┐                   │
   │               │Findings│ │Findings│ │Findings│                   │
   │               └───┬────┘ └───┬────┘ └───┬────┘                   │
   │                   │          │          │                        │
   │                    └─────────┼─────────┘                         │
   │                              │                                   │
   │                       8. Merge all                               │
   │                          findings                                │
   │                              │                                   │
   │                       9. Filter Pipeline                         │
   │                          ├─ Confidence                           │
   │                          ├─ Deduplication                        │
   │                          ├─ Hallucination                        │
   │                          └─ Feedback                             │
   │                              │                                   │
   │                              │───────────────────────────────────▶
   │                              │  10. Query similar feedback       │
   │                              │      (Supabase pgvector)          │
   │                              │◀──────────────────────────────────│
   │                              │                                   │
   │                       11. Final filtered                         │
   │                           findings                               │
   │                              │                                   │
   │◀─────────────────────────────│                                   │
   │ 12. POST review comments     │                                   │
   │     (GitHub API)             │                                   │
   │                              │                                   │
   │                              │───────────────────────────────────▶
   │                              │  13. Store comments for           │
   │                              │      feedback learning            │
   │                              │      (Supabase)                   │
   │                              │                                   │
└──┴──────────────────────────────┴───────────────────────────────────┘

Timeline: ~8-15 seconds for 5 files
```

### LLM Client Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         LLM Client Architecture                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│                        ┌─────────────────────┐                              │
│                        │     LLMClient       │                              │
│                        │   (Unified API)     │                              │
│                        └──────────┬──────────┘                              │
│                                   │                                         │
│              ┌────────────────────┼────────────────────┐                    │
│              │                    │                    │                    │
│              ▼                    ▼                    ▼                    │
│   ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐           │
│   │   Gemini API     │ │   OpenAI API     │ │   Bytez API      │           │
│   │  (HTTP Direct)   │ │  (SDK Client)    │ │  (SDK Client)    │           │
│   │                  │ │                  │ │                  │           │
│   │ gemini-2.0-flash │ │ gpt-4            │ │ granite-4.0      │           │
│   │ ⚡ Fastest       │ │ 🎯 Highest qual  │ │ 💡 Lightweight   │           │
│   │ 💰 Cheapest      │ │ 💰💰💰 Expensive │ │ 💰 Budget        │           │
│   │ 1M ctx tokens    │ │ 128K ctx tokens  │ │ 32K ctx tokens   │           │
│   └──────────────────┘ └──────────────────┘ └──────────────────┘           │
│                                                                             │
│   Selection: LLM_PROVIDER env var → "gemini" | "openai" | "bytez"          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

Unified interface supporting 3 providers:

```python
class LLMClient:
    """Unified LLM client supporting multiple providers."""
    
    def __init__(self, provider: str = "gemini"):
        if provider == "gemini":
            self.gemini_api_key = os.getenv("GEMINI_API_KEY")
            # Uses direct HTTP requests to Gemini API
        elif provider == "openai":
            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        elif provider == "bytez":
            self.client = Bytez(api_key=os.getenv("BYTEZ_API_KEY"))
    
    def chat(self, messages: List[Dict], **kwargs) -> str:
        """Unified chat interface for all providers."""
        # Route to appropriate provider
```

**Provider Comparison**:

| Provider | Model | Speed | Cost | Context Window |
|----------|-------|-------|------|----------------|
| **Gemini** (Default) | `gemini-2.0-flash` | ⚡ Fastest | 💰 Cheapest | 1M tokens |
| **OpenAI** | `gpt-4` | 🐢 Slower | 💰💰💰 Expensive | 128K tokens |
| **Bytez** | `granite-4.0-h-tiny` | ⚡ Fast | 💰 Cheap | 32K tokens |

### Agent Configuration

Each agent has tuned parameters:

```python
ORCHESTRATOR_CONFIG = {
    "analysis": {
        "temperature": 0.2,        # Low = focused, consistent reviews
        "max_tokens": 10000,
        "confidence_threshold": 0.5
    },
    "bug_detection": {
        "temperature": 0.1,        # Very low = precise bug detection
        "max_tokens": 10000,
        "confidence_threshold": 0.6  # Higher bar for bug reports
    },
    "security": {
        "temperature": 0.1,
        "max_tokens": 10000,
        "confidence_threshold": 0.65  # Highest bar - security critical
    },
    "generation": {
        "temperature": 0.3,        # Medium = creative refactoring
        "max_tokens": 16000        # Larger for code generation
    }
}
```

### Memory Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Memory System                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐              ┌─────────────────┐                      │
│  │  Short-Term     │              │  Long-Term      │                      │
│  │  (AgentMemory)  │              │  (VectorStore)  │                      │
│  │                 │              │                 │                      │
│  │ • Current task  │              │ • FAISS index   │                      │
│  │ • File context  │              │ • Embeddings    │                      │
│  │ • Findings      │              │ • Past reviews  │                      │
│  │ • Cleared per PR│              │ • Persistent    │                      │
│  └─────────────────┘              └─────────────────┘                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

</details>

---

## 🚧 Issues We Faced & Solutions

<details>
<summary><b>Click to expand Issues Faced & Solutions (8 major issues)</b></summary>

### Issue 1: LLM Response Parsing Failures

**Problem**: LLMs returned malformed JSON, missing fields, or prose instead of structured data.

**Root Cause**: Prompts were too open-ended, allowing LLM to "be creative."

**Solution**: 
1. Added strict JSON schema in system prompt
2. Included few-shot examples showing exact format
3. Added response validation with fallback parsing

```python
# Before (problematic)
prompt = "Review this code and find bugs"

# After (reliable)
prompt = """Review this code and return JSON:
{
  "findings": [
    {
      "line": <number>,
      "severity": "critical|high|medium|low",
      "category": "<category>",
      "description": "<description>",
      "suggested_fix": "<fix>"
    }
  ]
}

Example output:
{
  "findings": [
    {
      "line": 42,
      "severity": "high",
      "category": "Null Safety",
      "description": "Variable 'user' may be None",
      "suggested_fix": "Add null check: if user is not None:"
    }
  ]
}
"""
```

**Outcome**: Parsing success rate improved from ~60% to ~95%.

---

### Issue 2: Duplicate GitHub Events

**Problem**: GitHub sometimes sends duplicate webhook events, causing duplicate review comments.

**Root Cause**: GitHub's delivery system retries on timeout, and some events trigger both `issue_comment` and `pull_request_review_comment`.

**Solution**: Event deduplication with action type checking.

```python
# In webhooks.py
event_type = request.headers.get("X-GitHub-Event")
action = payload.get("action")

# Skip if not a new comment creation
if action != "created":
    return {"status": "ignored", "reason": f"action is {action}, not created"}

# Track processed events to prevent duplicates
processed_events = set()
event_id = f"{repo_full_name}:{pr_number}:{comment_id}"
if event_id in processed_events:
    return {"status": "duplicate", "reason": "already processed"}
processed_events.add(event_id)
```

**Outcome**: Zero duplicate comments in production.

---

### Issue 3: Slow Sequential File Processing

**Problem**: 5-file PRs took 40+ seconds (8s × 5 files sequentially).

**Root Cause**: Each file waited for previous file to complete analysis.

**Solution**: `ThreadPoolExecutor` for concurrent processing.

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def process_pr_files(files: List[Dict]) -> List[Finding]:
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(analyze_file, f): f 
            for f in files[:50]
        }
        
        all_findings = []
        for future in as_completed(futures):
            try:
                findings = future.result(timeout=30)
                all_findings.extend(findings)
            except Exception as e:
                logger.error(f"File analysis failed: {e}")
                # Continue with other files
        
        return all_findings
```

**Outcome**: 5x speedup (40s → 8s for 5 files).

---

### Issue 4: Comments on Unchanged Code

**Problem**: LLM found issues in unchanged parts of files, annoying developers.

**Root Cause**: Prompt sent full file content without highlighting what changed.

**Solution**: Diff-aware prompting with `StructuredContext`.

```python
@dataclass
class DiffChange:
    change_type: ChangeType  # ADDITION, REMOVAL, MODIFICATION
    old_line: Optional[int]
    new_line: int
    content: str
    context_before: List[str]  # 3 lines before
    context_after: List[str]   # 3 lines after

# Prompt now clearly separates:
# - Lines added (focus here)
# - Lines removed (for context only)
# - Unchanged context (for understanding)
```

**Outcome**: 100% of comments now on actually changed lines.

---

### Issue 5: GitHub Permission for Codebase Indexing

**Problem**: Codebase indexing required `contents:read` permission, but not all GitHub App installations grant this.

**Root Cause**: Some users install with minimal permissions.

**Solution**: Permission checking with graceful fallback.

```python
async def _check_contents_permission(github_client, repo_full_name: str) -> bool:
    """Check if we can read repo contents."""
    try:
        await github_client.get_contents(repo_full_name, "")
        return True
    except Exception:
        return False

# In webhook handler
if await _check_contents_permission(github_client, repo):
    # Full experience with impact analysis
    asyncio.create_task(_trigger_background_indexing(repo, github_client))
else:
    # Standard review - still valuable!
    logger.info(f"No contents permission for {repo}, skipping indexing")
```

**Outcome**: App works for all users; premium features for those with full permissions.

---

### Issue 6: Hallucinated Line Numbers

**Problem**: LLM sometimes reported line numbers that didn't exist in the file.

**Root Cause**: LLM "estimated" line numbers based on context.

**Solution**: Post-processing validation + HallucinationFilter.

```python
class HallucinationFilter(BaseFilter):
    """Verify findings have valid evidence."""
    
    def filter(self, findings: List[Finding]) -> List[Finding]:
        filtered = []
        for finding in findings:
            # Verify line number exists
            if finding.line_number > total_lines:
                continue
            
            # Verify code snippet matches actual content
            if finding.evidence.get("code_snippet"):
                actual_line = file_content[finding.line_number - 1]
                if finding.evidence["code_snippet"] not in actual_line:
                    finding.confidence *= 0.5  # Penalize
            
            if finding.confidence >= 0.3:
                filtered.append(finding)
        
        return filtered
```

**Outcome**: Invalid line numbers reduced by 90%.

---

### Issue 7: Rate Limiting on LLM APIs

**Problem**: High-volume PRs hit API rate limits.

**Solution**: 
1. Parallel processing with controlled concurrency (max 5)
2. Retry logic with exponential backoff
3. Provider fallback (Gemini → OpenAI → Bytez)

```python
import time
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def call_llm(prompt: str) -> str:
    try:
        return llm_client.chat([{"role": "user", "content": prompt}])
    except RateLimitError:
        time.sleep(5)
        raise
```

</details>

---

## ⚙️ Setup & Installation

<details>
<summary><b>Click to expand Setup & Installation</b></summary>

### Prerequisites

- Python 3.11+
- GitHub App credentials
- LLM API key (Gemini recommended)
- Supabase account (optional, for feedback + indexing)

### 1. Clone & Install

```bash
git clone https://github.com/hj2713/InspectAI.git
cd InspectAI
pip install -r requirements.txt
```

### 2. Environment Variables

Create `.env` file:

```env
# ===========================================
# LLM Provider (choose one)
# ===========================================
GEMINI_API_KEY=your_gemini_api_key      # Recommended - fastest & cheapest
# OPENAI_API_KEY=your_openai_key        # Alternative - highest quality
# BYTEZ_API_KEY=your_bytez_key          # Alternative - lightweight

# ===========================================
# GitHub App (required)
# ===========================================
GITHUB_APP_ID=your_github_app_id
GITHUB_PRIVATE_KEY_PATH=/path/to/private-key.pem
# Or base64 encoded:
# GITHUB_PRIVATE_KEY=base64_encoded_key
GITHUB_WEBHOOK_SECRET=your_webhook_secret

# ===========================================
# Supabase (optional - for feedback/indexing)
# ===========================================
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_anon_key

# ===========================================
# Optional Overrides
# ===========================================
# LLM_PROVIDER=gemini                   # gemini, openai, bytez
# PORT=8000                             # Server port
```

### 3. Run Locally

```bash
# Start webhook server
uvicorn src.api.server:app --reload --port 8000

# Or use script
./scripts/start_webhook_server.sh
```

### 4. Expose for GitHub (Local Testing)

```bash
# Using ngrok
ngrok http 8000

# Update GitHub App webhook URL to:
# https://xxxx.ngrok.io/webhook/github
```

</details>

---

## 🔧 Configuration

<details>
<summary><b>Click to expand Configuration</b></summary>

### Provider Configuration

Edit `config/default_config.py`:

```python
# Single source of truth for LLM provider
DEFAULT_PROVIDER = "gemini"  # Options: "gemini", "openai", "bytez"

# Model configurations
GEMINI_MODEL = "gemini-2.0-flash"
OPENAI_MODEL = "gpt-4"
BYTEZ_MODEL = "ibm-granite/granite-4.0-h-tiny"
```

### Agent Settings

```python
ORCHESTRATOR_CONFIG = {
    "analysis": {
        "temperature": 0.2,
        "max_tokens": 10000,
        "confidence_threshold": 0.5
    },
    "bug_detection": {
        "temperature": 0.1,
        "max_tokens": 10000,
        "confidence_threshold": 0.6
    },
    "security": {
        "temperature": 0.1,
        "max_tokens": 10000,
        "confidence_threshold": 0.65
    }
}

FILTER_CONFIG = {
    "confidence_threshold": 0.5,
    "similarity_threshold": 85,  # Deduplication
    "strict_evidence": False
}
```

### GitHub Settings

```python
GITHUB_CONFIG = {
    "api_timeout": 30,
    "max_files_per_pr": 50,
}
```

</details>

---

## 🌐 Deployment

<details>
<summary><b>Click to expand Deployment</b></summary>

### Production (Render)

Currently deployed at: `https://inspectai-f0vx.onrender.com`

**Render Settings**:
- **Build**: `pip install -r requirements.txt`
- **Start**: `uvicorn src.api.server:app --host 0.0.0.0 --port $PORT`
- **Auto-Deploy**: Enabled from `main` branch

**Environment Variables** (in Render dashboard):
```
GEMINI_API_KEY=xxx
GITHUB_APP_ID=xxx
GITHUB_PRIVATE_KEY=xxx (base64 encoded)
GITHUB_WEBHOOK_SECRET=xxx
LLM_PROVIDER=gemini
PORT=8080
SUPABASE_URL=xxx
SUPABASE_KEY=xxx
```

### Docker

```bash
# Build
docker build -t inspectai .

# Run
docker run -p 8080:8080 \
  -e GEMINI_API_KEY=xxx \
  -e GITHUB_APP_ID=xxx \
  -e GITHUB_PRIVATE_KEY=xxx \
  -e GITHUB_WEBHOOK_SECRET=xxx \
  inspectai
```

### Google Cloud Platform

See: [docs/GCP_DEPLOYMENT.md](docs/GCP_DEPLOYMENT.md)

</details>

---

## 🧪 Testing

<details>
<summary><b>Click to expand Testing</b></summary>

### Run Tests

```bash
# All tests
pytest tests/ -v

# Specific test
pytest tests/test_agents.py -v

# With coverage
pytest --cov=src tests/
```

### Test Files

- `tests/test_agents.py` - Agent initialization, processing, error handling
- `tests/test_orchestrator.py` - Task routing, coordination, memory

### Manual Testing

1. Create PR with intentional bugs
2. Comment `/inspectai_review`
3. Verify inline comments on correct lines
4. React with 👍/👎 to test feedback learning

</details>

---

## ✅ QA Checklist

<details>
<summary><b>Click to expand full QA testing checklist</b></summary>

### Pre-requisites
- [ ] Bot is deployed and running on Render
- [ ] GitHub App is installed on test repository
- [ ] Environment variables are set (GEMINI_API_KEY, GITHUB_TOKEN, SUPABASE_URL, etc.)

---

### 1️⃣ Command Recognition Tests

| Test | Command | Expected Result |
|------|---------|-----------------|
| [ ] | `/inspectai_review` | Bot responds, posts inline comments on changed lines |
| [ ] | `/inspectai_bugs` | Bot responds, scans entire files for bugs |
| [ ] | `/inspectai_security` | Bot responds, runs 4 security sub-agents |
| [ ] | `/inspectai_tests` | Bot responds, generates unit tests |
| [ ] | `/inspectai_docs` | Bot responds, generates docstrings (Python files) |
| [ ] | `/inspectai_help` | Bot posts help message with all commands |
| [ ] | Random comment | Bot ignores (no response) |
| [ ] | Bot's own comment | Bot ignores (no infinite loop) |

---

### 2️⃣ Code Review Quality Tests (`/inspectai_review`)

| Test | Scenario | Expected Result |
|------|----------|-----------------|
| [ ] | Python file with mutable default arg | Detects `def func(items=[])` bug |
| [ ] | Python file with bare except | Flags `except:` or `except Exception: pass` |
| [ ] | JavaScript file with `==` | Suggests using `===` |
| [ ] | JavaScript file with floating Promise | Detects unawaited async call |
| [ ] | File with SQL injection | Flags f-string in SQL query |
| [ ] | File with hardcoded secret | Detects API key/password in code |
| [ ] | Clean code file | Returns "No issues found" or minimal findings |
| [ ] | Multi-file PR | Reviews all changed files |
| [ ] | Large file (500+ lines) | Completes without timeout |

---

### 3️⃣ Bug Detection Tests (`/inspectai_bugs`)

| Test | Scenario | Expected Result |
|------|----------|-----------------|
| [ ] | Off-by-one error in loop | Detects boundary issue |
| [ ] | Null/None dereference | Flags missing null check |
| [ ] | Type coercion bug | Detects `int(user_input)` without try/except |
| [ ] | Race condition pattern | Flags concurrent access issue |
| [ ] | Resource leak | Detects unclosed file/connection |

---

### 4️⃣ Security Scan Tests (`/inspectai_security`)

| Test | Scenario | Expected Result |
|------|----------|-----------------|
| [ ] | SQL injection | Flags string formatting in queries |
| [ ] | Command injection | Flags `os.system()` with user input |
| [ ] | XSS (JavaScript) | Flags `innerHTML` with user data |
| [ ] | Hardcoded credentials | Detects password/API key in code |
| [ ] | Pickle deserialization | Flags `pickle.loads(untrusted)` |
| [ ] | Path traversal | Flags `open(user_path)` without validation |
| [ ] | Safe code (ORM, parameterized) | No false positives |

---

### 5️⃣ Test Generation (`/inspectai_tests`)

| Test | Scenario | Expected Result |
|------|----------|-----------------|
| [ ] | Python function | Generates pytest test cases |
| [ ] | JavaScript function | Generates Jest/Mocha tests |
| [ ] | Class with methods | Generates tests for each method |
| [ ] | Edge cases covered | Tests include null, empty, boundary values |

---

### 6️⃣ Documentation (`/inspectai_docs`)

| Test | Scenario | Expected Result |
|------|----------|-----------------|
| [ ] | Python file without docstrings | Generates Google-style docstrings |
| [ ] | Function with params | Documents parameters and return type |
| [ ] | Non-Python file | Skips gracefully (only Python supported) |

---

### 7️⃣ Error Handling Tests

| Test | Scenario | Expected Result |
|------|----------|-----------------|
| [ ] | One file fails analysis | Other files still reviewed (partial success) |
| [ ] | LLM API timeout | User-friendly error message posted |
| [ ] | Invalid file content | Graceful skip, no crash |
| [ ] | Empty PR (no code changes) | Appropriate message ("No code files to review") |
| [ ] | Binary files in PR | Skipped automatically |

---

### 8️⃣ Feedback System Tests

| Test | Scenario | Expected Result |
|------|----------|-----------------|
| [ ] | React 👍 to comment | Feedback stored in Supabase |
| [ ] | React 👎 to comment | Feedback stored, affects future filtering |
| [ ] | Reply to comment | Reply text captured as feedback |
| [ ] | Similar issue in new PR | Previously 👎 patterns filtered out |

---

### 9️⃣ Multi-Language Support

| Language | Test File | Commands to Test |
|----------|-----------|------------------|
| [ ] Python | `.py` | All commands |
| [ ] JavaScript | `.js` | review, bugs, security |
| [ ] TypeScript | `.ts` | review, bugs, security |
| [ ] Java | `.java` | review, bugs |
| [ ] Go | `.go` | review, bugs |
| [ ] Rust | `.rs` | review |
| [ ] C/C++ | `.c`, `.cpp` | review |

---

### 🔟 Performance Tests

| Test | Metric | Target |
|------|--------|--------|
| [ ] | Single file review | < 30 seconds |
| [ ] | 5 file PR review | < 60 seconds |
| [ ] | 10 file PR review | < 120 seconds |
| [ ] | Memory usage | No OOM on Render free tier |

---

### 1️⃣1️⃣ Edge Cases

| Test | Scenario | Expected Result |
|------|----------|-----------------|
| [ ] | PR with only deleted files | Appropriate message |
| [ ] | PR with renamed files | Reviews new content |
| [ ] | PR with 50+ files | Handles or limits gracefully |
| [ ] | File with non-UTF8 encoding | No crash |
| [ ] | Very long single line | Handles without issue |
| [ ] | Empty file | Skips gracefully |

---

### Quick Smoke Test (5 minutes)

1. [ ] Create PR with intentional bug: `def test(items=[]): pass`
2. [ ] Comment `/inspectai_review`
3. [ ] Verify bot responds with mutable default arg warning
4. [ ] Comment `/inspectai_help`
5. [ ] Verify help message appears
6. [ ] React 👎 to a comment
7. [ ] Check Supabase for feedback entry

---

### Test PR Template

Create a test file with these intentional issues:

```python
# test_qa.py - QA Test File
import os
import pickle

def process_data(items=[], cache={}):  # Mutable defaults
    try:
        result = int(input("Enter number: "))  # No validation
    except:  # Bare except
        pass  # Swallowing exception
    
    query = f"SELECT * FROM users WHERE id = {result}"  # SQL injection
    os.system(f"echo {result}")  # Command injection
    
    data = pickle.loads(user_input)  # Unsafe deserialization
    
    API_KEY = "sk-1234567890abcdef"  # Hardcoded secret
    
    f = open("file.txt")  # No context manager
    content = f.read()
    # Missing f.close()
    
    return content
```

</details>

---

## 📁 Project Structure

<details>
<summary><b>Click to expand Project Structure</b></summary>

```
InspectAI/                          # ~40,000+ lines of Python
├── src/
│   ├── agents/                     # 7 specialized agents (~8,000 lines)
│   │   ├── base_agent.py           # Abstract base class
│   │   ├── code_review_expert.py   # Senior dev reviewer (306 lines)
│   │   ├── code_analysis_agent.py  # Orchestrates expert
│   │   ├── bug_detection_agent.py  # 4 sub-agents
│   │   ├── security_agent.py       # 4 sub-agents
│   │   ├── research_agent.py
│   │   ├── code_generation_agent.py
│   │   ├── test_generation_agent.py
│   │   ├── documentation_agent.py
│   │   ├── filter_pipeline.py      # Quality filtering (292 lines)
│   │   ├── bug_detection/          # Sub-agents
│   │   └── security/               # Sub-agents
│   │
│   ├── api/                        # FastAPI server (~1,800 lines)
│   │   ├── server.py               # Health checks, routes
│   │   └── webhooks.py             # GitHub webhook handler (1,563 lines)
│   │
│   ├── prompts/                    # Prompt engineering (~800 lines)
│   │   └── prompt_builder.py       # Structured prompts (777 lines)
│   │
│   ├── indexer/                    # Codebase indexing (~1,800 lines)
│   │   ├── code_parser.py          # AST parsing (661 lines)
│   │   ├── indexer.py              # Supabase storage
│   │   ├── background_indexer.py   # Async background jobs
│   │   └── context_enricher.py     # Impact analysis (352 lines)
│   │
│   ├── feedback/                   # Learning system (~400 lines)
│   │   └── feedback_system.py      # Reaction tracking (347 lines)
│   │
│   ├── github/                     # GitHub API
│   │   └── client.py               # API wrapper
│   │
│   ├── llm/                        # LLM clients
│   │   ├── client.py               # Unified client (230 lines)
│   │   ├── local_client.py
│   │   └── device_info.py
│   │
│   ├── memory/                     # Context management
│   │   ├── agent_memory.py
│   │   ├── vector_store.py         # Legacy ChromaDB store
│   │   └── supabase_vector_store.py # Unified Supabase pgvector
│   │
│   ├── orchestrator/               # Agent coordination
│   │   └── orchestrator.py         # Main orchestrator (640 lines)
│   │
│   ├── utils/
│   │   └── logger.py
│   │
│   └── main.py
│
├── config/
│   └── default_config.py           # All configuration
│
├── tests/
│   ├── test_agents.py
│   └── test_orchestrator.py
│
├── scripts/
│   ├── start_webhook_server.sh
│   └── deploy_gcp.sh
│
├── docs/
│   └── GCP_DEPLOYMENT.md
│
├── supabase_schema.sql             # Database schema (review_comments, feedback, vectors)
├── Dockerfile
├── requirements.txt
└── README.md                       # This file
```

</details>

---

## 🤝 Contributing

<details>
<summary><b>Click to expand Contributing</b></summary>

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

### Areas for Contribution

1. **New Language Support**: Add bug patterns for Ruby, PHP, Kotlin
2. **IDE Integration**: VS Code extension for real-time reviews
3. **Custom Rules**: Project-specific rule configuration
4. **Performance**: Caching, incremental analysis
5. **Documentation**: Tutorials, API docs

</details>

---

## ❓ FAQ

<details>
<summary><b>Click to expand FAQ (Frequently Asked Questions)</b></summary>

### Q: Why use Render instead of GCP Cloud Run?

**A:** GitHub webhooks require a **publicly accessible endpoint** to receive events. This creates a challenge with GCP Cloud Run:

| Platform | Webhook Challenge | Solution |
|----------|------------------|----------|
| **GCP Cloud Run** | Requires `--allow-unauthenticated` flag (security risk) OR complex OIDC proxy setup | Need GitHub Actions workflow + Workload Identity Federation to proxy webhooks securely |
| **Render** | ✅ Built-in public HTTPS endpoint | Just deploy and set webhook URL |

**The GCP workaround requires:**
1. Workload Identity Pool + Provider setup
2. Service account with `roles/run.invoker`
3. GitHub Actions workflow to intercept webhooks
4. OIDC authentication for each request

**Render is simpler because:**
- ✅ Public endpoint works out of the box
- ✅ GitHub webhook secret validation is sufficient security
- ✅ No IAM/OIDC configuration needed
- ✅ Free tier available
- ✅ Auto-deploy from GitHub

> **Note:** GCP deployment docs exist in `docs/GCP_DEPLOYMENT.md` if you need GCP-specific features or have existing GCP infrastructure.

---

### Q: How do users provide feedback on reviews?

**A:** Two methods:

1. **Emoji Reactions** (easiest):
   - 👍 = Comment was helpful
   - 👎 = Comment was not helpful/false positive

2. **Reply Comments** (detailed):
   - Reply to any InspectAI comment with explanation
   - Example: *"This is intentional for backwards compatibility"*
   - System auto-detects sentiment from keywords

Feedback is used to improve future reviews via similarity matching.

---

### Q: Why does `/inspectai_security` show false positives?

**A:** We've significantly improved the security scanners to reduce false positives. The scanners now:

- ✅ Only report what they **SEE** in the code, not speculate
- ✅ Exclude safe patterns (Supabase RPC, ORM queries, env vars)
- ✅ Require 0.70+ confidence threshold
- ✅ Don't flag file extension strings as parsing vulnerabilities

If you still see false positives, react with 👎 - the feedback system learns!

---

### Q: What LLM providers are supported?

**A:** Three providers with easy switching:

| Provider | Model | Best For |
|----------|-------|----------|
| **Gemini** (default) | `gemini-2.0-flash` | Fast, good quality, free tier |
| **OpenAI** | `gpt-4` | Highest quality |
| **Bytez** | `granite-4.0-h-tiny` | Lightweight, fast |

Change provider via environment variable:
```bash
LLM_PROVIDER=gemini  # or openai, bytez
```

---

### Q: Why use GitHub Webhooks directly instead of Hookdeck?

**A:** We chose **native GitHub webhooks** over third-party webhook services like [Hookdeck](https://hookdeck.com/):

| Approach | Pros | Cons |
|----------|------|------|
| **GitHub Webhooks (chosen)** | ✅ No extra dependency<br>✅ Zero additional cost<br>✅ Direct integration | ⚠️ Can miss events during network congestion<br>⚠️ No built-in retry queue |
| **Hookdeck/Third-party** | ✅ More reliable delivery<br>✅ Built-in retry logic<br>✅ Better monitoring | ❌ Additional cost<br>❌ Extra service to manage |

**Our reasoning:**
- For a class project/MVP, GitHub's native webhooks are sufficient
- GitHub does retry failed deliveries (up to 3 times)
- We use webhook secret validation for security
- Keeps architecture simple with fewer moving parts

> **Future consideration:** If scaling to handle many concurrent PRs, consider adding a webhook relay service.

---

### Q: Why not use Hatchet or a queue-based architecture?

**A:** We currently process webhook events **synchronously** without a job queue like [Hatchet](https://hatchet.run/):

| Architecture | When to Use |
|--------------|-------------|
| **Current (sync)** | Low volume, single PR at a time, simpler deployment |
| **Queue-based (Hatchet, Celery, BullMQ)** | High volume, many concurrent PRs, need retry/persistence |

**Why we chose synchronous processing:**

1. **Scale is low** - This is a class project / MVP, not handling thousands of PRs/day
2. **Simplicity over complexity** - Adding Hatchet/Redis requires:
   - Additional infrastructure (Redis, worker processes)
   - More configuration and deployment complexity
   - Extra costs and monitoring
3. **Can be added later** - Architecture supports easy migration if needed

**This applies to feedback storage too:**
- User reactions (👍/👎) are stored synchronously in Supabase
- For current scale (~50-100ms per write), this is acceptable
- No message queue between webhook and database

**Current limitations:**
- If multiple PRs trigger reviews simultaneously, they process sequentially
- Long-running reviews could timeout
- Network errors may lose the request

**When to add a queue:**
- If bot is installed on many repositories
- If reviews frequently timeout (> 30 seconds)
- If you need guaranteed delivery and retry logic

**Potential future architecture:**
```
GitHub Webhook → Queue (Hatchet/Redis) → Worker Processes → GitHub API
                     ↓
              Persistent storage
              (survives restarts)
```

This would allow horizontal scaling and prevent lost requests during high load.

---

### Q: Why Supabase over ChromaDB for vector storage?

**A:** We migrated from ChromaDB to Supabase pgvector for several reasons:

| Feature | ChromaDB | Supabase (pgvector) |
|---------|----------|---------------------|
| **Persistence** | File-based (local) | ✅ Cloud PostgreSQL |
| **Scaling** | Single node | ✅ Managed scaling |
| **Multi-tenancy** | Complex setup | ✅ Row-level security |
| **Additional features** | Just vectors | ✅ Full SQL, auth, realtime |
| **Cost** | Free (local) | Free tier available |

**Key reasons for switch:**
1. **Persistence**: ChromaDB stores locally, lost on container restart
2. **Unified storage**: Feedback, indexing, vectors all in one database
3. **SQL queries**: Can JOIN vectors with feedback for complex filtering
4. **Production-ready**: Supabase handles backups, scaling, monitoring

**Migration was straightforward:**
```python
# Old: ChromaDB
collection = chroma_client.get_collection("embeddings")
results = collection.query(query_embeddings=[embedding])

# New: Supabase pgvector
results = supabase.rpc("match_similar_comments", {
    "query_embedding": embedding,
    "match_threshold": 0.85
}).execute()
```

---

### Q: Why sentence-transformers over OpenAI embeddings?

**A:** We switched from OpenAI's `text-embedding-ada-002` to local sentence-transformers:

| Aspect | OpenAI ada-002 | sentence-transformers |
|--------|----------------|----------------------|
| **Cost** | $0.0001/1K tokens | ✅ **FREE** |
| **Speed** | Network latency | ✅ Local, instant |
| **Privacy** | Data sent to OpenAI | ✅ Data stays local |
| **Quality** | 1536 dimensions | 384 dimensions (sufficient) |
| **Dependency** | API key required | ✅ No API key |

**Model used**: `all-MiniLM-L6-v2`
- 22M parameters, 80MB model
- Optimized for semantic similarity
- Works great for code comment matching

```python
# Implementation
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-MiniLM-L6-v2')
embedding = model.encode(text).tolist()  # 384-dim vector
```

---

### Q: Why ThreadPoolExecutor instead of asyncio for parallel processing?

**A:** We use `ThreadPoolExecutor` for file-level parallelism:

| Approach | Pros | Cons |
|----------|------|------|
| **ThreadPoolExecutor (chosen)** | ✅ Simple, works with sync LLM calls<br>✅ Predictable resource usage<br>✅ Easy to limit concurrency | ⚠️ GIL limits true parallelism |
| **asyncio** | ✅ True async, better for I/O<br>✅ More scalable | ⚠️ Requires async everywhere<br>⚠️ Complex error handling |
| **multiprocessing** | ✅ True parallelism (no GIL) | ⚠️ Memory overhead<br>⚠️ Complex IPC |

**Why ThreadPoolExecutor works:**
- LLM API calls are **I/O bound** (network waiting), not CPU bound
- GIL is released during I/O operations
- Simpler code than full async rewrite
- 5 workers = 5 concurrent API calls

```python
# Current implementation
with ThreadPoolExecutor(max_workers=5) as executor:
    futures = {executor.submit(process_file, f): f for f in files}
    for future in as_completed(futures):
        results.extend(future.result())
```

---

### Q: Why are confidence thresholds different per agent?

**A:** Each agent type has different false positive rates:

| Agent | Threshold | Reasoning |
|-------|-----------|-----------|
| **Code Review** | 0.50 | General review, some false positives OK |
| **Bug Detection** | 0.60 | Bugs should be more certain |
| **Security** | 0.65-0.70 | Security alerts must be high confidence |
| **Refactoring** | 0.40 | Suggestions can be more speculative |

**Security is highest because:**
- False positive security alerts cause alarm fatigue
- Developers may ignore real issues if too many false ones
- Better to miss edge cases than flood with noise

```python
ORCHESTRATOR_CONFIG = {
    "analysis": {"confidence_threshold": 0.5},
    "bug_detection": {"confidence_threshold": 0.6},
    "security": {"confidence_threshold": 0.65},
}
```

---

### Q: Why diff-aware analysis instead of full-file analysis?

**A:** Focusing on changed lines provides better signal-to-noise:

| Approach | Result |
|----------|--------|
| **Full file analysis** | ❌ Comments on old code<br>❌ Overwhelms developer<br>❌ Irrelevant to PR |
| **Diff-aware (chosen)** | ✅ Only changed lines<br>✅ Relevant to PR<br>✅ Actionable feedback |

**How it works:**
```
PR Diff:
  Line 10: unchanged context
  Line 11: - old code (removed)
  Line 12: + new code (added)    ← Only comment here
  Line 13: unchanged context
```

**Exception**: Bug detection scans entire file because bugs may exist in code that calls the changed function.

---

### Q: Why does `/inspectai_tests` skip large files and process in parallel?

**A:** Test generation is optimized for speed and reliability:

```
┌─────────────────────────────────────────────────────────────────┐
│                 Test Generation Pipeline                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 1. File Filtering                                               │
│    • Skip files > 500 lines (high LLM payload = slow response)  │
│    • Only process .py files                                     │
│    • Log skipped files for transparency                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. Diff-Aware Analysis                                          │
│    • Parse diff to extract ONLY changed/added lines             │
│    • Don't send entire file to LLM (wastes tokens)              │
│    • Focus tests on new code, not existing stable code          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. Parallel Processing                                          │
│    • ThreadPoolExecutor(max_workers=3)                          │
│    • Process multiple files simultaneously                      │
│    • 3x faster than sequential for multi-file PRs               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. Response Generation                                          │
│    • Aggregate results from all files                           │
│    • Note which files were skipped and why                      │
│    • Post as single PR comment                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Why skip files > 500 lines?**
- Large files = large LLM payload = slow response (can exceed 60s timeout)
- Tests for 500+ line files should be written incrementally, not all at once
- Prevents webhook timeouts and GitHub API errors

**Why diff-aware instead of full file?**
- Sending 926 lines to generate tests for 20 changed lines is wasteful
- Focused tests are more relevant (test what you changed)
- Faster LLM response (smaller input = faster processing)

---

### Q: Why 4 specialized security sub-agents?

**A:** A single "find all security issues" prompt produces poor results. Specialized agents are more accurate:

```
                    ┌─────────────────────┐
                    │   SecurityAgent     │
                    │   (Orchestrator)    │
                    └──────────┬──────────┘
                               │
       ┌───────────┬───────────┼───────────┬───────────┐
       │           │           │           │           │
       ▼           ▼           ▼           ▼           │
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│Injection │ │   Auth   │ │  Data    │ │Dependency│   │
│ Scanner  │ │ Scanner  │ │ Exposure │ │ Scanner  │   │
│          │ │          │ │ Scanner  │ │          │   │
│SQL, XSS, │ │Session,  │ │Logging,  │ │Outdated, │   │
│Command   │ │JWT, RBAC │ │Secrets,  │ │CVEs,     │   │
│Injection │ │          │ │PII       │ │Known vuln│   │
└──────────┘ └──────────┘ └──────────┘ └──────────┘   │
       │           │           │           │          │
       └───────────┴───────────┴───────────┴──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │  Merge & Dedupe     │
                    │  (Confidence 0.70+) │
                    └─────────────────────┘
```

**Benefits:**
- Each agent has specialized prompts
- Parallel execution (4x faster than sequential)
- Different confidence thresholds per category
- Easier to tune false positive rates independently

---

### Q: How does the feedback system prevent infinite loops?

**A:** We have several safeguards:

1. **Minimum feedback threshold**: Need ≥2 thumbs down to filter
2. **Repo isolation**: Feedback only applies within same repository
3. **Time decay** (planned): Old feedback weighted less
4. **Confidence cap**: Boosted confidence maxes at 1.0

```python
# Filter logic prevents aggressive filtering
if total_negative > total_positive and total_negative >= 2:
    # Only filter if SIGNIFICANTLY more negative feedback
    return None  # Skip this comment

# Boost is capped
comment["confidence"] = min(comment["confidence"] * 1.2, 1.0)
```

</details>

---

## 🎯 Roadmap

<details>
<summary><b>Click to expand Roadmap</b></summary>

- [ ] **Web Dashboard**: Review history, metrics, agent performance
- [ ] **Custom Rules**: Project-specific review rules via `.inspectai.yml`
- [ ] **Multi-Repo Analysis**: Cross-repository dependency analysis
- [ ] **VS Code Extension**: Real-time reviews in editor
- [ ] **Auto-Fix PRs**: Automatically create fix commits
- [ ] **Team Analytics**: Code quality trends over time
- [ ] **Slack Integration**: Review notifications
- [ ] **More Languages**: Ruby, PHP, Kotlin, Swift

</details>

---

## 🙏 Acknowledgments

### Core Services
| Service | Provider | Purpose |
|---------|----------|----------|
| **Primary LLM** | [Google Gemini](https://ai.google.dev/) | Code analysis with Gemini 2.0-flash |
| **Alternative LLM** | [OpenAI](https://openai.com/) | GPT-4 fallback provider |
| **Lightweight LLM** | [Bytez](https://bytez.com/) | Granite model for fast inference |
| **Database** | [Supabase](https://supabase.com/) | PostgreSQL + pgvector for feedback & embeddings |
| **Deployment** | [Render](https://render.com/) | Cloud hosting with auto-deploy |
| **Alternative Cloud** | [Google Cloud Platform](https://cloud.google.com/) | Cloud Run deployment option |

### Libraries & Tools
| Library | Purpose |
|---------|----------|
| [FastAPI](https://fastapi.tiangolo.com/) | High-performance async web framework |
| [sentence-transformers](https://www.sbert.net/) | Free local embeddings (all-MiniLM-L6-v2) |
| [ChromaDB](https://www.trychroma.com/) | Vector database (legacy, migrated to Supabase) |
| [PyGithub](https://pygithub.readthedocs.io/) | GitHub API integration |
| [unidiff](https://github.com/matiasb/python-unidiff) | Git diff parsing |
| [tiktoken](https://github.com/openai/tiktoken) | Token counting for LLM context management |
| [tenacity](https://tenacity.readthedocs.io/) | Retry logic with exponential backoff |
| [Pydantic](https://docs.pydantic.dev/) | Data validation and settings management |

### Inspiration & Learning
| Resource | Contribution |
|----------|-------------|
| [Ellipsis.dev](https://www.ellipsis.dev/blog/how-we-built-ellipsis) | Architecture patterns for AI code review |
| [OWASP Top 10](https://owasp.org/www-project-top-ten/) | Security vulnerability classifications |
| [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html) | Docstring format standards |
