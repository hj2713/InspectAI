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
                    from config.default_config import BYTEZ_MODEL
                    config[key]["model"] = BYTEZ_MODEL
        
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
    """Handle InspectAI agent commands with REAL specialized agents.
    
    Args:
        repo_full_name: Full repository name (owner/repo)
        pr_number: Pull request number
        comment_author: Who triggered the command
        command: The command triggered (review, bugs, refactor)
        installation_id: GitHub App installation ID for authentication
        
    Returns:
        Result of posting comment
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
        
        # Map command to task type
        task_mapping = {
            "review": "full_review",  # All 12 agents
            "bugs": "bug_fix",  # Bug detection agents
            "refactor": "code_improvement"  # Code review agents only
        }
        
        task_type = task_mapping.get(command, "full_review")
        
        # Initialize orchestrator with configured provider
        config = copy.deepcopy(ORCHESTRATOR_CONFIG)
        provider = os.getenv("LLM_PROVIDER", "local")
        
        for key in config:
            if isinstance(config[key], dict):
                config[key]["provider"] = provider
        
        orchestrator = OrchestratorAgent(config)
        
        try:
            # Get PR files to analyze
            pr = github_client.get_pull_request(repo_full_name, pr_number)
            
            # Analyze all changed files
            all_findings = []
            files_analyzed = 0
            
            for pr_file in pr.files:
                if pr_file.status == "removed":
                    continue
                
                # Only analyze code files
                if not orchestrator._is_code_file(pr_file.filename):
                    continue
                
                try:
                    content = github_client.get_pr_file_content(repo_full_name, pr_number, pr_file.filename)
                    logger.info(f"Analyzing {pr_file.filename}...")
                    
                    # Run analysis based on command
                    if command == "review":
                        # Full review: all 12 agents
                        analysis = orchestrator.agents["analysis"].process(content)
                        bugs = orchestrator.agents["bug_detection"].process(content)
                        security = orchestrator.agents["security"].process(content)
                        
                        # Collect findings
                        for s in analysis.get("suggestions", []):
                            if isinstance(s, dict):
                                s["file"] = pr_file.filename
                                all_findings.append(s)
                        
                        for b in bugs.get("bugs", []):
                            if isinstance(b, dict):
                                b["file"] = pr_file.filename
                                all_findings.append(b)
                        
                        for v in security.get("vulnerabilities", []):
                            if isinstance(v, dict):
                                v["file"] = pr_file.filename
                                all_findings.append(v)
                    
                    elif command == "bugs":
                        # Bug detection only
                        bugs = orchestrator.agents["bug_detection"].process(content)
                        for b in bugs.get("bugs", []):
                            if isinstance(b, dict):
                                b["file"] = pr_file.filename
                                all_findings.append(b)
                    
                    elif command == "refactor":
                        # Code review only
                        analysis = orchestrator.agents["analysis"].process(content)
                        for s in analysis.get("suggestions", []):
                            if isinstance(s, dict):
                                s["file"] = pr_file.filename
                                all_findings.append(s)
                    
                    files_analyzed += 1
                    
                except Exception as e:
                    logger.error(f"Failed to analyze {pr_file.filename}: {e}")
                    continue
            
            # Generate summary comment
            message = _format_findings_message(
                command,
                comment_author,
                pr_number,
                repo_full_name,
                all_findings,
                files_analyzed
            )
            
            # Post comment
            result = github_client.post_pr_comment(
                repo_url=repo_full_name,
                pr_number=pr_number,
                body=message
            )
            
            logger.info(f"Successfully posted analysis on {repo_full_name}#{pr_number} ({len(all_findings)} findings)")
            return {"status": "success", "comment_id": result.get("id"), "findings_count": len(all_findings)}
            
        finally:
            orchestrator.cleanup()
        
    except Exception as e:
        logger.error(f"Failed to handle command on {repo_full_name}#{pr_number}: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


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
    message_parts.append("- `/InspectAI_review` - Full review \n")
    message_parts.append("- `/InspectAI_bugs` - Bug detection \n")
    message_parts.append("- `/InspectAI_refactor` - Code improvements \n")
    
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
