"""GitHub Webhook Handler for automatic PR reviews.

This module handles incoming webhook events from GitHub, specifically:
- Pull Request opened/synchronized events
- Issue comments (for /review command)
- Push events (optional)

Commands:
- /inspectai_review: Reviews ONLY the changed lines in the PR diff
- /inspectai_bugs: Finds bugs in WHOLE files that have changes
- /inspectai_refactor: Code improvement suggestions (style, performance, etc.)
- /inspectai_security: Security vulnerability scan using 4 specialized sub-agents
- /inspectai_tests: Generate unit tests for changed code
- /inspectai_docs: Generate/update documentation for changed code

Setup:
1. Create a GitHub App at https://github.com/settings/apps
2. Set the Webhook URL to: https://your-domain.com/webhook/github
3. Set a Webhook Secret and add it to your .env as GITHUB_WEBHOOK_SECRET
4. Subscribe to events: Pull requests, Issue comments, Push
5. Install the app on your repository

Required Environment Variables:
- GITHUB_WEBHOOK_SECRET: Secret for verifying webhook signatures
- GITHUB_TOKEN: Token for API calls (from GitHub App installation)
"""
import hashlib
import hmac
import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from pydantic import BaseModel

from ..utils.logger import get_logger
from ..github.client import GitHubClient
from ..memory.pr_memory import get_pr_memory, BugFinding
from ..utils.error_handler import (
    format_error_for_github_comment,
    format_partial_success_for_github_comment,
    GracefulErrorHandler
)
from ..feedback.feedback_system import get_feedback_system
from ..indexer import trigger_repo_indexing, get_context_enricher, get_scheduled_reindexer

logger = get_logger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhooks"])

# Store for tracking processed events (in production, use Redis/DB)
_processed_events: Dict[str, datetime] = {}


class WebhookEvent(BaseModel):
    """Model for tracking webhook events."""
    event_type: str
    action: Optional[str]
    repository: str
    sender: str
    delivery_id: str
    timestamp: datetime


