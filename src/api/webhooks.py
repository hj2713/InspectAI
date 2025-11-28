"""GitHub Webhook Handler for automatic PR reviews.

This module handles incoming webhook events from GitHub, specifically:
- Pull Request opened/synchronized events
- Issue comments (for /review command)
- Push events (optional)

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
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from pydantic import BaseModel

from ..utils.logger import get_logger
from ..github.client import GitHubClient

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
        provider = os.getenv("LLM_PROVIDER", "bytez")
        
        for key in config:
            if isinstance(config[key], dict):
                config[key]["provider"] = provider
                if provider == "bytez":
                    config[key]["model"] = "Qwen/Qwen3-0.6B"
        
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
    """Handle InspectAI agent commands.
    
    Args:
        repo_full_name: Full repository name (owner/repo)
        pr_number: Pull request number
        comment_author: Who triggered the command
        command: The command triggered (review, bugs, refactor)
        installation_id: GitHub App installation ID for authentication
        
    Returns:
        Result of posting comment
    """
    logger.info(f"Handling /InspectAI_{command} command for {repo_full_name}#{pr_number} by {comment_author}")
    
    try:
        # Initialize GitHub client with installation token (no user token needed!)
        if installation_id:
            github_client = GitHubClient.from_installation(installation_id)
            logger.info(f"Using GitHub App installation token for installation {installation_id}")
        else:
            # Fallback to env token (for testing)
            github_client = GitHubClient()
            logger.warning("No installation_id provided, using fallback token")
        
        # Agent-specific responses (dummy for now - will be replaced with real agent logic)
        if command == "review":
            emoji = "🔍"
            agent_name = "Code Reviewer Agent"
            description = "Analyzes code for incorrect logic, poor naming, and insecure code patterns"
            dummy_findings = """
### 📋 Code Review Findings (Demo)

#### ⚠️ Issues Found:

1. **Naming Convention** (Line 15)
   - Variable `x` should have a more descriptive name
   - Suggestion: Rename to `user_count` or similar

2. **Security Warning** (Line 42)
   - Potential SQL injection vulnerability detected
   - Suggestion: Use parameterized queries

3. **Code Style** (Line 78)
   - Function `doStuff()` is too long (150+ lines)
   - Suggestion: Break into smaller functions

#### ✅ Good Practices Observed:
- Proper error handling in API calls
- Consistent indentation
- Good use of type hints
"""

        elif command == "bugs":
            emoji = "🐛"
            agent_name = "Bug Finder Agent"
            description = "Simulates code execution to detect runtime errors and edge case bugs"
            dummy_findings = """
### 🐛 Bug Analysis Report (Demo)

#### 🚨 Potential Bugs Detected:

1. **Null Reference Error** (Line 23)
   - `user.name` accessed without null check
   - Could crash if `user` is undefined
   ```python
   # Fix suggestion:
   if user and user.name:
       print(user.name)
   ```

2. **Off-by-One Error** (Line 56)
   - Loop iterates `i <= len(arr)` instead of `i < len(arr)`
   - Will cause IndexError on last iteration

3. **Race Condition** (Line 89)
   - Shared resource accessed without lock
   - May cause data corruption in concurrent execution

#### 🧪 Edge Cases to Test:
- Empty input arrays
- Negative numbers
- Unicode characters in strings
"""

        elif command == "refactor":
            emoji = "♻️"
            agent_name = "Refactor Agent"
            description = "Suggests maintainable code improvements while preserving functionality"
            dummy_findings = """
### ♻️ Refactoring Suggestions (Demo)

#### 🔧 Recommended Improvements:

1. **Extract Method** (Lines 45-67)
   - Complex logic can be extracted into `calculate_discount()`
   - Improves readability and testability

2. **Replace Magic Numbers** (Line 12)
   - `if count > 100:` → `if count > MAX_RETRY_COUNT:`
   - Define constants for better maintainability

3. **Use List Comprehension** (Lines 78-82)
   ```python
   # Before:
   result = []
   for item in items:
       if item.active:
           result.append(item.name)
   
   # After:
   result = [item.name for item in items if item.active]
   ```

4. **Apply DRY Principle** (Lines 100, 145, 189)
   - Duplicate code found in 3 locations
   - Suggestion: Create shared utility function

#### 📊 Metrics:
- Cyclomatic Complexity: 15 → 8 (after refactoring)
- Lines of Code: 250 → 180
- Test Coverage Impact: +15%
"""
        else:
            emoji = "❓"
            agent_name = "Unknown Agent"
            description = "Unknown command"
            dummy_findings = "No analysis available for this command."
        
        # Build the response message
        message = f"""{emoji} **{agent_name}** - Analysis Complete

> {description}

**Triggered by:** @{comment_author}
**Command:** `/InspectAI_{command}`
**PR:** #{pr_number}
**Repository:** {repo_full_name}

---
{dummy_findings}

---
⚡ *This is a demo response. Real analysis coming soon!*

💡 **Available Commands:**
- `/InspectAI_review` - Code review for logic, naming, security
- `/InspectAI_bugs` - Bug detection and edge case analysis  
- `/InspectAI_refactor` - Refactoring suggestions
"""
        
        result = github_client.post_pr_comment(
            repo_url=repo_full_name,
            pr_number=pr_number,
            body=message
        )
        
        logger.info(f"Successfully posted {agent_name} response on {repo_full_name}#{pr_number}")
        return {"status": "success", "comment_id": result.get("id"), "agent": agent_name}
        
    except Exception as e:
        logger.error(f"Failed to post comment on {repo_full_name}#{pr_number}: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


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
