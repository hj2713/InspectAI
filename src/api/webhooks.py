"""GitHub Webhook Handler for automatic PR reviews.

This module handles incoming webhook events from GitHub, specifically:
- Pull Request opened/synchronized events
- Issue comments (for /review command)
- Push events (optional)

Commands:
- /inspectai_review: Reviews ONLY the changed lines in the PR diff
- /inspectai_bugs: Finds bugs in WHOLE files that have changes
- /inspectai_refactor: Code improvement suggestions (style, performance, etc.)
- /inspectai_fixbugs: Auto-fixes bugs found by /inspectai_bugs using memory

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
    location = finding.get("location", "")
    if not location:
        # Try to get from line_number field directly
        line_num = finding.get("line_number") or finding.get("line")
        if line_num:
            try:
                return int(line_num)
            except (ValueError, TypeError):
                pass
        return None
    
    # Try various patterns
    patterns = [
        r'line\s*(\d+)',
        r'L(\d+)',
        r':(\d+)',
        r'^(\d+)$'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, str(location), re.IGNORECASE)
        if match:
            return int(match.group(1))
    
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
                return await _handle_refactor_command(
                    github_client, orchestrator, pr_memory,
                    repo_full_name, pr_number, pr, comment_author
                )
            elif command == "fixbugs":
                return await _handle_fixbugs_command(
                    github_client, orchestrator, pr_memory,
                    repo_full_name, pr_number, pr, comment_author
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
    """
    logger.info(f"[REVIEW] Starting diff-only review for {repo_full_name}#{pr_number}")
    
    inline_comments = []
    files_reviewed = 0
    
    for pr_file in pr.files:
        if pr_file.status == "removed":
            continue
        
        if not orchestrator._is_code_file(pr_file.filename):
            continue
        
        try:
            # Get changed line ranges from diff
            changed_ranges = parse_diff_for_changed_lines(pr_file.patch)
            if not changed_ranges:
                logger.info(f"[REVIEW] No changed lines in {pr_file.filename}")
                continue
            
            # Get file content
            content = github_client.get_pr_file_content(repo_full_name, pr_number, pr_file.filename)
            lines = content.split('\n')
            
            # Extract only the changed portions for analysis
            changed_code_parts = []
            for start, end, _ in changed_ranges:
                snippet = '\n'.join(lines[max(0, start-1):min(len(lines), end+2)])
                changed_code_parts.append(f"# Lines {start}-{end}:\n{snippet}")
            
            changed_code = '\n\n'.join(changed_code_parts)
            
            logger.info(f"[REVIEW] Analyzing {len(changed_ranges)} changed regions in {pr_file.filename}")
            
            # Run analysis on changed code only
            analysis = orchestrator.agents["analysis"].process(changed_code)
            
            # Create inline comments for findings
            for suggestion in analysis.get("suggestions", []):
                if isinstance(suggestion, dict):
                    line_num = extract_line_number_from_finding(suggestion) or changed_ranges[0][0]
                    
                    # Ensure line is in valid range for this file's diff
                    valid_line = None
                    for start, end, _ in changed_ranges:
                        if start <= line_num <= end:
                            valid_line = line_num
                            break
                    
                    if valid_line is None:
                        valid_line = changed_ranges[0][0]
                    
                    comment_body = _format_inline_comment(suggestion)
                    inline_comments.append({
                        "path": pr_file.filename,
                        "line": valid_line,
                        "side": "RIGHT",
                        "body": comment_body
                    })
            
            files_reviewed += 1
            
            # Store review context in memory
            pr_memory.store_review_context(
                repo_full_name, pr_number, "review",
                f"Reviewed {pr_file.filename}: {len(analysis.get('suggestions', []))} suggestions",
                {"file": pr_file.filename, "command": "review"}
            )
            
        except Exception as e:
            logger.error(f"[REVIEW] Failed to analyze {pr_file.filename}: {e}", exc_info=True)
            continue
    
    # Post review with inline comments
    if inline_comments:
        summary = f"""## 🔍 InspectAI Code Review

**Triggered by:** @{comment_author}
**Files Reviewed:** {files_reviewed}
**Inline Comments:** {len(inline_comments)}

I've added inline comments on the specific lines that need attention.
Only the **changed lines** in this PR were reviewed.

---
*Use `/inspectai_bugs` to scan entire files for bugs.*
"""
        try:
            result = github_client.create_review(
                repo_url=repo_full_name,
                pr_number=pr_number,
                body=summary,
                event="COMMENT",
                comments=inline_comments
            )
            logger.info(f"[REVIEW] Posted review with {len(inline_comments)} inline comments")
            return {"status": "success", "review_id": result.get("id"), "comments": len(inline_comments)}
        except Exception as e:
            logger.error(f"[REVIEW] Failed to post review: {e}")
            # Fallback to regular comment
            github_client.post_pr_comment(repo_full_name, pr_number, summary)
            return {"status": "partial", "error": str(e), "comments": len(inline_comments)}
    else:
        # No issues found
        message = f"""## 🔍 InspectAI Code Review

**Triggered by:** @{comment_author}
**Files Reviewed:** {files_reviewed}

✅ **No issues found in the changed lines!**

The diff looks good. Only changed lines were reviewed.

---
*Use `/inspectai_bugs` to do a deeper scan of entire files.*
"""
        github_client.post_pr_comment(repo_full_name, pr_number, message)
        return {"status": "success", "comments": 0}