def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook signature.
    
    Args:
        payload: Raw request body
        signature: X-Hub-Signature-256 header value
        secret: Webhook secret from GitHub App settings
        
    Returns:
        True if signature is valid
    """
    if not signature or not secret:
        return False
    
    expected = "sha256=" + hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected, signature)


def is_duplicate_event(delivery_id: str) -> bool:
    """Check if we've already processed this event.
    
    GitHub may retry webhook delivery, so we track processed events.
    """
    if delivery_id in _processed_events:
        return True
    
    # Clean old entries (older than 1 hour)
    cutoff = datetime.now()
    for key in list(_processed_events.keys()):
        if (cutoff - _processed_events[key]).seconds > 3600:
            del _processed_events[key]
    
    _processed_events[delivery_id] = datetime.now()
    return False


async def _check_contents_permission(github_client: GitHubClient, repo_full_name: str) -> bool:
    """Check if we have permission to read repository contents.
    
    This is needed for codebase indexing. If not granted, we gracefully
    skip indexing and use default PR-only review behavior.
    
    Args:
        github_client: GitHub client instance
        repo_full_name: Full repository name
        
    Returns:
        True if we have contents:read permission, False otherwise
    """
    try:
        # Try to access root directory - this will fail if no contents permission
        owner, repo = repo_full_name.split("/")
        # Use a lightweight API call to check access
        github_client.get_repo_contents(owner, repo, "")
        return True
    except Exception as e:
        error_str = str(e).lower()
        if "403" in error_str or "permission" in error_str or "not found" in error_str:
            logger.info(
                f"No contents:read permission for {repo_full_name}. "
                "Codebase indexing skipped. To enable, grant 'Contents: Read' permission in GitHub App settings."
            )
            return False
        # Other errors - log but assume no permission to be safe
        logger.warning(f"Could not verify contents permission for {repo_full_name}: {e}")
        return False


async def _trigger_background_indexing(repo_full_name: str, installation_id: int):
    """Trigger background codebase indexing for a repository.
    
    This runs asynchronously and doesn't block the webhook response.
    Only triggers if we have contents:read permission.
    
    Args:
        repo_full_name: Full repository name (owner/repo)
        installation_id: GitHub App installation ID
    """
    try:
        # Create GitHub client
        github_client = GitHubClient.from_installation(installation_id)
        
        # Check if we have permission to read repository contents
        has_permission = await _check_contents_permission(github_client, repo_full_name)
        
        if not has_permission:
            logger.info(
                f"Skipping codebase indexing for {repo_full_name} - "
                "contents permission not granted. PR reviews will work normally."
            )
            return None
        
        # Trigger indexing (runs in background)
        job_id = await trigger_repo_indexing(
            repo_full_name=repo_full_name,
            github_client=github_client,
            installation_id=installation_id
        )
        
        if job_id:
            logger.info(f"Background indexing started for {repo_full_name} (job: {job_id})")
        else:
            logger.warning(f"Failed to start indexing for {repo_full_name}")
            
    except Exception as e:
        logger.error(f"Error triggering indexing for {repo_full_name}: {e}")


def parse_diff_for_changed_lines(patch: str) -> List[Tuple[int, int, str]]:
    """Parse a git diff patch to extract changed line ranges.
    
    Args:
        patch: Git diff patch string
        
    Returns:
        List of (start_line, end_line, change_type) tuples
        change_type is 'added' or 'modified'
    """
    if not patch:
        return []
    
    changed_ranges = []
    current_line = 0
    
    for line in patch.split('\n'):
        # Parse hunk header: @@ -old_start,old_count +new_start,new_count @@
        hunk_match = re.match(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@', line)
        if hunk_match:
            current_line = int(hunk_match.group(1))
            continue
        
        if line.startswith('+') and not line.startswith('+++'):
            # Added line
            changed_ranges.append((current_line, current_line, 'added'))
            current_line += 1
        elif line.startswith('-') and not line.startswith('---'):
            # Deleted line - don't increment current_line
            pass
        else:
            # Context line
            current_line += 1
    
    # Merge adjacent ranges
    if not changed_ranges:
        return []
    
    merged = []
    start, end, ctype = changed_ranges[0]
    
    for i in range(1, len(changed_ranges)):
        next_start, next_end, next_type = changed_ranges[i]
        if next_start <= end + 3:  # Merge if within 3 lines
            end = next_end
        else:
            merged.append((start, end, ctype))
            start, end, ctype = next_start, next_end, next_type
    
    merged.append((start, end, ctype))
    return merged


def extract_line_number_from_finding(finding: Dict[str, Any]) -> Optional[int]:
    """Extract line number from a finding's location field.
    
    Args:
        finding: Finding dictionary with 'location' field
        
    Returns:
        Line number or None
    """
    # Try multiple fields in priority order
    for field in ["line_number", "line", "location"]:
        value = finding.get(field)
        if value is None:
            continue
            
        # If it's already an int
        if isinstance(value, int):
            return value
        
        # Try direct conversion
        try:
            return int(value)
        except (ValueError, TypeError):
            pass
        
        # Try pattern matching for strings like "line 5", "L5", ":5"
        if isinstance(value, str):
            patterns = [
                r'line\s*(\d+)',
                r'L(\d+)',
                r':(\d+)',
                r'^(\d+)$'
            ]
            for pattern in patterns:
                match = re.search(pattern, value, re.IGNORECASE)
                if match:
                    return int(match.group(1))
    
    # Also check evidence dict
    evidence = finding.get("evidence", {})
    if isinstance(evidence, dict):
        line_num = evidence.get("line_number") or evidence.get("line")
        if line_num:
            try:
                return int(line_num)
            except (ValueError, TypeError):
                pass
    
    return None


def snap_to_nearest_diff_line(line_num: int, diff_lines: set, max_distance: int = 5) -> Optional[int]:
    """Snap a line number to the nearest valid diff line.
    
    LLMs sometimes report line numbers that are off by a few lines.
    This function finds the closest valid diff line within max_distance.
    
    Args:
        line_num: The line number reported by the LLM
        diff_lines: Set of valid line numbers from the diff
        max_distance: Maximum distance to snap (default 5 lines)
        
    Returns:
        Nearest valid diff line, or None if no line within distance
    """
    if not diff_lines or line_num is None:
        return None
    
    # If the line is already in the diff, return it
    if line_num in diff_lines:
        return line_num
    
    # Find the nearest diff line within max_distance
    nearest = None
    min_distance = max_distance + 1
    
    for diff_line in diff_lines:
        distance = abs(diff_line - line_num)
        if distance < min_distance:
            min_distance = distance
            nearest = diff_line
    
    if min_distance <= max_distance:
        logger.debug(f"[SNAP] Snapped line {line_num} to {nearest} (distance: {min_distance})")
        return nearest
    
    return None


def get_diff_lines_for_file(patch: str) -> set:
    """Get set of line numbers that are in the diff (added/modified lines).
    
    These are the only lines where GitHub allows inline review comments.
    
    Args:
        patch: Git diff patch string for a file
        
    Returns:
        Set of line numbers that are in the diff
    """
    if not patch:
        return set()
    
    diff_lines = set()
    current_line = 0
    
    for line in patch.split('\n'):
        # Parse hunk header: @@ -old_start,old_count +new_start,new_count @@
        hunk_match = re.match(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@', line)
        if hunk_match:
            current_line = int(hunk_match.group(1))
            continue
        
        if line.startswith('+') and not line.startswith('+++'):
            # Added line - this is commentable
            diff_lines.add(current_line)
            current_line += 1
        elif line.startswith('-') and not line.startswith('---'):
            # Deleted line - don't increment, not on new side
            pass
        elif not line.startswith('\\'):  # Skip "\ No newline at end of file"
            # Context line - also commentable in the diff
            diff_lines.add(current_line)
            current_line += 1
    
    return diff_lines


async def process_pr_review(
    repo_full_name: str,
    pr_number: int,
    action: str,
    installation_id: Optional[int] = None
) -> Dict[str, Any]:
    """Process a PR review in the background.
    
    Args:
        repo_full_name: Full repository name (owner/repo)
        pr_number: Pull request number
        action: PR action (opened, synchronize, etc.)
        installation_id: GitHub App installation ID
        
    Returns:
        Review results
    """
    from ..orchestrator.orchestrator import OrchestratorAgent
    from config.default_config import ORCHESTRATOR_CONFIG
    import copy
    
    logger.info(f"Processing PR review for {repo_full_name}#{pr_number} (action: {action})")
    
    try:
        # Check rate limit before starting expensive operations
        try:
            github_check = GitHubClient.from_installation(installation_id) if installation_id else GitHubClient()
            rate_status = github_check.get_rate_limit_status()
            remaining = rate_status.get('remaining', 0)
            
            if remaining < 50:  # Need at least 50 API calls for a PR review
                reset_time = rate_status.get('reset', 0)
                wait_until = datetime.fromtimestamp(reset_time).strftime('%H:%M:%S') if reset_time else 'unknown'
                logger.warning(
                    f"GitHub API rate limit too low ({remaining} remaining). "
                    f"Skipping PR review for {repo_full_name}#{pr_number}. "
                    f"Rate limit resets at {wait_until}"
                )
                return {
                    "status": "rate_limited",
                    "message": f"GitHub API rate limit too low ({remaining} remaining). Will retry after reset.",
                    "reset_at": reset_time
                }
        except Exception as e:
            logger.warning(f"Could not check rate limit: {e}. Proceeding anyway...")
        
        # Initialize orchestrator
        config = copy.deepcopy(ORCHESTRATOR_CONFIG)
        from config.default_config import DEFAULT_PROVIDER, GEMINI_MODEL, BYTEZ_MODEL, OPENAI_MODEL
        provider = os.getenv("LLM_PROVIDER", DEFAULT_PROVIDER)
        
        # Set model based on provider
        model_map = {
            "gemini": GEMINI_MODEL,
            "bytez": BYTEZ_MODEL,
            "openai": OPENAI_MODEL
        }
        
        for key in config:
            if isinstance(config[key], dict):
                config[key]["provider"] = provider
                config[key]["model"] = model_map.get(provider, GEMINI_MODEL)
        
        orchestrator = OrchestratorAgent(config)
        
        try:
            # Run PR review
            task = {
                "type": "pr_review",
                "input": {
                    "repo_url": repo_full_name,
                    "pr_number": pr_number,
                    "post_comments": True  # Auto-post review comments
                }
            }
            
            result = orchestrator.process_task(task)
            logger.info(f"PR review completed for {repo_full_name}#{pr_number}")
            
            # Generate PR description on PR open, when commits are pushed, or when PR is reopened
            if action in ["opened", "synchronize", "reopened"]:
                try:
                    logger.info(f"Generating PR description for {repo_full_name}#{pr_number}")
                    
                    # Get PR files and changes
                    github_client = GitHubClient()
                    pr = github_client.get_pull_request(repo_full_name, pr_number)
                    
                    # Build code changes data for PR description generator
                    code_changes = []
                    for pr_file in pr.files:
                        code_changes.append({
                            "filename": pr_file.filename,
                            "status": pr_file.status,
                            "additions": pr_file.additions,
                            "deletions": pr_file.deletions
                        })
                    
                    # Extract bugs and analysis from the review result
                    bugs_data = result.get("bug_detection", {}) if isinstance(result, dict) else {}
                    analysis_data = result.get("analysis", {}) if isinstance(result, dict) else {}
                    
                    # Prepare input for PR description generator
                    description_input = {
                        "code_changes": code_changes,
                        "bugs": {
                            "bug_count": bugs_data.get("bug_count", 0) if isinstance(bugs_data, dict) else 0,
                            "bugs": bugs_data.get("bugs", []) if isinstance(bugs_data, dict) else []
                        },
                        "security": result.get("security", {}) if isinstance(result, dict) else {},
                        "analysis": {
                            "suggestions": analysis_data.get("suggestions", []) if isinstance(analysis_data, dict) else []
                        }
                    }
                    
                    # Generate description
                    pr_description_result = orchestrator.agents["pr_description"].process(description_input)
                    
                    if pr_description_result.get("status") == "success":
                        generated_title = pr_description_result.get("title", "")
                        generated_description = pr_description_result.get("description", "")
                        pr_type = pr_description_result.get("pr_type", "general")
                        
                        logger.info(f"Generated PR description: {pr_type}")
                        logger.info(f"Generated title: {generated_title}")
                        
                        # Update PR description on GitHub
                        try:
                            github_client.update_pr_body(
                                repo_full_name,
                                pr_number,
                                generated_description
                            )
                            logger.info(f"Updated PR description for {repo_full_name}#{pr_number}")
                            result["pr_description"] = {
                                "status": "updated",
                                "title": generated_title,
                                "type": pr_type
                            }
                        except Exception as e:
                            logger.warning(f"Failed to update PR description: {e}")
                            result["pr_description"] = {
                                "status": "generated_not_posted",
                                "title": generated_title,
                                "type": pr_type,
                                "error": str(e)
                            }
                    else:
                        logger.warning(f"Failed to generate PR description: {pr_description_result.get('error')}")
                        
                except Exception as e:
                    logger.warning(f"Error generating PR description: {e}", exc_info=True)
            
            return result
            
        finally:
            orchestrator.cleanup()
            
    except Exception as e:
        logger.error(f"PR review failed for {repo_full_name}#{pr_number}: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


async def handle_agent_command(
    repo_full_name: str,
    pr_number: int,
    comment_author: str,
    command: str,
    installation_id: Optional[int] = None
) -> Dict[str, Any]:
    """Handle InspectAI agent commands with specialized behavior.
    
    Commands:
    - review: Analyze ONLY changed lines in PR diff, post inline comments
    - bugs: Analyze WHOLE files, store findings in memory for refactor
    - refactor: Read bugs from memory and auto-fix by creating suggestions
    
    Args:
        repo_full_name: Full repository name (owner/repo)
        pr_number: Pull request number
        comment_author: Who triggered the command
        command: The command triggered (review, bugs, refactor)
        installation_id: GitHub App installation ID for authentication
        
    Returns:
        Result of the operation
    """
    from ..orchestrator.orchestrator import OrchestratorAgent
    from config.default_config import ORCHESTRATOR_CONFIG
    import copy
    
    logger.info(f"Handling /InspectAI_{command} command for {repo_full_name}#{pr_number} by {comment_author}")
    
    try:
        # Initialize GitHub client
        if installation_id:
            github_client = GitHubClient.from_installation(installation_id)
            logger.info(f"Using GitHub App installation token for installation {installation_id}")
        else:
            github_client = GitHubClient()
            logger.warning("No installation_id provided, using fallback token")
        
        # Initialize orchestrator with configured provider
        config = copy.deepcopy(ORCHESTRATOR_CONFIG)
        from config.default_config import DEFAULT_PROVIDER, GEMINI_MODEL, BYTEZ_MODEL, OPENAI_MODEL
        provider = os.getenv("LLM_PROVIDER", DEFAULT_PROVIDER)
        
        model_map = {
            "gemini": GEMINI_MODEL,
            "bytez": BYTEZ_MODEL,
            "openai": OPENAI_MODEL
        }
        
        for key in config:
            if isinstance(config[key], dict):
                config[key]["provider"] = provider
                config[key]["model"] = model_map.get(provider, GEMINI_MODEL)
        
        orchestrator = OrchestratorAgent(config)
        pr_memory = get_pr_memory()
        
        try:
            # Get PR files
            pr = github_client.get_pull_request(repo_full_name, pr_number)
            
            # Route to appropriate handler
            if command == "review":
                return await _handle_review_command(
                    github_client, orchestrator, pr_memory,
                    repo_full_name, pr_number, pr, comment_author
                )
            elif command == "bugs":
                return await _handle_bugs_command(
                    github_client, orchestrator, pr_memory,
                    repo_full_name, pr_number, pr, comment_author
                )
            elif command == "refactor":
                # Refactor is now combined with review - redirect
                logger.info(f"[REFACTOR] Redirecting to combined review command")
                return await _handle_review_command(
                    github_client, orchestrator, pr_memory,
                    repo_full_name, pr_number, pr, comment_author
                )
            elif command == "security":
                return await _handle_security_command(
                    github_client, orchestrator, pr_memory,
                    repo_full_name, pr_number, pr, comment_author
                )
            elif command == "tests":
                return await _handle_tests_command(
                    github_client, orchestrator, pr_memory,
                    repo_full_name, pr_number, pr, comment_author
                )
            elif command == "docs":
                return await _handle_docs_command(
                    github_client, orchestrator, pr_memory,
                    repo_full_name, pr_number, pr, comment_author
                )
            elif command == "help":
                return await _handle_help_command(
                    github_client, repo_full_name, pr_number, comment_author
                )
            # Hidden developer commands (not shown in /help)
            elif command == "reindex":
                return await _handle_reindex_command(
                    github_client, repo_full_name, pr_number, comment_author, installation_id
                )
            elif command == "status":
                return await _handle_status_command(
                    github_client, repo_full_name, pr_number, comment_author
                )
            else:
                return {"status": "error", "error": f"Unknown command: {command}"}
            
        finally:
            orchestrator.cleanup()
        
    except Exception as e:
        logger.error(f"Failed to handle command on {repo_full_name}#{pr_number}: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


async def _handle_review_command(
    github_client: GitHubClient,
    orchestrator,
    pr_memory,
    repo_full_name: str,
    pr_number: int,
    pr,
    comment_author: str
) -> Dict[str, Any]:
    """Handle /inspectai_review - Reviews ONLY changed lines in PR diff.
    
    Posts inline comments on specific lines that have issues.
    Focuses on issues INTRODUCED by the changes, not general code improvements.
    Uses codebase indexing to provide context about callers/dependencies.
    """
    logger.info(f"[REVIEW] Starting diff-only review for {repo_full_name}#{pr_number}")
    
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    # Get codebase context for changed files
    context_enricher = get_context_enricher()
    codebase_context = {}
    
    try:
        # Collect changed files for context enrichment
        changed_files = []
        for pr_file in pr.files:
            if pr_file.status != "removed" and orchestrator._is_code_file(pr_file.filename):
                changed_files.append(pr_file.filename)
        
        # Get enriched context (callers, dependencies, impact)
        if changed_files:
            codebase_context = await context_enricher.enrich_pr_context(
                repo_full_name=repo_full_name,
                changed_files=changed_files,
                diff_content="\n".join([f.patch for f in pr.files if f.patch])
            )
            logger.info(f"[REVIEW] Enriched context for {len(changed_files)} files: {len(codebase_context.get('context_summary', []))} items")
    except Exception as e:
        logger.warning(f"[REVIEW] Could not get codebase context: {e}")
        # Continue without enriched context - graceful degradation
    
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    def process_single_file(pr_file):
        """Process a single file and return inline comments."""
        try:
            if pr_file.status == "removed":
                return []
            
            if not orchestrator._is_code_file(pr_file.filename):
                return []
            
            # Get changed line ranges from diff
            changed_ranges = parse_diff_for_changed_lines(pr_file.patch)
            if not changed_ranges:
                logger.info(f"[REVIEW] No changed lines in {pr_file.filename}")
                return []
            
            # Get file content
            content = github_client.get_pr_file_content(repo_full_name, pr_number, pr_file.filename)
            
            # Get file-specific codebase context
            file_context_str = ""
            file_context = codebase_context.get("file_contexts", {}).get(pr_file.filename, {})
            if file_context:
                context_items = []
                
                # Add callers info
                for symbol, callers in file_context.get("callers", {}).items():
                    if callers:
                        context_items.append(f"- `{symbol}` is called by: {', '.join(callers[:5])}")
                
                # Add dependencies info
                for symbol, deps in file_context.get("dependencies", {}).items():
                    if deps:
                        context_items.append(f"- `{symbol}` depends on: {', '.join(deps[:5])}")
                
                # Add impact score
                impact = file_context.get("impact_score", 0)
                if impact > 5:
                    context_items.append(f"- ⚠️ HIGH IMPACT: Changes may affect {impact} other places in codebase")
                
                if context_items:
                    file_context_str = f"""
CODEBASE CONTEXT (from indexed repository):
{chr(10).join(context_items)}
"""
            
            # Build diff context for the LLM - comprehensive review (bugs + improvements)
            diff_context = f"""FILE: {pr_file.filename}
DIFF PATCH (shows what was changed with + for additions, - for removals):
```diff
{pr_file.patch}
```

FULL FILE CONTEXT:
```
{content}
```

CHANGED LINE RANGES: {', '.join([f'{s}-{e}' for s, e, _ in changed_ranges])}
{file_context_str}
REVIEW INSTRUCTIONS - Be thorough but focused:

**BUGS & ERRORS (High Priority):**
1. Logic errors, incorrect conditions, wrong operators
2. Off-by-one errors in loops or array access
3. Null/undefined access without checks
4. Resource leaks (unclosed files, connections)
5. Race conditions or threading issues
6. Type mismatches or incorrect conversions

**CODE QUALITY (Medium Priority):**
1. Missing error handling for operations that can fail
2. Hardcoded values that should be configurable
3. Inefficient algorithms (O(n²) when O(n) is possible)
4. Code that will break in edge cases

