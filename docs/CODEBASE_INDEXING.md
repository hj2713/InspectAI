# Codebase Indexing - Technical Documentation

## Overview

InspectAI now includes **AST-based codebase indexing** that enables the AI reviewer to understand the full context of your repository. When reviewing PRs, the AI knows:

- **Which functions call the code being changed** (callers)
- **What dependencies the changed code has** (imports, calls)
- **Impact score** - how many places might be affected by changes

This context helps catch issues like:
- Breaking changes that affect many callers
- Missing error handling in frequently-used functions
- Security vulnerabilities in high-impact code paths

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                     Codebase Indexing Flow                       │
└──────────────────────────────────────────────────────────────────┘

1. GitHub App Installation
   ┌─────────────┐       ┌──────────────────────┐
   │ GitHub      │──────►│ Installation Event   │
   │ App Install │       │ (created action)     │
   └─────────────┘       └──────────────────────┘
                                    │
                                    ▼
2. Background Indexing (Async, non-blocking)
   ┌──────────────────────┐       ┌──────────────────────┐
   │ BackgroundIndexer    │──────►│ Clone Repository     │
   │ (triggered by event) │       │ (temp directory)     │
   └──────────────────────┘       └──────────────────────┘
                                    │
                                    ▼
3. AST Parsing
   ┌──────────────────────┐       ┌──────────────────────┐
   │ CodeParser           │       │ Extract:             │
   │ - Python (ast)       │──────►│ - Functions/Classes  │
   │ - Java (tree-sitter) │       │ - Imports            │
   │ - C++ (tree-sitter)  │       │ - Function calls     │
   └──────────────────────┘       └──────────────────────┘
                                    │
                                    ▼
4. Supabase Storage
   ┌──────────────────────────────────────────────────────┐
   │ Tables:                                              │
   │ - indexed_projects  (project metadata)               │
   │ - code_symbols      (functions, classes, methods)    │
   │ - code_imports      (import statements)              │
   │ - code_calls        (function call relationships)    │
   │ - indexing_jobs     (job tracking)                   │
   └──────────────────────────────────────────────────────┘
                                    │
                                    ▼
5. PR Review Enrichment
   ┌──────────────────────┐       ┌──────────────────────┐
   │ ContextEnricher      │──────►│ Add to review prompt:│
   │ (queries Supabase)   │       │ "X is called by Y,Z" │
   │                      │       │ "Impact: 5 callers"  │
   └──────────────────────┘       └──────────────────────┘
```

---

## Supported Languages

| Language | Parser | Status |
|----------|--------|--------|
| Python   | Built-in `ast` module | ✅ Full support |
| Java     | tree-sitter-java | ✅ Full support |
| C++      | tree-sitter-cpp | ✅ Full support |

**Future expansion**: JavaScript, TypeScript, Go, Rust (use tree-sitter)

---

## Database Schema

### Tables

```sql
-- Project tracking
indexed_projects (
    id SERIAL PRIMARY KEY,
    repo_full_name TEXT UNIQUE,
    repo_id BIGINT,
    default_branch TEXT,
    languages JSONB,
    last_indexed_at TIMESTAMPTZ,
    total_files INTEGER,
    total_symbols INTEGER
)

-- Functions, classes, methods
code_symbols (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES indexed_projects(id),
    file_path TEXT,
    symbol_name TEXT,
    symbol_type TEXT,         -- 'function', 'class', 'method'
    line_start INTEGER,
    line_end INTEGER,
    signature TEXT,           -- Full signature
    docstring TEXT,
    is_exported BOOLEAN,
    metadata JSONB
)

-- Import statements
code_imports (
    id SERIAL PRIMARY KEY,
    project_id INTEGER,
    file_path TEXT,
    module_name TEXT,
    imported_names TEXT[],
    is_relative BOOLEAN
)

-- Function calls (caller → callee relationships)
code_calls (
    id SERIAL PRIMARY KEY,
    project_id INTEGER,
    caller_file TEXT,
    caller_function TEXT,
    callee_name TEXT,
    call_line INTEGER
)

-- Job tracking
indexing_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id INTEGER,
    repo_full_name TEXT,
    status TEXT,              -- 'pending', 'running', 'completed', 'failed'
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    files_processed INTEGER,
    symbols_extracted INTEGER,
    error_message TEXT
)
```

### Functions

```sql
-- Get all callers of a symbol
get_symbol_callers(p_project_id INT, p_symbol_name TEXT)

-- Get all dependencies of a symbol
get_symbol_dependencies(p_project_id INT, p_file_path TEXT)