async def _handle_bugs_command(
    github_client: GitHubClient,
    orchestrator,
    pr_memory,
    repo_full_name: str,
    pr_number: int,
    pr,
    comment_author: str
) -> Dict[str, Any]:
    """Handle /inspectai_bugs - Scans WHOLE files for bugs.
    
    Stores findings in memory for later use by /inspectai_fixbugs.
    Posts inline comments on bug locations that are in the diff.
    """
    logger.info(f"[BUGS] Starting full file bug scan for {repo_full_name}#{pr_number}")
    
    all_bugs: List[BugFinding] = []
    inline_comments = []
    bugs_not_in_diff = []  # Bugs on lines not in the diff
    files_scanned = 0
    
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
            # Get FULL file content
            content = github_client.get_pr_file_content(repo_full_name, pr_number, pr_file.filename)
            logger.info(f"[BUGS] Scanning entire file: {pr_file.filename} ({len(content)} bytes)")
            
            diff_lines = diff_lines_by_file.get(pr_file.filename, set())
            
            # Run bug detection on entire file
            bugs_result = orchestrator.agents["bug_detection"].process(content)
            logger.info(f"[BUGS] Found {bugs_result.get('bug_count', 0)} bugs in {pr_file.filename}")
            
            # Also run security scan
            security_result = orchestrator.agents["security"].process(content)
            logger.info(f"[BUGS] Found {security_result.get('vulnerability_count', 0)} vulnerabilities in {pr_file.filename}")
            
            # Convert to BugFinding objects and store in memory
            for bug in bugs_result.get("bugs", []):
                if isinstance(bug, dict):
                    line_num = extract_line_number_from_finding(bug) or 1
                    
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
                    
                    # Only add inline comment if line is in the diff
                    if line_num in diff_lines:
                        inline_comments.append({
                            "path": pr_file.filename,
                            "line": line_num,
                            "side": "RIGHT",
                            "body": _format_bug_comment(finding)
                        })
                    else:
                        bugs_not_in_diff.append(finding)
            
            # Add security vulnerabilities as bugs too
            for vuln in security_result.get("vulnerabilities", []):
                if isinstance(vuln, dict):
                    line_num = extract_line_number_from_finding(vuln) or 1
                    
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
                    
                    if line_num in diff_lines:
                        inline_comments.append({
                            "path": pr_file.filename,
                            "line": line_num,
                            "side": "RIGHT",
                            "body": _format_bug_comment(finding)
                        })
                    else:
                        bugs_not_in_diff.append(finding)
            
            files_scanned += 1
            
        except Exception as e:
            logger.error(f"[BUGS] Failed to scan {pr_file.filename}: {e}", exc_info=True)
            continue
    
    # Store all bugs in memory for /inspectai_fixbugs to use
    if all_bugs:
        stored = pr_memory.store_bug_findings(repo_full_name, pr_number, all_bugs)
        logger.info(f"[BUGS] Stored {stored} bugs in memory for fixbugs")
    
    # Build severity summary
    severity_counts = {}
    for bug in all_bugs:
        severity_counts[bug.severity] = severity_counts.get(bug.severity, 0) + 1
    
    severity_summary = " | ".join([
        f"{'🔴' if s == 'critical' else '🟠' if s == 'high' else '🟡' if s == 'medium' else '⚪'} {s.capitalize()}: {c}"
        for s, c in sorted(severity_counts.items(), key=lambda x: ['critical', 'high', 'medium', 'low'].index(x[0]) if x[0] in ['critical', 'high', 'medium', 'low'] else 4)
    ])
    
    # Build list of bugs not in diff for the main comment
    bugs_not_in_diff_text = ""
    if bugs_not_in_diff:
        bugs_not_in_diff_text = "\n\n### 📋 Bugs Outside Changed Lines:\n"
        for bug in bugs_not_in_diff[:10]:  # Limit to 10
            sev_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}.get(bug.severity, "⚪")
            bugs_not_in_diff_text += f"\n- {sev_icon} **{bug.file_path}:{bug.line_number}** - {bug.category}: {bug.description[:100]}..."
        if len(bugs_not_in_diff) > 10:
            bugs_not_in_diff_text += f"\n- *...and {len(bugs_not_in_diff) - 10} more*"
    
    summary = f"""## 🐛 InspectAI Bug Detection

**Triggered by:** @{comment_author}
**Files Scanned:** {files_scanned}
**Bugs Found:** {len(all_bugs)}

{severity_summary if severity_summary else "✅ No bugs found!"}

{f"I've added **{len(inline_comments)} inline comments** on bugs in changed lines." if inline_comments else ""}
{bugs_not_in_diff_text}

---
{"💡 **Run `/inspectai_fixbugs` to auto-fix these bugs!**" if all_bugs else ""}
"""
    
    if inline_comments:
        try:
            result = github_client.create_review(
                repo_url=repo_full_name,
                pr_number=pr_number,
                body=summary,
                event="COMMENT",
                comments=inline_comments[:50]  # GitHub limits to 50 comments per review
            )
            return {"status": "success", "bugs_found": len(all_bugs), "comments": len(inline_comments)}
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
            
            # Run code analysis for refactoring suggestions
            analysis = orchestrator.agents["analysis"].process(content)
            
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