**DO NOT REPORT:**
- Style preferences (formatting, naming that works fine)
- General suggestions for code that wasn't changed
- Theoretical issues that are unlikely in practice

**OUTPUT FORMAT:**
- Each issue MUST reference a specific line number from the changed ranges
- Include severity: critical (will crash), high (likely bug), medium (potential issue), low (improvement)
- Be specific about what's wrong and how to fix it
"""
            
            logger.info(f"[REVIEW] Analyzing {len(changed_ranges)} changed regions in {pr_file.filename}")
            
            # Run analysis with diff context - use safe execution
            analysis = orchestrator._safe_execute_agent("analysis", diff_context)
            
            # Check if agent failed
            if analysis.get("status") == "error":
                logger.warning(f"[REVIEW] Analysis failed for {pr_file.filename}: {analysis.get('error_message')}")
                return []  # Return empty instead of crashing
            
            # Create inline comments for findings - snap to nearest diff line
            # Get diff lines for snapping
            diff_lines = set()
            for start, end, _ in changed_ranges:
                diff_lines.update(range(start, end + 1))
            
            file_comments = []
            for suggestion in analysis.get("suggestions", []):
                if isinstance(suggestion, dict):
                    raw_line_num = extract_line_number_from_finding(suggestion)
                    
                    # Skip findings without a valid line number
                    if not raw_line_num:
                        logger.debug(f"[REVIEW] Skipping finding without line number: {suggestion.get('description', '')[:50]}")
                        continue
                    
                    # Snap to nearest valid diff line (LLMs often report slightly wrong line numbers)
                    valid_line = snap_to_nearest_diff_line(raw_line_num, diff_lines, max_distance=3)
                    
                    # Skip findings on lines that aren't near any changed line
                    if valid_line is None:
                        logger.debug(f"[REVIEW] Skipping finding on line {raw_line_num} - not near diff")
                        continue
                    
                    comment_body = _format_inline_comment(suggestion)
                    file_comments.append({
                        "path": pr_file.filename,
                        "line": valid_line,
                        "side": "RIGHT",
                        "body": comment_body,
                        # Store metadata for feedback system
                        "category": suggestion.get("category", "Code Review"),
                        "severity": suggestion.get("severity", "medium"),
                        "description": suggestion.get("description", ""),
                        "confidence": suggestion.get("confidence", 0.7)
                    })
            
            # Store review context in memory
            pr_memory.store_review_context(
                repo_full_name, pr_number, "review",
                f"Reviewed {pr_file.filename}: {len(analysis.get('suggestions', []))} suggestions",
                {"file": pr_file.filename, "command": "review"}
            )
            
            return file_comments
            
        except Exception as e:
            logger.error(f"[REVIEW] Failed to analyze {pr_file.filename}: {e}", exc_info=True)
            # Don't crash the pipeline - just skip this file
            return []
    
    # Process files in parallel (max 5 at a time to avoid overwhelming LLM API)
    all_comments = []  # Changed from inline_comments
    files_reviewed = 0
    files_failed = 0
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_file = {executor.submit(process_single_file, pr_file): pr_file for pr_file in pr.files}
        
        for future in as_completed(future_to_file):
            pr_file = future_to_file[future]
            try:
                file_comments = future.result()
                if file_comments:
                    all_comments.extend(file_comments)
                    files_reviewed += 1
                elif orchestrator._is_code_file(pr_file.filename) and pr_file.status != "removed":
                    # File was processed but no issues found
                    files_reviewed += 1
            except Exception as e:
                logger.error(f"[REVIEW] Error processing {pr_file.filename}: {e}")
                files_failed += 1
                continue
    
    # Apply feedback filtering BEFORE posting
    feedback_system = get_feedback_system()
    filtered_comments = await feedback_system.filter_by_feedback(all_comments, repo_full_name)
    
    # Prepare inline comments for GitHub (remove metadata)
    inline_comments = [
        {"path": c["path"], "line": c["line"], "side": c["side"], "body": c["body"]}
        for c in filtered_comments
    ]
    
    # Post review with inline comments
    if inline_comments:
        summary = f"""## 🔍 InspectAI Code Review

**Triggered by:** @{comment_author}
**Files Reviewed:** {files_reviewed}
**Inline Comments:** {len(inline_comments)}

I've added inline comments on the specific lines that need attention.
Only the **changed lines** in this PR were reviewed.
"""
        
        # Add warning if some files failed
        if files_failed > 0:
            summary += f"\n⚠️ **Note:** {files_failed} file(s) could not be analyzed due to errors.\n"
        
        summary += "\n---\n*Use `/inspectai_bugs` to scan entire files for bugs.*\n"
        
        # Merge comments on the same line
        merged_comments = _merge_inline_comments(inline_comments)
        try:
            result = github_client.create_review(
                repo_url=repo_full_name,
                pr_number=pr_number,
                body=summary,
                event="COMMENT",
                comments=merged_comments
            )
            logger.info(f"[REVIEW] Posted review with {len(merged_comments)} inline comments")
            
            # Store comments WITHOUT embeddings (lazy generation when feedback arrives)
            # This saves computation - embeddings only generated for comments that get feedback
            review_id = result.get("id")
            for comment_data in filtered_comments:
                try:
                    await feedback_system.store_comment(
                        repo_full_name=repo_full_name,
                        pr_number=pr_number,
                        file_path=comment_data["path"],
                        line_number=comment_data["line"],
                        comment_body=comment_data["body"],
                        category=comment_data.get("category", "Code Review"),
                        severity=comment_data.get("severity", "medium"),
                        github_comment_id=None,  # Will be populated during reaction sync
                        command_type="review",
                        generate_embedding=False  # Lazy - generated when feedback arrives
                    )
                except Exception as e:
                    logger.error(f"Error storing comment in feedback system: {e}")
            
            # Record filter stats (still useful for monitoring)
            await feedback_system.record_filter_stats(
                repo_full_name=repo_full_name,
                pr_number=pr_number,
                command_type="review",
                total_generated=len(all_comments),
                filtered_count=len(all_comments) - len(filtered_comments),
                boosted_count=sum(1 for c in filtered_comments if c.get("confidence", 0.7) > 0.8)
            )
            
            return {"status": "success", "review_id": review_id, "comments": len(merged_comments)}
        except Exception as e:
            logger.error(f"[REVIEW] Failed to post review: {e}")
            # Fallback to regular comment - graceful degradation
            github_client.post_pr_comment(repo_full_name, pr_number, summary)
            return {"status": "partial", "error": str(e), "comments": len(inline_comments)}
    
    # Check if we reviewed any files at all
    elif files_reviewed > 0:
        # No issues found
        message = f"""## 🔍 InspectAI Code Review

**Triggered by:** @{comment_author}
**Files Reviewed:** {files_reviewed}

✅ **No issues found in the changed lines!**

The diff looks good. Only changed lines were reviewed.
"""
        
        if files_failed > 0:
            message += f"\n⚠️ **Note:** {files_failed} file(s) could not be analyzed.\n"
        
        message += "\n---\n*Use `/inspectai_bugs` to do a deeper scan of entire files.*\n"
        
        github_client.post_pr_comment(repo_full_name, pr_number, message)
        return {"status": "success", "comments": 0}
    
    else:
        # Complete failure - all files failed to process
        error_message = f"""## ⚠️ InspectAI Error

**Command:** `/inspectai_review`
**Triggered by:** @{comment_author}

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
*InspectAI is experiencing technical difficulties. Our team has been notified.*
"""
        
        github_client.post_pr_comment(repo_full_name, pr_number, error_message)
        return {"status": "error", "message": "All files failed to process"}


async def _handle_bugs_command(
    github_client: GitHubClient,
    orchestrator,
    pr_memory,
    repo_full_name: str,
    pr_number: int,
    pr,
    comment_author: str
) -> Dict[str, Any]:
    """Handle /inspectai_bugs - Finds bugs CAUSED BY the changed code.
    
    Focuses on issues introduced by the PR changes, not generic code suggestions.
    """
    logger.info(f"[BUGS] Starting bug scan for changes in {repo_full_name}#{pr_number}")
    
    all_bugs: List[BugFinding] = []
    inline_comments = []
    files_scanned = 0
    files_failed = 0
    
    # Build a map of which lines are in the diff for each file
    diff_lines_by_file: Dict[str, set] = {}
    for pr_file in pr.files:
        if hasattr(pr_file, 'patch') and pr_file.patch:
            diff_lines_by_file[pr_file.filename] = get_diff_lines_for_file(pr_file.patch)
        else:
            diff_lines_by_file[pr_file.filename] = set()
    
    for pr_file in pr.files:
        if pr_file.status == "removed":
            continue
        
        if not orchestrator._is_code_file(pr_file.filename):
            continue
        
        try:
            # Get file content and diff
            content = github_client.get_pr_file_content(repo_full_name, pr_number, pr_file.filename)
            diff_patch = pr_file.patch if hasattr(pr_file, 'patch') else ""
            diff_lines = diff_lines_by_file.get(pr_file.filename, set())
            
            if not diff_lines:
                logger.info(f"[BUGS] No changed lines in {pr_file.filename}, skipping")
                continue
            
            logger.info(f"[BUGS] Scanning {pr_file.filename} - {len(diff_lines)} changed lines")
            
            # Build context that tells LLM what changed
            diff_context = f"""
=== IMPORTANT: FOCUS ONLY ON BUGS CAUSED BY THE CHANGES ===

The following lines were CHANGED in this PR (these are the lines you should focus on):
Changed line numbers: {sorted(diff_lines)}

Here is the diff showing what was changed:
```diff
{diff_patch}
```

Your task: Find bugs, errors, or issues that are DIRECTLY CAUSED by these changes.
Do NOT report:
- General code style suggestions
- Issues in unchanged parts of the code
- Best practice recommendations unrelated to the changes