-- Calculate impact score
get_impact_score(p_project_id INT, p_symbol_name TEXT)
```

---

## Setup Instructions

### 1. Run the SQL Schema

Execute the schema in your Supabase dashboard:

1. Go to Supabase Dashboard → SQL Editor
2. Copy contents of `supabase_codebase_schema.sql`
3. Execute

### 2. Environment Variables

Already configured (same as feedback system):
```env
SUPABASE_URL=https://qwwvadfeyhlzjzjpvnto.supabase.co
SUPABASE_KEY=your-key-here
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

New dependencies:
- `tree-sitter>=0.20.0`
- `tree-sitter-java>=0.20.0`
- `tree-sitter-cpp>=0.20.0`

---

## How It Works

### On App Installation

1. GitHub sends `installation.created` event
2. Webhook triggers `_trigger_background_indexing()`
3. BackgroundIndexer clones repo, parses all files
4. Symbols stored in Supabase with project_id isolation

### On PR Review

1. `/inspectai_review` command triggered
2. `ContextEnricher` queries Supabase for:
   - All callers of changed functions
   - Dependencies of changed code
   - Impact score calculation
3. Context added to LLM prompt:
   ```
   CODEBASE CONTEXT (from indexed repository):
   - `process_user()` is called by: handle_login, handle_signup, reset_password
   - `validate_email()` depends on: re.match, EmailValidator
   - ⚠️ HIGH IMPACT: Changes may affect 12 other places in codebase
   ```
4. AI reviewer uses this context for better reviews

### Incremental Updates

On each PR:
1. Detect changed files from diff
2. Re-parse only changed files
3. Update symbols/calls in Supabase
4. Delete old entries for changed files

---

## API Reference

### trigger_repo_indexing

```python
from src.indexer import trigger_repo_indexing

job_id = await trigger_repo_indexing(
    repo_full_name="owner/repo",
    github_client=client,
    installation_id=12345
)
```

### get_enriched_context

```python
from src.indexer import get_enriched_context

context = await get_enriched_context(
    repo_full_name="owner/repo",
    file_path="src/auth.py",
    diff_patch="..."
)

# Returns:
{
    "file_contexts": {
        "src/auth.py": {
            "callers": {"authenticate": ["login_view", "api_auth"]},
            "dependencies": {"authenticate": ["bcrypt.verify", "jwt.encode"]},
            "impact_score": 8
        }
    },
    "context_summary": [
        "`authenticate` is called by: login_view, api_auth",
        "⚠️ HIGH IMPACT: Changes may affect 8 other places"
    ]
}
```

---

## Performance Considerations

### Storage Estimates

For a typical 10,000 line repository:

| Table | Rows | Size |
|-------|------|------|
| code_symbols | ~500 | ~100KB |
| code_imports | ~200 | ~40KB |
| code_calls | ~1000 | ~200KB |
| indexed_projects | 1 | <1KB |

**Total per repo**: ~350KB

### Query Performance

All queries use indexed columns:
- `project_id` - All tables have index
- `file_path` - Indexed for file lookups
- `symbol_name` - Indexed for caller queries

Typical query time: <50ms

### Background Indexing

- Non-blocking: Uses `asyncio` and background tasks
- Rate limited: One repo at a time to avoid API limits
- Resumable: Failed jobs can be retried

---

## Cost

**$0** - This implementation uses:
- Built-in Python `ast` module (free)
- tree-sitter (free, open-source)
- Supabase storage (within free tier limits)
- No embedding models (no OpenAI/vector costs)

---

## Troubleshooting

### Indexing Not Starting

Check:
1. `SUPABASE_URL` and `SUPABASE_KEY` environment variables
2. Webhook receiving `installation.created` events
3. Logs for `[INDEXER]` entries

### Context Not Appearing in Reviews

Check:
1. Project is indexed: Query `indexed_projects` table
2. Symbols exist: Query `code_symbols` table
3. ContextEnricher initialized correctly

### Query Errors

Common issues:
- Schema not applied: Run `supabase_codebase_schema.sql`
- Missing indexes: Schema includes all required indexes
- Permission issues: Check Supabase API key has read/write access

---

## Future Enhancements

1. **Semantic Search** (Phase 2)
   - Add embeddings for code search
   - "Find similar functions" feature
   - Cost: ~$0.01/1000 tokens

2. **Cross-File Impact Analysis**
   - Track changes across files
   - Dependency graph visualization

3. **More Languages**
   - JavaScript/TypeScript
   - Go, Rust
   - Uses tree-sitter (easy to add)

4. **Incremental Webhooks**
   - Index on push events
   - Real-time updates
