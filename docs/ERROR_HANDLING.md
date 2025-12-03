# Error Handling & Graceful Degradation

## Overview

InspectAI implements robust error handling to ensure that failures in one agent don't break the entire pipeline. Users receive graceful, user-friendly error messages instead of technical stack traces.

## Key Features

### 1. **Agent Isolation**
- Each agent execution is wrapped in error handling
- Failures in one agent don't affect other agents
- Pipeline continues processing even when agents fail

### 2. **Graceful Error Messages**
- Technical errors converted to user-friendly messages
- Context-specific guidance for users
- No stack traces exposed to end users

### 3. **Partial Success Handling**
- System tracks successful vs failed agents
- Users get results from successful agents even if some fail
- Clear indication of what completed and what failed

## Implementation

### Safe Agent Execution

All agent calls use `_safe_execute_agent()` wrapper:

```python
# Before (brittle - crashes on error)
result = orchestrator.agents["analysis"].process(code)

# After (resilient - returns error dict)
result = orchestrator._safe_execute_agent("analysis", code)
if result.get("status") == "error":
    # Handle gracefully
    logger.warning(f"Agent failed: {result.get('error_message')}")
else:
    # Process successful result
    process_results(result)
```

### Error Message Translation

Technical errors are automatically converted to user-friendly messages:

```python
# Rate limit error
Exception("429 Too Many Requests")
→ "The CodeAnalyzer is experiencing high demand. Please try again in a minute."

# Timeout error
Exception("Request timed out after 60s")
→ "The BugDetector took too long to respond. Try breaking the PR into smaller changes."

# API key error
Exception("Invalid API key")
→ "API key error for SecurityAgent. Please contact the repository owner."
```

### Partial Success Results

When some agents succeed and others fail:

```python
{
    "status": "partial_success",
    "success_count": 3,
    "failure_count": 1,
    "successful_agents": {
        "analysis": {...},
        "security": {...},
        "test_generation": {...}
    },
    "failed_agents": {
        "bug_detection": {
            "error_message": "The bug detection took too long...",
            "error_type": "TimeoutError"
        }
    }
}
```

## GitHub PR Comments

### Success (All Agents)

```markdown
## 🔍 InspectAI Code Review

**Triggered by:** @username
**Files Reviewed:** 5
**Inline Comments:** 12

I've added inline comments on the specific lines that need attention.
```

### Partial Success (Some Agents Failed)

```markdown
## 🔍 InspectAI Code Review

**Triggered by:** @username
**Files Reviewed:** 3
**Inline Comments:** 8

⚠️ **Note:** 2 file(s) could not be analyzed due to errors.

---
*Some analysis may be incomplete. Try running the command again.*
```

### Complete Failure (All Agents Failed)

```markdown
## ⚠️ InspectAI Error

**Command:** `/inspectai_review`
**Triggered by:** @username

### What Happened
I encountered errors while trying to review the files in this PR. This might be due to:
- Large files taking too long to process
- Temporary API issues
- Network connectivity problems

### What You Can Do
- Try running `/inspectai_review` again in a few minutes
- Try `/inspectai_bugs` on specific files instead
- Contact the repository maintainer if the issue persists

---
*InspectAI is experiencing technical difficulties.*
```

## Error Categories

### 1. Rate Limiting (429)
- **User Message**: "High demand. Try again in a minute."
- **Recovery**: Automatic retry after delay
- **Prevention**: Rate limit tracking

### 2. Timeouts
- **User Message**: "Processing took too long. Try smaller changes."
- **Recovery**: Suggest breaking PR into smaller parts
- **Prevention**: File size limits, chunking

### 3. Authentication (401/403)
- **User Message**: "Authentication failed. Contact repository owner."
- **Recovery**: Admin needs to update credentials
- **Prevention**: Token refresh logic

### 4. Service Unavailable (503)
- **User Message**: "AI service temporarily unavailable."
- **Recovery**: Retry after delay
- **Prevention**: Health checks, circuit breaker

### 5. Network Errors
- **User Message**: "Network connectivity problem."
- **Recovery**: Automatic retry
- **Prevention**: Connection pooling, keep-alive

## Testing Error Handling

Run the error handling test suite:

```bash
pytest tests/test_error_handling.py -v
```

Tests cover:
- Safe agent execution with failures
- User-friendly error message generation
- Partial success result creation
- GitHub comment formatting
- Pipeline continuation on errors

## Best Practices

### For Developers

1. **Always use `_safe_execute_agent()`** instead of direct agent calls
2. **Check result status** before processing results
3. **Log technical details** but show user-friendly messages to users
4. **Track success/failure counts** for monitoring
5. **Provide actionable guidance** in error messages

### For Users

1. **Try again** - Many errors are transient
2. **Break up large PRs** - Smaller changes process faster
3. **Use alternative commands** - Try `/inspectai_bugs` if `/inspectai_review` fails
4. **Contact maintainer** - For persistent issues

## Monitoring & Logging

All errors are logged with full context:

```python
logger.error(
    f"[REVIEW] Failed to analyze {filename}: {error}",
    exc_info=True  # Includes full stack trace
)
```

Monitor these metrics:
- **Agent success rate** per agent type
- **Error types** frequency distribution  
- **Files failed** vs total files processed
- **User impact** - complete vs partial failures

## Future Enhancements

- [ ] Automatic retry with exponential backoff
- [ ] Model fallback (Gemini → GPT-4 if primary fails)
- [ ] Circuit breaker pattern for failing services
- [ ] Health dashboard showing agent status
- [ ] Detailed error analytics and alerts