Only report ACTUAL BUGS introduced by the changed code.
"""
            
            # Run bug detection with diff context - use safe execution
            bugs_result = orchestrator._safe_execute_agent("bug_detection", (content, diff_context))
            
            # Check if agent failed
            if bugs_result.get("status") == "error":
                logger.warning(f"[BUGS] Bug detection failed for {pr_file.filename}: {bugs_result.get('error_message')}")
                files_failed += 1
                continue
            
            logger.info(f"[BUGS] Bug detection returned {bugs_result.get('bug_count', 0)} bugs")
            
            # Also run security scan with diff context - use safe execution
            security_result = orchestrator._safe_execute_agent("security", (content, diff_context))
            
            # Check if agent failed
            if security_result.get("status") == "error":
                logger.warning(f"[BUGS] Security scan failed for {pr_file.filename}: {security_result.get('error_message')}")
                # Don't increment files_failed again, we already got bug results
            else:
                logger.info(f"[BUGS] Security scan returned {security_result.get('vulnerability_count', 0)} vulnerabilities")
            
            # Convert to BugFinding objects - snap to nearest diff line if needed
            for bug in bugs_result.get("bugs", []):
                if isinstance(bug, dict):
                    raw_line_num = extract_line_number_from_finding(bug)
                    
                    # Snap to nearest valid diff line (LLMs often report slightly wrong line numbers)
                    line_num = snap_to_nearest_diff_line(raw_line_num, diff_lines, max_distance=5)
                    
                    if line_num is None:
                        logger.debug(f"[BUGS] Skipping bug - line {raw_line_num} not near any diff line")
                        continue
                    
                    finding = BugFinding(
                        file_path=pr_file.filename,
                        line_number=line_num,
                        category=bug.get("category", "Bug"),
                        severity=bug.get("severity", "medium"),
                        description=bug.get("description", ""),
                        fix_suggestion=bug.get("fix_suggestion") or bug.get("fix", ""),
                        confidence=bug.get("confidence", 0.5),
                        code_snippet=_extract_code_snippet(content, line_num)
                    )
                    all_bugs.append(finding)
                    
                    inline_comments.append({
                        "path": pr_file.filename,
                        "line": line_num,
                        "side": "RIGHT",
                        "body": _format_bug_comment(finding)
                    })
            
            # Add security vulnerabilities - also snap to nearest diff line
            for vuln in security_result.get("vulnerabilities", []):
                if isinstance(vuln, dict):
                    raw_line_num = extract_line_number_from_finding(vuln)
                    
                    # Snap to nearest valid diff line
                    line_num = snap_to_nearest_diff_line(raw_line_num, diff_lines, max_distance=5)
                    
                    if line_num is None:
                        continue
                    
                    finding = BugFinding(
                        file_path=pr_file.filename,
                        line_number=line_num,
                        category=f"Security: {vuln.get('category', 'Vulnerability')}",
                        severity=vuln.get("severity", "high"),
                        description=vuln.get("description", ""),
                        fix_suggestion=vuln.get("remediation") or vuln.get("fix", ""),
                        confidence=vuln.get("confidence", 0.6),
                        code_snippet=_extract_code_snippet(content, line_num)
                    )
                    all_bugs.append(finding)
                    
                    inline_comments.append({
                        "path": pr_file.filename,
                        "line": line_num,
                        "side": "RIGHT",
                        "body": _format_bug_comment(finding)
                    })
            
            files_scanned += 1
            
        except Exception as e:
            logger.error(f"[BUGS] Failed to scan {pr_file.filename}: {e}", exc_info=True)
            files_failed += 1
            continue
    
    # Build severity summary
    severity_counts = {}
    for bug in all_bugs:
        severity_counts[bug.severity] = severity_counts.get(bug.severity, 0) + 1
    
    severity_summary = " | ".join([
        f"{'🔴' if s == 'critical' else '🟠' if s == 'high' else '🟡' if s == 'medium' else '⚪'} {s.capitalize()}: {c}"
        for s, c in sorted(severity_counts.items(), key=lambda x: ['critical', 'high', 'medium', 'low'].index(x[0]) if x[0] in ['critical', 'high', 'medium', 'low'] else 4)
    ])
    
    summary = f"""## 🐛 InspectAI Bug Detection

**Triggered by:** @{comment_author}
**Files Scanned:** {files_scanned}
**Issues Found:** {len(all_bugs)}

{severity_summary if severity_summary else "✅ No issues found in changed code!"}

{f"I've added **{len(inline_comments)} inline comments** on issues introduced by your changes." if inline_comments else ""}
"""
    
    # Add warning if some files failed
    if files_failed > 0:
        summary += f"\n⚠️ **Note:** {files_failed} file(s) could not be scanned due to errors.\n"
    
    # Check if we scanned any files at all
    if files_scanned == 0:
        # Complete failure
        error_message = f"""## ⚠️ InspectAI Error

**Command:** `/inspectai_bugs`
**Triggered by:** @{comment_author}

### What Happened
I couldn't scan any files in this PR due to technical errors. This might be because:
- The PR contains very large files
- Temporary API issues
- Network connectivity problems

### What You Can Do
- Try running `/inspectai_bugs` again in a few minutes
- Try `/inspectai_review` for a quicker diff-only review instead
- Contact the repository maintainer if the issue persists

---
*InspectAI is experiencing technical difficulties. Our team has been notified.*
"""
        github_client.post_pr_comment(repo_full_name, pr_number, error_message)
        return {"status": "error", "message": "All files failed to scan"}
    
    # Apply feedback filtering to bug findings
    feedback_system = get_feedback_system()
    if inline_comments:
        # Convert to format expected by feedback system
        comments_for_feedback = [
            {
                "description": c.get("body", ""),
                "category": "Bug Detection",
                "severity": "medium",
                "confidence": 0.7
            }
            for c in inline_comments
        ]
        filtered_comments_data = await feedback_system.filter_by_feedback(comments_for_feedback, repo_full_name)
        
        # Filter inline_comments based on feedback results
        filtered_count = len(inline_comments) - len(filtered_comments_data)
        if filtered_count > 0:
            logger.info(f"[BUGS] Feedback system filtered {filtered_count} comments based on past reactions")
            # Keep comments that passed filter (by index)
            inline_comments = inline_comments[:len(filtered_comments_data)]
    
    if inline_comments:
        # Merge comments on the same line
        merged_comments = _merge_inline_comments(inline_comments)
        try:
            result = github_client.create_review(
                repo_url=repo_full_name,
                pr_number=pr_number,
                body=summary,
                event="COMMENT",
                comments=merged_comments[:50]  # GitHub limits to 50 comments per review
            )
            
            # Store comments WITHOUT embeddings (lazy generation when feedback arrives)
            for comment in merged_comments[:50]:
                try:
                    await feedback_system.store_comment(
                        repo_full_name=repo_full_name,
                        pr_number=pr_number,
                        file_path=comment.get("path", ""),
                        line_number=comment.get("line", 0),
                        comment_body=comment.get("body", ""),
                        category="Bug Detection",
                        severity="medium",
                        command_type="bugs",
                        generate_embedding=False  # Lazy - generated when feedback arrives
                    )
                except Exception as e:
                    logger.debug(f"[BUGS] Failed to store comment for feedback: {e}")
            
            return {"status": "success", "bugs_found": len(all_bugs), "comments": len(merged_comments)}
        except Exception as e:
            logger.error(f"[BUGS] Failed to post review: {e}")
            github_client.post_pr_comment(repo_full_name, pr_number, summary)
            return {"status": "partial", "bugs_found": len(all_bugs), "error": str(e)}
    else:
        github_client.post_pr_comment(repo_full_name, pr_number, summary)
        return {"status": "success", "bugs_found": 0}


async def _handle_refactor_command(
    github_client: GitHubClient,
    orchestrator,
    pr_memory,
    repo_full_name: str,
    pr_number: int,
    pr,
    comment_author: str
) -> Dict[str, Any]:
    """Handle /inspectai_refactor - Code improvement suggestions.
    
    Analyzes code for refactoring opportunities (not bug fixes).
    """
    logger.info(f"[REFACTOR] Starting code improvement analysis for {repo_full_name}#{pr_number}")
    
    all_suggestions = []
    inline_comments = []
    suggestions_not_in_diff = []
    files_analyzed = 0
    files_failed = 0
    
    # Build a map of which lines are in the diff for each file
    diff_lines_by_file: Dict[str, set] = {}
    for pr_file in pr.files:
        if hasattr(pr_file, 'patch') and pr_file.patch:
            diff_lines_by_file[pr_file.filename] = get_diff_lines_for_file(pr_file.patch)
        else:
            diff_lines_by_file[pr_file.filename] = set()
    
    for pr_file in pr.files:
        if pr_file.status == "removed":
            continue
        
        if not orchestrator._is_code_file(pr_file.filename):
            continue
        
        try:
            content = github_client.get_pr_file_content(repo_full_name, pr_number, pr_file.filename)
            logger.info(f"[REFACTOR] Analyzing {pr_file.filename} for improvements")
            
            diff_lines = diff_lines_by_file.get(pr_file.filename, set())
            
            # Run code analysis for refactoring suggestions - use safe execution
            analysis = orchestrator._safe_execute_agent("analysis", content)
            
            # Check if agent failed
            if analysis.get("status") == "error":
                logger.warning(f"[REFACTOR] Analysis failed for {pr_file.filename}: {analysis.get('error_message')}")
                files_failed += 1
                continue
            
            for suggestion in analysis.get("suggestions", []):
                if isinstance(suggestion, dict):
                    suggestion["file"] = pr_file.filename
                    all_suggestions.append(suggestion)
                    
                    line_num = extract_line_number_from_finding(suggestion) or 1
                    
                    if line_num in diff_lines:
                        inline_comments.append({
                            "path": pr_file.filename,
                            "line": line_num,
                            "side": "RIGHT",
                            "body": _format_inline_comment(suggestion)
                        })
                    else:
                        suggestions_not_in_diff.append({
                            "file": pr_file.filename,
                            "line": line_num,
                            "suggestion": suggestion
                        })
            
            files_analyzed += 1
            
        except Exception as e:
            logger.error(f"[REFACTOR] Failed to analyze {pr_file.filename}: {e}", exc_info=True)
            files_failed += 1
            continue
    
    # Build list of suggestions not in diff
    suggestions_text = ""
    if suggestions_not_in_diff:
        suggestions_text = "\n\n### 📋 Suggestions Outside Changed Lines:\n"
        for s in suggestions_not_in_diff[:10]:
            desc = s["suggestion"].get("description", "")[:80]
            suggestions_text += f"\n- **{s['file']}:{s['line']}** - {desc}..."
        if len(suggestions_not_in_diff) > 10:
            suggestions_text += f"\n- *...and {len(suggestions_not_in_diff) - 10} more*"
    
    # Post review with inline comments
    summary = f"""## ♻️ InspectAI Refactor - Code Improvements

**Triggered by:** @{comment_author}
**Files Analyzed:** {files_analyzed}
**Suggestions:** {len(all_suggestions)}

{f"I've added **{len(inline_comments)} inline comments** on lines in the diff." if inline_comments else "✅ Code looks clean! No major improvements needed."}
{suggestions_text}
"""
    
    # Add warning if some files failed
    if files_failed > 0:
        summary += f"\n⚠️ **Note:** {files_failed} file(s) could not be analyzed due to errors.\n"
    
    summary += "\n---\n*Use `/inspectai_review` for quick code review or `/inspectai_bugs` for deep bug scanning.*\n"
    
    # Check if we analyzed any files at all
    if files_analyzed == 0:
        # Complete failure
        error_message = f"""## ⚠️ InspectAI Error

**Command:** `/inspectai_refactor`
**Triggered by:** @{comment_author}

### What Happened
I couldn't analyze any files in this PR. This might be due to:
- Large files causing processing timeouts
- Temporary API service issues
- Network connectivity problems

### What You Can Do
- Try running `/inspectai_refactor` again in a few minutes
- Try `/inspectai_review` or `/inspectai_bugs` instead
- Contact the repository maintainer if the issue persists