---
*Use `/inspectai_bugs` to detect bugs, then `/inspectai_fixbugs` to auto-fix them.*
"""
    
    if inline_comments:
        try:
            result = github_client.create_review(
                repo_url=repo_full_name,
                pr_number=pr_number,
                body=summary,
                event="COMMENT",
                comments=inline_comments[:50]
            )
            return {"status": "success", "suggestions": len(all_suggestions)}
        except Exception as e:
            logger.error(f"[REFACTOR] Failed to post review: {e}")
            github_client.post_pr_comment(repo_full_name, pr_number, summary)
            return {"status": "partial", "suggestions": len(all_suggestions), "error": str(e)}
    else:
        github_client.post_pr_comment(repo_full_name, pr_number, summary)
        return {"status": "success", "suggestions": 0}


async def _handle_fixbugs_command(
    github_client: GitHubClient,
    orchestrator,
    pr_memory,
    repo_full_name: str,
    pr_number: int,
    pr,
    comment_author: str
) -> Dict[str, Any]:
    """Handle /inspectai_fixbugs - Auto-fixes bugs and commits to PR.
    
    Reads bugs stored by /inspectai_bugs, generates fixes, and commits them.
    """
    logger.info(f"[FIXBUGS] Starting auto-fix for {repo_full_name}#{pr_number}")
    
    # Get unfixed bugs from memory
    unfixed_bugs = pr_memory.get_unfixed_bugs(repo_full_name, pr_number)
    
    if not unfixed_bugs:
        message = f"""## 🔧 InspectAI Fix Bugs