---
*InspectAI is experiencing technical difficulties. Our team has been notified.*
"""
        github_client.post_pr_comment(repo_full_name, pr_number, error_message)
        return {"status": "error", "message": "All files failed to analyze"}
    
    # Apply feedback filtering to refactor suggestions
    feedback_system = get_feedback_system()
    if inline_comments:
        # Convert to format expected by feedback system
        comments_for_feedback = [
            {
                "description": c.get("body", ""),
                "category": "Refactor",
                "severity": "low",
                "confidence": 0.6
            }
            for c in inline_comments
        ]
        filtered_comments_data = await feedback_system.filter_by_feedback(comments_for_feedback, repo_full_name)
        
        # Filter inline_comments based on feedback results
        filtered_count = len(inline_comments) - len(filtered_comments_data)
        if filtered_count > 0:
            logger.info(f"[REFACTOR] Feedback system filtered {filtered_count} comments based on past reactions")
            inline_comments = inline_comments[:len(filtered_comments_data)]
    
    if inline_comments:
        # Merge comments on the same line
        merged_comments = _merge_inline_comments(inline_comments)
        try:
            result = github_client.create_review(
                repo_url=repo_full_name,
                pr_number=pr_number,
                body=summary,
                event="COMMENT",
                comments=merged_comments[:50]
            )
            
            # Store comments WITHOUT embeddings (lazy generation when feedback arrives)
            for comment in merged_comments[:50]:
                try:
                    await feedback_system.store_comment(
                        repo_full_name=repo_full_name,
                        pr_number=pr_number,
                        file_path=comment.get("path", ""),
                        line_number=comment.get("line", 0),
                        comment_body=comment.get("body", ""),
                        category="Refactor",
                        severity="low",
                        command_type="refactor",
                        generate_embedding=False  # Lazy - generated when feedback arrives
                    )
                except Exception as e:
                    logger.debug(f"[REFACTOR] Failed to store comment for feedback: {e}")
            
            return {"status": "success", "suggestions": len(all_suggestions)}
        except Exception as e:
            logger.error(f"[REFACTOR] Failed to post review: {e}")
            github_client.post_pr_comment(repo_full_name, pr_number, summary)
            return {"status": "partial", "suggestions": len(all_suggestions), "error": str(e)}
    else:
        github_client.post_pr_comment(repo_full_name, pr_number, summary)
        return {"status": "success", "suggestions": 0}


async def _handle_security_command(
    github_client: GitHubClient,
    orchestrator,
    pr_memory,
    repo_full_name: str,
    pr_number: int,
    pr,
    comment_author: str
) -> Dict[str, Any]:
    """Handle /inspectai_security - Security vulnerability scan.
    
    Uses 4 specialized security sub-agents:
    - InjectionScanner: SQL/command injection
    - AuthScanner: Authentication/authorization flaws
    - DataExposureScanner: Hardcoded secrets, sensitive data
    - DependencyScanner: Unsafe dependencies
    """
    logger.info(f"[SECURITY] Starting security scan for {repo_full_name}#{pr_number}")
    
    all_vulnerabilities = []
    inline_comments = []
    files_scanned = 0
    files_failed = 0
    
    # Build diff lines map
    diff_lines_by_file: Dict[str, set] = {}
    for pr_file in pr.files:
        if hasattr(pr_file, 'patch') and pr_file.patch:
            diff_lines_by_file[pr_file.filename] = get_diff_lines_for_file(pr_file.patch)
        else:
            diff_lines_by_file[pr_file.filename] = set()
    
    for pr_file in pr.files:
        if pr_file.status == "removed":
            continue
        
        if not orchestrator._is_code_file(pr_file.filename):
            continue
        
        try:
            content = github_client.get_pr_file_content(repo_full_name, pr_number, pr_file.filename)
            diff_patch = pr_file.patch if hasattr(pr_file, 'patch') else ""
            diff_lines = diff_lines_by_file.get(pr_file.filename, set())
            
            if not diff_lines:
                continue
            
            logger.info(f"[SECURITY] Scanning {pr_file.filename} - {len(diff_lines)} changed lines")
            
            # Build security-focused context
            security_context = f"""
=== SECURITY VULNERABILITY SCAN ===

File: {pr_file.filename}
Changed lines: {sorted(diff_lines)}

Diff:
```diff
{diff_patch}
```

Focus on security vulnerabilities introduced by changes:
- SQL/NoSQL Injection
- Command Injection
- XSS vulnerabilities
- Hardcoded secrets/credentials
- Authentication bypasses
- Path traversal
- Insecure deserialization
- SSRF vulnerabilities

ONLY report vulnerabilities in the changed code (lines {sorted(diff_lines)}).
"""
            
            # Run security scan
            security_result = orchestrator._safe_execute_agent("security", (content, security_context))
            
            if security_result.get("status") == "error":
                logger.warning(f"[SECURITY] Scan failed for {pr_file.filename}: {security_result.get('error_message')}")
                files_failed += 1
                continue
            
            logger.info(f"[SECURITY] Found {security_result.get('vulnerability_count', 0)} vulnerabilities")
            
            # Process vulnerabilities - snap to nearest diff line
            for vuln in security_result.get("vulnerabilities", []):
                if isinstance(vuln, dict):
                    raw_line_num = extract_line_number_from_finding(vuln)
                    
                    # Snap to nearest valid diff line
                    line_num = snap_to_nearest_diff_line(raw_line_num, diff_lines, max_distance=5)
                    
                    if line_num is None:
                        continue
                    
                    finding = BugFinding(
                        file_path=pr_file.filename,
                        line_number=line_num,
                        category=f"🔒 {vuln.get('category', 'Security')}",
                        severity=vuln.get("severity", "high"),
                        description=vuln.get("description", ""),
                        fix_suggestion=vuln.get("remediation") or vuln.get("fix_suggestion") or vuln.get("fix", ""),
                        confidence=vuln.get("confidence", 0.7),
                        code_snippet=_extract_code_snippet(content, line_num)
                    )
                    all_vulnerabilities.append(finding)
                    
                    inline_comments.append({
                        "path": pr_file.filename,
                        "line": line_num,
                        "side": "RIGHT",
                        "body": _format_security_comment(finding),
                        "category": vuln.get("category", "Security"),
                        "severity": vuln.get("severity", "high")
                    })
            
            files_scanned += 1
            
        except Exception as e:
            logger.error(f"[SECURITY] Failed to scan {pr_file.filename}: {e}", exc_info=True)
            files_failed += 1
            continue
    
    # Calculate risk score
    risk_score = _calculate_security_risk_score(all_vulnerabilities)
    risk_emoji = "🔴" if risk_score >= 7 else "🟠" if risk_score >= 4 else "🟢"
    
    # Build severity summary
    severity_counts = {}
    for vuln in all_vulnerabilities:
        severity_counts[vuln.severity] = severity_counts.get(vuln.severity, 0) + 1
    
    severity_summary = " | ".join([
        f"{'🔴' if s == 'critical' else '🟠' if s == 'high' else '🟡' if s == 'medium' else '⚪'} {s.capitalize()}: {c}"
        for s, c in sorted(severity_counts.items(), key=lambda x: ['critical', 'high', 'medium', 'low'].index(x[0]) if x[0] in ['critical', 'high', 'medium', 'low'] else 4)
    ])
    
    summary = f"""## 🔒 InspectAI Security Scan

**Triggered by:** @{comment_author}
**Files Scanned:** {files_scanned}
**Vulnerabilities Found:** {len(all_vulnerabilities)}
**Risk Score:** {risk_emoji} {risk_score:.1f}/10

{severity_summary if severity_summary else "✅ No security vulnerabilities found in changed code!"}

{f"I've added **{len(inline_comments)} inline comments** on potential security issues." if inline_comments else ""}
"""
    
    if files_failed > 0:
        summary += f"\n⚠️ **Note:** {files_failed} file(s) could not be scanned.\n"
    
    summary += "\n---\n*Use `/inspectai_review` for code review or `/inspectai_bugs` for bug detection.*\n"
    
    # Apply feedback filtering
    feedback_system = get_feedback_system()
    if inline_comments:
        comments_for_feedback = [{"description": c.get("body", ""), "category": "Security", "severity": c.get("severity", "high"), "confidence": 0.8} for c in inline_comments]
        filtered_comments_data = await feedback_system.filter_by_feedback(comments_for_feedback, repo_full_name)
        filtered_count = len(inline_comments) - len(filtered_comments_data)
        if filtered_count > 0:
            logger.info(f"[SECURITY] Feedback filtered {filtered_count} comments")
            inline_comments = inline_comments[:len(filtered_comments_data)]
    
    if inline_comments:
        merged_comments = _merge_inline_comments(inline_comments)
        try:
            github_client.create_review(
                repo_url=repo_full_name,
                pr_number=pr_number,
                body=summary,
                event="COMMENT",
                comments=merged_comments[:50]
            )
            
            # Store comments WITHOUT embeddings (lazy generation when feedback arrives)
            for comment in merged_comments[:50]:
                try:
                    await feedback_system.store_comment(
                        repo_full_name=repo_full_name,
                        pr_number=pr_number,
                        file_path=comment.get("path", ""),
                        line_number=comment.get("line", 0),
                        comment_body=comment.get("body", ""),
                        category="Security",
                        severity=comment.get("severity", "high"),
                        command_type="security",
                        generate_embedding=False  # Lazy - generated when feedback arrives
                    )
                except Exception as e:
                    logger.debug(f"[SECURITY] Failed to store comment for feedback: {e}")
            
            return {"status": "success", "vulnerabilities_found": len(all_vulnerabilities), "risk_score": risk_score}
        except Exception as e:
            logger.error(f"[SECURITY] Failed to post review: {e}")
            github_client.post_pr_comment(repo_full_name, pr_number, summary)
            return {"status": "partial", "vulnerabilities_found": len(all_vulnerabilities), "error": str(e)}
    else:
        github_client.post_pr_comment(repo_full_name, pr_number, summary)
        return {"status": "success", "vulnerabilities_found": 0, "risk_score": 0}


async def _handle_tests_command(
    github_client: GitHubClient,
    orchestrator,
    pr_memory,
    repo_full_name: str,
    pr_number: int,
    pr,
    comment_author: str
) -> Dict[str, Any]:
    """Handle /inspectai_tests - Generate unit tests for changed code.
    
    Uses TestGenerationAgent to create pytest/unittest tests.
    Features:
    - Parallel processing of multiple files
    - Generates tests ONLY for changed code (not entire files)
    - Skips files > 500 lines to avoid timeouts
    """
    logger.info(f"[TESTS] Starting test generation for {repo_full_name}#{pr_number}")
    
    # Configuration
    MAX_FILE_LINES = 500  # Skip files larger than this
    MAX_WORKERS = 3  # Process up to 3 files in parallel
    
    generated_tests = []
    files_processed = 0
    files_failed = 0
    files_skipped = []
    
    try:
        # Collect files to process
        files_to_process = []
        for pr_file in pr.files:
            if pr_file.status == "removed":
                continue
            
            if not orchestrator._is_code_file(pr_file.filename):
                continue
            
            # Focus on Python files for now
            if not pr_file.filename.endswith('.py'):
                continue
            
            files_to_process.append(pr_file)
        
        if not files_to_process:
            summary = f"""## 🧪 InspectAI Test Generation

**Triggered by:** @{comment_author}

ℹ️ No Python files found in this PR to generate tests for.
"""
            github_client.post_pr_comment(repo_full_name, pr_number, summary)
            return {"status": "success", "tests_generated": 0}
        
        logger.info(f"[TESTS] Found {len(files_to_process)} Python files to process")
        
        # Function to process a single file
        def process_single_file(pr_file):
            try:
                content = github_client.get_pr_file_content(repo_full_name, pr_number, pr_file.filename)
                diff_patch = pr_file.patch if hasattr(pr_file, 'patch') else ""
                
                # Check file size (count lines)
                line_count = content.count('\n') + 1
                if line_count > MAX_FILE_LINES:
                    logger.info(f"[TESTS] Skipping {pr_file.filename} ({line_count} lines > {MAX_FILE_LINES} limit)")
                    return {
                        "status": "skipped",
                        "file": pr_file.filename,
                        "reason": f"File too large ({line_count} lines)"
                    }
                
                logger.info(f"[TESTS] Generating tests for {pr_file.filename} ({line_count} lines)")
                
                # Run test generation - now uses diff to generate tests only for changes
                test_result = orchestrator._safe_execute_agent("test_generation", {
                    "code": content,
                    "framework": "pytest",
                    "coverage_focus": ["happy_path", "edge_cases", "error_handling"],
                    "diff_context": diff_patch  # Agent will use this to focus on changed code only
                })
                
                if test_result.get("status") == "error":
                    return {
                        "status": "error",
                        "file": pr_file.filename,
                        "error": test_result.get('error_message', 'Unknown error')
                    }
                
                test_code = test_result.get("test_code", "")
                if test_code:
                    return {
                        "status": "success",
                        "file": pr_file.filename,
                        "test_file": f"test_{pr_file.filename.split('/')[-1]}",
                        "test_code": test_code,
                        "descriptions": test_result.get("test_descriptions", [])
                    }
                else:
                    return {
                        "status": "empty",
                        "file": pr_file.filename,
                        "reason": "No tests generated"
                    }
                    
            except Exception as e:
                logger.error(f"[TESTS] Failed to process {pr_file.filename}: {e}", exc_info=True)
                return {
                    "status": "error",
                    "file": pr_file.filename,
                    "error": str(e)
                }
        
        # Process files in parallel using ThreadPoolExecutor
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        logger.info(f"[TESTS] Processing {len(files_to_process)} files with {MAX_WORKERS} workers")
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_file = {
                executor.submit(process_single_file, pr_file): pr_file 
                for pr_file in files_to_process
            }
            
            for future in as_completed(future_to_file):
                result = future.result()
                
                if result["status"] == "success":
                    generated_tests.append(result)
                    files_processed += 1
                    logger.info(f"[TESTS] ✓ Generated tests for {result['file']}")
                elif result["status"] == "skipped":
                    files_skipped.append(result)
                    logger.info(f"[TESTS] ⏭ Skipped {result['file']}: {result['reason']}")
                elif result["status"] == "empty":
                    files_processed += 1
                    logger.info(f"[TESTS] ○ No tests for {result['file']}")
                else:  # error
                    files_failed += 1
                    logger.warning(f"[TESTS] ✗ Failed {result['file']}: {result.get('error', 'Unknown')}")
        
        # Build summary comment
        summary = f"""## 🧪 InspectAI Test Generation

**Triggered by:** @{comment_author}
**Files Processed:** {files_processed}
**Test Files Generated:** {len(generated_tests)}

"""
        
        if files_skipped:
            summary += f"⏭️ **Skipped {len(files_skipped)} large file(s)** (>{MAX_FILE_LINES} lines):\n"
            for skipped in files_skipped:
                summary += f"- `{skipped['file']}` - {skipped['reason']}\n"
            summary += "\n"
        
        if generated_tests:
            summary += "### Generated Tests\n\n"
            summary += "ℹ️ *Tests generated for **changed code only** (not entire files)*\n\n"
            for test in generated_tests:
                summary += f"<details>\n<summary>📝 <code>{test['test_file']}</code> (for {test['file']})</summary>\n\n"
                summary += f"```python\n{test['test_code'][:3000]}\n```\n"
                if len(test['test_code']) > 3000:
                    summary += f"\n*... truncated (full file is {len(test['test_code'])} chars)*\n"
                summary += "\n</details>\n\n"
        else:
            summary += "ℹ️ No tests could be generated. This might be because:\n"
            summary += "- No testable functions were added/modified\n"
            summary += "- The changes were too small (e.g., import changes)\n"
        
        if files_failed > 0:
            summary += f"\n⚠️ **Note:** {files_failed} file(s) failed to process.\n"
        
        summary += "\n---\n*Tests generated for changed code only. Copy to your test directory and run `pytest`.*\n"
        
        logger.info(f"[TESTS] Posting summary comment to PR #{pr_number}")
        github_client.post_pr_comment(repo_full_name, pr_number, summary)
        logger.info(f"[TESTS] Successfully posted test generation results")
        return {"status": "success", "tests_generated": len(generated_tests)}
        
    except Exception as e:
        logger.error(f"[TESTS] Unhandled error in test generation: {e}", exc_info=True)
        # Try to post error message to PR
        try:
            error_msg = f"""## 🧪 InspectAI Test Generation

**Triggered by:** @{comment_author}

❌ **Error:** Test generation failed due to an unexpected error.

```
{str(e)[:500]}
```

Please try again or report this issue.
"""
            github_client.post_pr_comment(repo_full_name, pr_number, error_msg)
        except Exception as post_error:
            logger.error(f"[TESTS] Failed to post error message: {post_error}")
        
        return {"status": "error", "error": str(e)}


async def _handle_docs_command(
    github_client: GitHubClient,
    orchestrator,
    pr_memory,
    repo_full_name: str,
    pr_number: int,
    pr,
    comment_author: str
) -> Dict[str, Any]:
    """Handle /inspectai_docs - Generate/update documentation for changed code.
    
    Uses DocumentationAgent to create docstrings and documentation.
    """
    logger.info(f"[DOCS] Starting documentation generation for {repo_full_name}#{pr_number}")
    
    documented_files = []
    files_processed = 0
    files_failed = 0
    
    for pr_file in pr.files:
        if pr_file.status == "removed":
            continue
        
        if not orchestrator._is_code_file(pr_file.filename):
            continue
        
        # Focus on Python files for now
        if not pr_file.filename.endswith('.py'):
            continue
        
        try:
            content = github_client.get_pr_file_content(repo_full_name, pr_number, pr_file.filename)
            
            logger.info(f"[DOCS] Generating docs for {pr_file.filename}")
            
            # Run documentation generation
            doc_result = orchestrator._safe_execute_agent("documentation", {
                "code": content,
                "doc_type": "docstring",
                "style": "google"
            })
            
            if doc_result.get("status") == "error":
                logger.warning(f"[DOCS] Generation failed for {pr_file.filename}: {doc_result.get('error_message')}")
                files_failed += 1
                continue
            
            documented_code = doc_result.get("documented_code", "")
            if documented_code and documented_code != content:
                documented_files.append({
                    "file": pr_file.filename,
                    "original": content,
                    "documented": documented_code,
                    "doc_type": "docstring"
                })
            
            files_processed += 1
            
        except Exception as e:
            logger.error(f"[DOCS] Failed to process {pr_file.filename}: {e}", exc_info=True)
            files_failed += 1
            continue
    
    # Build summary comment
    summary = f"""## 📚 InspectAI Documentation Generator

**Triggered by:** @{comment_author}
**Files Processed:** {files_processed}
**Files with New Documentation:** {len(documented_files)}

"""
    
    if documented_files:
        summary += "### Updated Files with Docstrings\n\n"
        for doc in documented_files:
            summary += f"<details>\n<summary>📝 <code>{doc['file']}</code></summary>\n\n"
            summary += f"```python\n{doc['documented'][:4000]}\n```\n"
            if len(doc['documented']) > 4000:
                summary += f"\n*... truncated (full file is {len(doc['documented'])} chars)*\n"
            summary += "\n</details>\n\n"
    else:
        summary += "ℹ️ No documentation updates needed. The changed files either:\n"
        summary += "- Already have comprehensive docstrings\n"
        summary += "- Are not Python files (only Python supported currently)\n"
    
    if files_failed > 0:
        summary += f"\n⚠️ **Note:** {files_failed} file(s) could not be processed.\n"
    
    summary += "\n---\n*Review the generated docstrings and apply them to your codebase.*\n"
    
    github_client.post_pr_comment(repo_full_name, pr_number, summary)
    return {"status": "success", "files_documented": len(documented_files)}


async def _handle_help_command(
    github_client: GitHubClient,
    repo_full_name: str,
    pr_number: int,
    comment_author: str
) -> Dict[str, Any]:
    """Handle /inspectai_help - Show available commands."""
    logger.info(f"[HELP] Showing help for {repo_full_name}#{pr_number}")
    
    help_message = f"""## 🤖 InspectAI Commands

**Triggered by:** @{comment_author}

### Available Commands

| Command | Description |
|---------|-------------|
| `/inspectai_review` | **Quick Review** - Reviews ONLY the changed lines in your PR. Posts inline comments on issues introduced by your changes. Fast and focused. |
| `/inspectai_bugs` | **Deep Bug Scan** - Analyzes entire files (not just diffs) for potential bugs, logic errors, and edge cases. More thorough but slower. |
| `/inspectai_refactor` | **Refactor Suggestions** - Suggests code improvements for readability, performance, and maintainability. |
| `/inspectai_security` | **Security Audit** - Scans for security vulnerabilities using 4 specialized sub-agents: Injection, Auth, Data Exposure, Dependencies. |
| `/inspectai_tests` | **Test Generation** - Generates unit tests for your changed code. |
| `/inspectai_docs` | **Documentation** - Generates/updates docstrings for changed Python files using Google-style format. |
| `/inspectai_help` | **Help** - Shows this message. |

### Tips

- 🚀 **Start with** `/inspectai_review` for quick feedback on your changes
- 🐛 **Use** `/inspectai_bugs` when you want a deeper analysis of edge cases
- 🔐 **Run** `/inspectai_security` before merging code that handles user input or authentication
- ✅ **Generate tests** with `/inspectai_tests` to improve coverage

### Feedback

React with 👍 or 👎 on any InspectAI comment to help improve future reviews!

---
*InspectAI - Your AI Code Review Assistant*
"""
    
    github_client.post_pr_comment(repo_full_name, pr_number, help_message)
    return {"status": "success", "command": "help"}


# ============================================
# Hidden Developer Commands
# ============================================

async def _handle_reindex_command(
    github_client: GitHubClient,
    repo_full_name: str,
    pr_number: int,
    comment_author: str,
    installation_id: int
) -> Dict[str, Any]:
    """Handle /inspectai_reindex - Manually trigger codebase reindexing.
    
    This is a hidden developer command that triggers a full reindex
    of the repository's codebase. Useful when:
    - Scheduled reindexing job hasn't run yet
    - Major code changes need immediate indexing
    - Debugging indexing issues
    
    The command runs asynchronously - it returns immediately and
    indexing happens in the background.
    """
    logger.info(f"[REINDEX] Manual reindex triggered by {comment_author} for {repo_full_name}")
    
    try:
        # Get scheduled reindexer
        scheduled_reindexer = get_scheduled_reindexer()
        
        # Start reindexing
        result = await scheduled_reindexer.reindex_single_repository(
            repo_full_name=repo_full_name,
            installation_id=installation_id
        )
        
        if result.get("status") == "started":
            message = f"""## 🔄 Codebase Reindexing Started

**Triggered by:** @{comment_author}
**Repository:** `{repo_full_name}`
**Job ID:** `{result.get('job_id', 'N/A')}`

The codebase is being reindexed in the background. This includes:
- 📁 Parsing all code files (Python, Java, C++, JS, etc.)
- 🔗 Extracting function/class definitions and call graphs
- 📊 Storing in vector database for semantic search
- 🎯 Updating impact analysis data

**Note:** Indexing may take a few minutes for large repositories.
The next `/inspectai_review` or `/inspectai_bugs` will use the updated index.

---
*InspectAI - Developer Command*
"""
        else:
            message = f"""## ⚠️ Reindexing Failed

**Triggered by:** @{comment_author}
**Repository:** `{repo_full_name}`
**Error:** {result.get('message', 'Unknown error')}

Please check:
1. The bot has `Contents: Read` permission for this repository
2. Supabase is configured and accessible
3. Check server logs for more details

---
*InspectAI - Developer Command*
"""
        
        github_client.post_pr_comment(repo_full_name, pr_number, message)
        return {"status": result.get("status"), "command": "reindex", "job_id": result.get("job_id")}
        
    except Exception as e:
        logger.error(f"[REINDEX] Error handling reindex command: {e}", exc_info=True)
        error_message = f"""## ❌ Reindex Command Error

**Triggered by:** @{comment_author}
**Error:** {str(e)}

Please try again or check server logs.