**Triggered by:** @{comment_author}

⚠️ **No bugs found to fix!**

Please run `/inspectai_bugs` first to detect bugs, then run `/inspectai_fixbugs` to fix them.
"""
        github_client.post_pr_comment(repo_full_name, pr_number, message)
        return {"status": "no_bugs", "message": "No bugs found"}
    
    logger.info(f"[FIXBUGS] Found {len(unfixed_bugs)} unfixed bugs in memory")
    
    # Group bugs by file
    bugs_by_file: Dict[str, List[BugFinding]] = {}
    for bug in unfixed_bugs:
        if bug.file_path not in bugs_by_file:
            bugs_by_file[bug.file_path] = []
        bugs_by_file[bug.file_path].append(bug)
    
    files_fixed = []
    files_failed = []
    
    for file_path, file_bugs in bugs_by_file.items():
        try:
            # Get current file content
            content = github_client.get_pr_file_content(repo_full_name, pr_number, file_path)
            
            # Build detailed fix prompt with all bug info
            bug_descriptions = "\n".join([
                f"""Bug {i} (Line {bug.line_number}, {bug.severity}):
- Category: {bug.category}
- Description: {bug.description}
- Suggested Fix: {bug.fix_suggestion}
- Code Snippet: {bug.code_snippet}"""
                for i, bug in enumerate(file_bugs, 1)
            ])
            
            # Use code generation agent to generate fixed code
            fix_prompt = {
                "code": content,
                "bugs": bug_descriptions,
                "suggestions": [b.fix_suggestion for b in file_bugs],
                "requirements": [
                    "Apply ALL the suggested fixes to the code",
                    "Return ONLY the complete fixed code, no explanations",
                    "Maintain the exact same structure and formatting",
                    "Do not change anything that is not related to the bugs"
                ]
            }
            
            fix_result = orchestrator.agents["generation"].process(fix_prompt)
            
            # Extract the fixed code
            fixed_code = fix_result.get("generated_code") or fix_result.get("raw_analysis", "")
            
            # Clean up the response - extract just the code
            if "```" in fixed_code:
                # Extract code from markdown code blocks
                import re
                code_blocks = re.findall(r'```(?:\w+)?\n(.*?)```', fixed_code, re.DOTALL)
                if code_blocks:
                    fixed_code = code_blocks[0]
            
            # Validate we have actual code
            if not fixed_code or len(fixed_code) < 10:
                logger.warning(f"[FIXBUGS] Generated code too short for {file_path}")
                files_failed.append({"file": file_path, "reason": "Generated code too short"})
                continue
            
            # Commit the fix to the PR
            commit_message = f"fix: Apply InspectAI bug fixes to {file_path}\n\nFixed {len(file_bugs)} bug(s):\n" + "\n".join(
                [f"- {b.category}: {b.description[:50]}..." for b in file_bugs]
            )
            
            github_client.update_file_in_pr(
                repo_url=repo_full_name,
                pr_number=pr_number,
                file_path=file_path,
                new_content=fixed_code,
                commit_message=commit_message
            )
            
            logger.info(f"[FIXBUGS] Committed fix for {file_path}")
            files_fixed.append({
                "file": file_path,
                "bugs_fixed": len(file_bugs)
            })
            
            # Mark bugs as fixed in memory
            pr_memory.mark_bugs_fixed(
                repo_full_name, pr_number, file_path,
                [b.line_number for b in file_bugs]
            )
            
        except Exception as e:
            logger.error(f"[FIXBUGS] Failed to fix {file_path}: {e}", exc_info=True)
            files_failed.append({"file": file_path, "reason": str(e)})
            continue
    
    # Post summary
    if files_fixed:
        total_bugs = sum(f["bugs_fixed"] for f in files_fixed)
        message_parts = [f"""## 🔧 InspectAI Fix Bugs - Fixes Committed!

**Triggered by:** @{comment_author}
**Files Fixed:** {len(files_fixed)}
**Total Bugs Fixed:** {total_bugs}