---
*InspectAI - Developer Command*
"""
        github_client.post_pr_comment(repo_full_name, pr_number, error_message)
        return {"status": "error", "command": "reindex", "error": str(e)}


async def _handle_status_command(
    github_client: GitHubClient,
    repo_full_name: str,
    pr_number: int,
    comment_author: str
) -> Dict[str, Any]:
    """Handle /inspectai_status - Show system status and indexing info.
    
    This is a hidden developer command that shows:
    - Repository indexing status
    - Scheduled reindexer status
    - Last indexed timestamp
    - System health information
    """
    logger.info(f"[STATUS] Status check triggered by {comment_author} for {repo_full_name}")
    
    try:
        from ..indexer import get_codebase_indexer, get_background_indexer
        
        indexer = get_codebase_indexer()
        background_indexer = get_background_indexer()
        scheduled_reindexer = get_scheduled_reindexer()
        
        # Get project info
        project_info = None
        if indexer.client:
            project_info = await indexer.get_project(repo_full_name)
        
        # Get scheduler status
        scheduler_status = scheduled_reindexer.get_status()
        
        # Get current indexing status
        indexing_status = background_indexer.get_job_status(repo_full_name)
        
        # Format status message
        if project_info:
            last_indexed = project_info.get("last_indexed_at", "Never")
            total_files = project_info.get("total_files", 0)
            total_symbols = project_info.get("total_symbols", 0)
            status = project_info.get("indexing_status", "unknown")
            
            project_section = f"""### 📊 Repository Index Status
| Metric | Value |
|--------|-------|
| **Status** | `{status}` |
| **Last Indexed** | `{last_indexed}` |
| **Indexed Files** | {total_files} |
| **Indexed Symbols** | {total_symbols} |
| **Current Activity** | `{indexing_status}` |
"""
        else:
            project_section = """### 📊 Repository Index Status
⚠️ Repository not yet indexed or Supabase not configured.
"""
        
        scheduler_section = f"""### ⏰ Scheduled Reindexer
| Setting | Value |
|---------|-------|
| **Active** | {'✅ Yes' if scheduler_status.get('scheduler_active') else '❌ No'} |
| **Interval** | Every {scheduler_status.get('interval_days', 7)} days |
| **Last Run** | `{scheduler_status.get('last_run', 'Never')}` |
"""
        
        message = f"""## 📈 InspectAI System Status

**Triggered by:** @{comment_author}
**Repository:** `{repo_full_name}`

{project_section}

{scheduler_section}

### 💡 Developer Commands
| Command | Description |
|---------|-------------|
| `/inspectai_reindex` | Manually trigger codebase reindexing |
| `/inspectai_status` | Show this status page |

---
*InspectAI - Developer Command*
"""
        
        github_client.post_pr_comment(repo_full_name, pr_number, message)
        return {"status": "success", "command": "status"}
        
    except Exception as e:
        logger.error(f"[STATUS] Error handling status command: {e}", exc_info=True)
        error_message = f"""## ❌ Status Command Error

**Triggered by:** @{comment_author}
**Error:** {str(e)}

---
*InspectAI - Developer Command*
"""
        github_client.post_pr_comment(repo_full_name, pr_number, error_message)
        return {"status": "error", "command": "status", "error": str(e)}


def _format_security_comment(finding: BugFinding) -> str:
    """Format a security finding as an inline comment."""
    sev_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}.get(finding.severity, "⚪")
    
    comment = f"{sev_icon} **{finding.category}** ({finding.severity})\n\n{finding.description}"
    if finding.fix_suggestion:
        comment += f"\n\n**Remediation:** {finding.fix_suggestion}"
    return comment


def _calculate_security_risk_score(vulnerabilities: List[BugFinding]) -> float:
    """Calculate security risk score from 0-10."""
    if not vulnerabilities:
        return 0.0
    
    severity_weights = {"critical": 10.0, "high": 7.0, "medium": 4.0, "low": 1.0}
    total_score = sum(severity_weights.get(v.severity, 1.0) * v.confidence for v in vulnerabilities)
    max_score = len(vulnerabilities) * 10
    return min(10.0, (total_score / max_score) * 10) if max_score > 0 else 0.0


def _format_inline_comment(finding: Dict[str, Any]) -> str:
    """Format a finding as an inline comment."""
    severity = finding.get("severity", "medium")
    sev_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}.get(severity, "⚪")
    
    category = finding.get("category", "Issue")
    description = finding.get("description", "")
    fix = finding.get("fix_suggestion") or finding.get("fix", "")
    
    comment = f"{sev_icon} **{category}** ({severity}): {description}"
    if fix:
        comment += f"\n**Fix:** {fix}"
    return comment


def _format_bug_comment(bug: BugFinding) -> str:
    """Format a BugFinding as an inline comment."""
    sev_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}.get(bug.severity, "⚪")
    
    comment = f"{sev_icon} **{bug.category}** ({bug.severity}): {bug.description}"
    if bug.fix_suggestion:
        comment += f"\n**Fix:** {bug.fix_suggestion}"
    if bug.code_snippet:
        comment += f"\n```python\n{bug.code_snippet}\n```"
    return comment


def _merge_inline_comments(comments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge multiple comments on the same file+line into a single comment.
    
    GitHub doesn't allow multiple review comments on the same line,
    so we combine them into one.
    """
    if not comments:
        return []
    
    # Group by (path, line)
    grouped: Dict[tuple, List[str]] = {}
    comment_meta: Dict[tuple, Dict] = {}
    
    for comment in comments:
        key = (comment["path"], comment["line"])
        if key not in grouped:
            grouped[key] = []
            comment_meta[key] = {
                "path": comment["path"],
                "line": comment["line"],
                "side": comment.get("side", "RIGHT")
            }
        grouped[key].append(comment["body"])
    
    # Merge bodies
    merged = []
    for key, bodies in grouped.items():
        if len(bodies) == 1:
            merged_body = bodies[0]
        else:
            # Combine multiple findings with separators
            merged_body = "\n\n---\n\n".join(bodies)
        
        merged.append({
            **comment_meta[key],
            "body": merged_body
        })
    
    return merged


def _extract_code_snippet(content: str, line_number: int, context: int = 2) -> str:
    """Extract code snippet around a line number."""
    lines = content.split('\n')
    start = max(0, line_number - context - 1)
    end = min(len(lines), line_number + context)
    return '\n'.join(lines[start:end])


def _format_findings_message(
    command: str,
    comment_author: str,
    pr_number: int,
    repo_full_name: str,
    findings: list,
    files_analyzed: int
) -> str:
    """Format findings into GitHub comment.
    
    Args:
        command: Command type (review, bugs, refactor)
        comment_author: Comment author
        pr_number: PR number
        repo_full_name: Repository name
        findings: List of finding dicts
        files_analyzed: Number of files analyzed
        
    Returns:
        Formatted markdown comment
    """
    # Command metadata
    command_info = {
        "review": ("🔍", "Code Review", "Comprehensive review using 12 specialized agents"),
        "bugs": ("🐛", "Bug Detection", "Bug analysis using 4 specialized detectors"),
        "refactor": ("♻️", "Code Improvement", "Refactoring suggestions using 4 code review agents")
    }
    
    emoji, title, description = command_info.get(command, ("❓", "Analysis", "Code analysis"))
    
    # Header
    message_parts = [f"""{emoji} **{title}** - Analysis Complete

> {description}

**Triggered by:** @{comment_author}
**Command:** `/InspectAI_{command}`
**Files Analyzed:** {files_analyzed}

---
"""]
    
    if not findings:
        message_parts.append("✅ **No issues found!** Code looks good.\n")
    else:
        # Group by severity
        by_severity = {}
        for f in findings:
            sev = f.get("severity", "medium")
            by_severity.setdefault(sev, []).append(f)
        
        # Stats
        message_parts.append(f"### 📊 Summary\n\n")
        message_parts.append(f"**Total Findings:** {len(findings)}\n\n")
        
        for sev in ["critical", "high", "medium", "low"]:
            if sev in by_severity:
                icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}.get(sev, "⚪")
                message_parts.append(f"{icon} **{sev.capitalize()}**: {len(by_severity[sev])}\n")
        
        message_parts.append("\n---\n\n")
       
        # Top findings (limit to 10)
        message_parts.append("### 🔍 Top Findings\n\n")
        
        for i, finding in enumerate(findings[:10], 1):
            category = finding.get("category", "Issue")
            severity = finding.get("severity", "medium")
            description = finding.get("description", "")
            fix = finding.get("fix_suggestion") or finding.get("fix") or finding.get("remediation", "")
            file = finding.get("file", "unknown")
            location = finding.get("location", "")
            
            sev_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}.get(severity, "⚪")
            
            message_parts.append(f"**{i}. [{sev_icon} {severity.upper()}] {category}** - `{file}`\n")
            message_parts.append(f"   - {description}\n")
            if location:
                message_parts.append(f"   - Location: {location}\n")
            if fix:
                message_parts.append(f"   - **Fix:** {fix}\n")
        
        if len(findings) > 10:
            message_parts.append(f"\n*... and {len(findings) - 10} more findings*\n")
    
    message_parts.append("\n---\n")
    message_parts.append("⚡ *Powered by InspectAI*\n\n")
    message_parts.append("💡 **Available Commands:**\n")
    message_parts.append("- `/inspectai_review` - Review diff changes with inline comments\n")
    message_parts.append("- `/inspectai_bugs` - Deep bug detection scan\n")
    message_parts.append("- `/inspectai_refactor` - Code improvement suggestions\n")
    message_parts.append("- `/inspectai_security` - Security vulnerability scan\n")
    message_parts.append("- `/inspectai_tests` - Generate unit tests for changes\n")
    message_parts.append("- `/inspectai_docs` - Generate documentation/docstrings\n")
    
    return "".join(message_parts)


@router.post("/github")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    """Handle incoming GitHub webhook events.
    
    Supported events:
    - pull_request: opened, synchronize, reopened
    - push: (optional, for branch updates)
    - ping: GitHub connectivity test
    """
    # Get headers
    event_type = request.headers.get("X-GitHub-Event", "")
    delivery_id = request.headers.get("X-GitHub-Delivery", "")
    signature = request.headers.get("X-Hub-Signature-256", "")
    
    # Get raw body for signature verification
    body = await request.body()
    
    # Verify signature (if secret is configured and not placeholder)
    webhook_secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    if webhook_secret and webhook_secret not in ["", "your_webhook_secret_here"]:
        if not verify_signature(body, signature, webhook_secret):
            logger.warning(f"Invalid webhook signature for delivery {delivery_id}")
            raise HTTPException(status_code=401, detail="Invalid signature")
    else:
        logger.warning("Webhook signature verification SKIPPED - no secret configured")
    
    # Parse payload
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    
    # Check for duplicate delivery
    if is_duplicate_event(delivery_id):
        logger.info(f"Duplicate event {delivery_id}, skipping")
        return {"status": "duplicate", "message": "Event already processed"}
    
    logger.info(f"Received {event_type} event (delivery: {delivery_id})")
    
    # Handle ping event (GitHub sends this when webhook is first configured)
    if event_type == "ping":
        return {
            "status": "ok",
            "message": "Pong! Webhook configured successfully.",
            "zen": payload.get("zen", ""),
            "hook_id": payload.get("hook_id")
        }
    
    # Handle installation events (GitHub App installed/uninstalled)
    if event_type == "installation":
        action = payload.get("action", "")
        installation = payload.get("installation", {})
        installation_id = installation.get("id")
        repositories = payload.get("repositories", [])
        
        if action == "created":
            logger.info(f"GitHub App installed (installation: {installation_id})")
            
            # Start background indexing for all repositories
            for repo in repositories:
                repo_full_name = repo.get("full_name")
                if repo_full_name:
                    logger.info(f"Triggering codebase indexing for {repo_full_name}")
                    background_tasks.add_task(
                        _trigger_background_indexing,
                        repo_full_name,
                        installation_id
                    )
            
            return {
                "status": "ok",
                "message": f"Installation created. Indexing {len(repositories)} repositories.",
                "installation_id": installation_id
            }
        
        elif action == "deleted":
            logger.info(f"GitHub App uninstalled (installation: {installation_id})")
            return {"status": "ok", "message": "Installation deleted"}
        
        return {"status": "ok", "message": f"Installation action '{action}' received"}
    
    # Handle installation_repositories events (repos added/removed from installation)
    if event_type == "installation_repositories":
        action = payload.get("action", "")
        installation_id = payload.get("installation", {}).get("id")
        
        if action == "added":
            repos_added = payload.get("repositories_added", [])
            for repo in repos_added:
                repo_full_name = repo.get("full_name")
                if repo_full_name:
                    logger.info(f"Repository added to installation: {repo_full_name}")
                    background_tasks.add_task(
                        _trigger_background_indexing,
                        repo_full_name,
                        installation_id
                    )
            
            return {
                "status": "ok",
                "message": f"Added {len(repos_added)} repositories. Indexing started."
            }
        
        return {"status": "ok", "message": f"Repository action '{action}' received"}
    
    # Handle pull_request events
    if event_type == "pull_request":
        action = payload.get("action", "")
        pr = payload.get("pull_request", {})
        repo = payload.get("repository", {})
        
        # Only process certain actions
        if action in ["opened", "synchronize", "reopened"]:
            pr_number = pr.get("number")
            repo_full_name = repo.get("full_name")
            installation_id = payload.get("installation", {}).get("id")
            
            logger.info(f"PR {action}: {repo_full_name}#{pr_number}")
            
            # Process review in background
            background_tasks.add_task(
                process_pr_review,
                repo_full_name,
                pr_number,
                action,
                installation_id
            )
            
            return {
                "status": "processing",
                "message": f"PR review started for {repo_full_name}#{pr_number}",
                "pr_number": pr_number,
                "action": action
            }
        else:
            return {
                "status": "ignored",
                "message": f"Action '{action}' not configured for processing"
            }
    
    # Handle issue_comment events (for /InspectAI commands)
    if event_type == "issue_comment":
        action = payload.get("action", "")
        comment = payload.get("comment", {})
        issue = payload.get("issue", {})
        repo = payload.get("repository", {})
        installation_id = payload.get("installation", {}).get("id")
        
        # Only process new comments on PRs
        if action == "created" and issue.get("pull_request"):
            comment_body = comment.get("body", "").strip().lower()
            comment_author = comment.get("user", {}).get("login", "unknown")
            comment_user_type = comment.get("user", {}).get("type", "User")
            pr_number = issue.get("number")
            repo_full_name = repo.get("full_name")
            
            # IMPORTANT: Ignore comments from bots (including our own bot) to prevent infinite loops
            if comment_user_type == "Bot":
                logger.info(f"Ignoring comment from bot: {comment_author}")
                return {
                    "status": "ignored",
                    "message": "Ignoring bot comments to prevent loops"
                }
            
            # Check for InspectAI commands
            command = None
            if "/inspectai_review" in comment_body:
                command = "review"
            elif "/inspectai_bugs" in comment_body:
                command = "bugs"
            elif "/inspectai_refactor" in comment_body:
                command = "refactor"
            elif "/inspectai_security" in comment_body:
                command = "security"
            elif "/inspectai_tests" in comment_body:
                command = "tests"
            elif "/inspectai_docs" in comment_body:
                command = "docs"
            elif "/inspectai_help" in comment_body:
                command = "help"
            # Hidden developer commands
            elif "/inspectai_reindex" in comment_body:
                command = "reindex"
            elif "/inspectai_status" in comment_body:
                command = "status"
            
            if command:
                logger.info(f"/InspectAI_{command} command detected on {repo_full_name}#{pr_number} by {comment_author}")
                
                # Handle command in background
                background_tasks.add_task(
                    handle_agent_command,
                    repo_full_name,
                    pr_number,
                    comment_author,
                    command,
                    installation_id
                )
                
                return {
                    "status": "processing",
                    "message": f"InspectAI {command} command received for {repo_full_name}#{pr_number}",
                    "pr_number": pr_number,
                    "command": command,
                    "triggered_by": comment_author
                }
            else:
                return {
                    "status": "ignored",
                    "message": "Comment does not contain a recognized command"
                }
        else:
            return {
                "status": "ignored",
                "message": "Not a new comment on a PR"
            }
    
    # Handle pull_request_review_comment events (for written feedback on bot comments)
    if event_type == "pull_request_review_comment":
        action = payload.get("action")
        comment = payload.get("comment", {})
        
        logger.info(f"[FEEDBACK-DEBUG] Received pull_request_review_comment event, action={action}")
        
        # Only process new comments that are replies
        if action == "created":
            in_reply_to_id = comment.get("in_reply_to_id")
            comment_body = comment.get("body", "")
            commenter = comment.get("user", {}).get("login", "")
            repo = payload.get("repository", {})
            repo_full_name = repo.get("full_name", "unknown/unknown")
            
            logger.info(
                f"[FEEDBACK-DEBUG] Comment details: "
                f"in_reply_to_id={in_reply_to_id}, "
                f"commenter={commenter}, "
                f"body='{comment_body[:100]}...'"
            )
            pull_request = payload.get("pull_request", {})
            pr_number = pull_request.get("number", 0)
            
            # Get file and line info from the comment
            file_path = comment.get("path", "")
            line_number = comment.get("line") or comment.get("original_line", 0)
            
            # Check if this is a reply to another comment (potential feedback)
            if in_reply_to_id:
                logger.info(
                    f"[FEEDBACK] Reply detected from {commenter} to comment {in_reply_to_id} "
                    f"in {repo_full_name}: '{comment_body[:50]}...'"
                )
                
                # Try to fetch the original comment to get its body
                # We need to use GitHub API to get the original comment
                original_comment_body = None
                try:
                    # Initialize GitHub client for fetching original comment
                    github_client = GitHubClient()
                    logger.info(f"[FEEDBACK-DEBUG] Fetching original comment {in_reply_to_id} from {repo_full_name}")
                    original_comment = github_client.get_pr_review_comment(
                        repo_full_name, in_reply_to_id
                    )
                    if original_comment:
                        original_comment_body = original_comment.get("body", "")
                        logger.info(f"[FEEDBACK-DEBUG] Original comment body (first 100 chars): {original_comment_body[:100] if original_comment_body else 'None'}...")
                        # Check if it's our bot's comment (contains InspectAI markers)
                        # InspectAI comments use severity emojis: 🔴 (critical), 🟠 (high), 🟡 (medium), 🟢 (low), 🔵 (info)
                        # Or contain "inspectai" or common InspectAI patterns
                        inspectai_markers = [
                            "inspectai",  # Brand name
                            "🔍",  # Search/analysis emoji
                            "🔴",  # Critical severity
                            "🟠",  # High severity  
                            "🟡",  # Medium severity
                            "🟢",  # Low severity
                            "🔵",  # Info severity
                            "**Security:",  # Security findings
                            "**Bug:",  # Bug findings
                            "**Style:",  # Style findings
                            "**Performance:",  # Performance findings
                        ]
                        is_inspectai_comment = any(
                            marker in original_comment_body or marker.lower() in original_comment_body.lower()
                            for marker in inspectai_markers
                        )
                        if not is_inspectai_comment:
                            # Not our comment, ignore
                            logger.info(f"[FEEDBACK-DEBUG] Original comment is NOT an InspectAI comment, ignoring feedback")
                            return {
                                "status": "ignored",
                                "message": "Reply not to an InspectAI comment"
                            }
                        logger.info(f"[FEEDBACK-DEBUG] Original comment IS an InspectAI comment, proceeding to store feedback")
                    else:
                        logger.warning(f"[FEEDBACK-DEBUG] Could not fetch original comment {in_reply_to_id} - returned None")
                except Exception as e:
                    logger.warning(f"[FEEDBACK] Could not fetch original comment {in_reply_to_id}: {e}")
                    import traceback
                    logger.warning(f"[FEEDBACK-DEBUG] Traceback: {traceback.format_exc()}")
                
                # Try to store as written feedback
                try:
                    from src.feedback.feedback_system import get_feedback_system
                    feedback_system = get_feedback_system()
                    
                    logger.info(f"[FEEDBACK-DEBUG] Feedback system enabled: {feedback_system.enabled}")
                    
                    if feedback_system.enabled:
                        logger.info(f"[FEEDBACK-DEBUG] Calling store_written_feedback...")
                        success = await feedback_system.store_written_feedback(
                            github_comment_id=in_reply_to_id,
                            user_login=commenter,
                            explanation=comment_body,
                            original_comment_body=original_comment_body,
                            repo_full_name=repo_full_name,
                            pr_number=pr_number,
                            file_path=file_path,
                            line_number=line_number
                        )
                        
                        logger.info(f"[FEEDBACK-DEBUG] store_written_feedback returned: {success}")
                        
                        if success:
                            logger.info(
                                f"[FEEDBACK] Stored written feedback from {commenter} "
                                f"for comment {in_reply_to_id}"
                            )
                            return {
                                "status": "ok",
                                "message": "Written feedback recorded",
                                "in_reply_to": in_reply_to_id,
                                "user": commenter
                            }
                        else:
                            # Comment not from InspectAI, ignore
                            logger.info(f"[FEEDBACK-DEBUG] store_written_feedback returned False - feedback not stored")
                            return {
                                "status": "ignored",
                                "message": "Reply not to an InspectAI comment"
                            }
                    else:
                        logger.info(f"[FEEDBACK-DEBUG] Feedback system is NOT enabled, skipping")
                        return {
                            "status": "ignored",
                            "message": "Feedback system not enabled"
                        }
                except Exception as e:
                    logger.error(f"[FEEDBACK] Error processing written feedback: {e}")
                    import traceback
                    logger.error(f"[FEEDBACK-DEBUG] Traceback: {traceback.format_exc()}")
                    return {
                        "status": "error",
                        "message": f"Error processing feedback: {str(e)}"
                    }
            else:
                return {
                    "status": "ignored",
                    "message": "Not a reply comment"
                }
        else:
            return {
                "status": "ignored",
                "message": f"Action '{action}' not processed for review comments"
            }
    
    # Handle push events (optional - for tracking branch updates)
    if event_type == "push":
        repo = payload.get("repository", {})
        ref = payload.get("ref", "")
        pusher = payload.get("pusher", {}).get("name", "unknown")
        
        logger.info(f"Push to {repo.get('full_name')} ref {ref} by {pusher}")
        
        return {
            "status": "ok",
            "message": "Push event received",
            "ref": ref
        }
    
    # Handle other events
    return {
        "status": "ok",
        "message": f"Event '{event_type}' received but not processed"
    }


@router.get("/github/status")
async def webhook_status():
    """Check webhook handler status."""
    return {
        "status": "active",
        "processed_events": len(_processed_events),
        "supported_events": ["ping", "pull_request", "issue_comment", "pull_request_review_comment", "push"],
        "supported_pr_actions": ["opened", "synchronize", "reopened"],
        "supported_commands": [
            "/InspectAI_review - Code Reviewer Agent (logic, naming, security)",
            "/InspectAI_bugs - Bug Finder Agent (runtime errors, edge cases)",
            "/InspectAI_refactor - Refactor Agent (code improvements)"
        ],
        "feedback": {
            "reactions": "👍 (thumbs up) = helpful, 👎 (thumbs down) = not helpful",
            "written": "Reply to any InspectAI comment with your explanation"
        }
    }