### ✅ Fixed Files:
"""]
        
        for fix in files_fixed:
            message_parts.append(f"- `{fix['file']}` - {fix['bugs_fixed']} bug(s) fixed\n")
        
        if files_failed:
            message_parts.append("\n### ⚠️ Failed Files:\n")
            for fail in files_failed:
                message_parts.append(f"- `{fail['file']}` - {fail['reason']}\n")
        
        message_parts.append("""
---
✨ **Fixes have been committed to this PR!**

Please review the changes and run your tests to verify the fixes.
""")
        
        message = "".join(message_parts)
        github_client.post_pr_comment(repo_full_name, pr_number, message)
        return {"status": "success", "files_fixed": len(files_fixed), "bugs_fixed": total_bugs}
    else:
        message = f"""## 🔧 InspectAI Fix Bugs

**Triggered by:** @{comment_author}

❌ **Failed to generate and commit fixes.**

{"### Failed Files:" + chr(10) + chr(10).join([f"- `{f['file']}`: {f['reason']}" for f in files_failed]) if files_failed else ""}

Please check the error messages and try again.
"""
        github_client.post_pr_comment(repo_full_name, pr_number, message)
        return {"status": "error", "message": "Failed to generate fixes"}


def _format_inline_comment(finding: Dict[str, Any]) -> str:
    """Format a finding as an inline comment."""
    severity = finding.get("severity", "medium")
    sev_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}.get(severity, "⚪")
    
    category = finding.get("category", "Issue")
    description = finding.get("description", "")
    fix = finding.get("fix_suggestion") or finding.get("fix", "")
    confidence = finding.get("confidence", 0.5)
    
    comment = f"""{sev_icon} **{category}** ({severity})

{description}
"""
    
    if fix:
        comment += f"""
**Suggested Fix:** {fix}
"""
    
    comment += f"""
*Confidence: {confidence:.0%}*
"""
    return comment


def _format_bug_comment(bug: BugFinding) -> str:
    """Format a BugFinding as an inline comment."""
    sev_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}.get(bug.severity, "⚪")
    
    comment = f"""{sev_icon} **{bug.category}** ({bug.severity})

{bug.description}
"""
    
    if bug.fix_suggestion:
        comment += f"""
**Suggested Fix:** {bug.fix_suggestion}
"""
    
    if bug.code_snippet:
        comment += f"""
```python
{bug.code_snippet}
```
"""
    
    comment += f"""
*Confidence: {bug.confidence:.0%}*
"""
    return comment


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
            confidence = finding.get("confidence", 0.0)
            
            sev_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}.get(severity, "⚪")
            
            message_parts.append(f"**{i}. [{sev_icon} {severity.upper()}] {category}** - `{file}`\n")
            message_parts.append(f"   - {description}\n")
            if location:
                message_parts.append(f"   - Location: {location}\n")
            if fix:
                message_parts.append(f"   - **Fix:** {fix}\n")
            message_parts.append(f"   - Confidence: {confidence:.0%}\n\n")
        
        if len(findings) > 10:
            message_parts.append(f"\n*... and {len(findings) - 10} more findings*\n")
    
    message_parts.append("\n---\n")
    message_parts.append("⚡ *Powered by InspectAI*\n\n")
    message_parts.append("💡 **Available Commands:**\n")
    message_parts.append("- `/InspectAI_review` - Review diff changes only\n")
    message_parts.append("- `/InspectAI_bugs` - Scan whole files for bugs\n")
    message_parts.append("- `/InspectAI_refactor` - Code improvement suggestions\n")
    message_parts.append("- `/InspectAI_fixbugs` - Auto-fix detected bugs\n")
    
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
        "supported_events": ["ping", "pull_request", "issue_comment", "push"],
        "supported_pr_actions": ["opened", "synchronize", "reopened"],
        "supported_commands": [
            "/InspectAI_review - Code Reviewer Agent (logic, naming, security)",
            "/InspectAI_bugs - Bug Finder Agent (runtime errors, edge cases)",
            "/InspectAI_refactor - Refactor Agent (code improvements)"
        ]
    }
