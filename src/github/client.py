"""GitHub Integration for repository access and PR comments.

This module provides functionality to:
1. Clone/download repositories
2. Read files from repositories
3. Read Pull Request information
4. Post comments on Pull Requests
5. GitHub App authentication with Installation Tokens

Setup for GitHub App (Recommended):
1. Create a GitHub App at https://github.com/settings/apps
2. Set GITHUB_APP_ID environment variable
3. Set GITHUB_APP_PRIVATE_KEY environment variable (or path to .pem file)

Setup for Personal Access Token (Alternative):
1. Create a PAT at https://github.com/settings/tokens
2. Set GITHUB_TOKEN environment variable

Usage:
    from src.github.client import GitHubClient
    
    # Using GitHub App (for any installation)
    client = GitHubClient.from_installation(installation_id=12345)
    
    # Using PAT (personal use)
    client = GitHubClient()
    
    # Clone a repo
    repo_path = client.clone_repo("owner/repo")
    
    # Get PR files
    files = client.get_pr_files("owner/repo", pr_number=123)
    
    # Post review comment
    client.post_review_comment("owner/repo", 123, "Great code!", "file.py", 10)
"""
import os
import re
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests

from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class PRFile:
    """Represents a file changed in a Pull Request."""
    filename: str
    status: str  # added, modified, removed, renamed
    additions: int
    deletions: int
    patch: Optional[str]  # The diff
    content: Optional[str] = None  # Full file content


@dataclass  
class PullRequest:
    """Represents a Pull Request."""
    number: int
    title: str
    body: str
    state: str  # open, closed
    head_sha: str
    base_sha: str
    head_branch: str
    base_branch: str
    files: List[PRFile]
    author: str
    url: str


def get_jwt_token(app_id: str, private_key: str) -> str:
    """Generate a JWT token for GitHub App authentication.
    
    Args:
        app_id: GitHub App ID
        private_key: GitHub App private key (PEM format)
        
    Returns:
        JWT token string
    """
    try:
        import jwt
    except ImportError:
        raise ImportError("PyJWT is required for GitHub App auth. Install with: pip install PyJWT")
    
    now = int(time.time())
    payload = {
        "iat": now - 60,  # Issued 60 seconds ago (clock drift)
        "exp": now + (10 * 60),  # Expires in 10 minutes
        "iss": app_id
    }
    
    return jwt.encode(payload, private_key, algorithm="RS256")


def get_installation_token(app_id: str, private_key: str, installation_id: int) -> str:
    """Get an installation access token for a GitHub App installation.
    
    Args:
        app_id: GitHub App ID
        private_key: GitHub App private key (PEM format)
        installation_id: Installation ID from webhook payload
        
    Returns:
        Installation access token
    """
    jwt_token = get_jwt_token(app_id, private_key)
    
    url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    response = requests.post(url, headers=headers)
    response.raise_for_status()
    
    data = response.json()
    return data["token"]


class GitHubClient:
    """Client for GitHub API interactions."""
    
    BASE_URL = "https://api.github.com"
    
    # Cache for installation tokens (installation_id -> (token, expiry))
    _token_cache: Dict[int, tuple] = {}
    
    def __init__(self, token: Optional[str] = None, installation_id: Optional[int] = None):
        """Initialize GitHub client.
        
        Args:
            token: GitHub Personal Access Token or Installation token.
                   Falls back to GITHUB_TOKEN env var.
            installation_id: GitHub App installation ID (for auto-token refresh)
        """
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.installation_id = installation_id
        self._app_id = os.getenv("GITHUB_APP_ID")
        self._private_key = self._load_private_key()
        
        if not self.token and not (self._app_id and self._private_key):
            logger.warning("No GitHub token or App credentials provided. API rate limits will be restricted.")
        
        self.session = requests.Session()
        self._update_session_auth()
        
        self._temp_dirs: List[Path] = []
    
    def _load_private_key(self) -> Optional[str]:
        """Load GitHub App private key from env var or file."""
        import base64
        key = os.getenv("GITHUB_APP_PRIVATE_KEY", "")
        
        # Check if it's a file path
        if key and os.path.isfile(key):
            with open(key, "r") as f:
                return f.read()
        
        # Check if it's base64 encoded
        if key and "BEGIN" not in key:
            try:
                decoded = base64.b64decode(key).decode('utf-8')
                if "BEGIN" in decoded:
                    return decoded
            except Exception:
                pass
        
        # Check if it's the actual key content
        if key and "BEGIN" in key:
            return key.replace("\\n", "\n")
        
        return None
    
    def _update_session_auth(self):
        """Update session headers with current auth token."""
        if self.token:
            self.session.headers.update({
                "Authorization": f"token {self.token}",
                "Accept": "application/vnd.github.v3+json"
            })
        else:
            self.session.headers.update({
                "Accept": "application/vnd.github.v3+json"
            })
    
    @classmethod
    def from_installation(cls, installation_id: int) -> "GitHubClient":
        """Create a client authenticated as a GitHub App installation.
        
        This is the recommended way to authenticate when processing webhooks.
        The token will be automatically refreshed if needed.
        
        Args:
            installation_id: Installation ID from the webhook payload
            
        Returns:
            GitHubClient instance authenticated for the installation
        """
        import base64
        
        app_id = os.getenv("GITHUB_APP_ID")
        private_key_raw = os.getenv("GITHUB_APP_PRIVATE_KEY", "")
        
        logger.debug(f"GITHUB_APP_ID: {app_id}")
        logger.debug(f"GITHUB_APP_PRIVATE_KEY length: {len(private_key_raw)}")
        logger.debug(f"GITHUB_APP_PRIVATE_KEY first 50 chars: {private_key_raw[:50] if private_key_raw else 'EMPTY'}")
        
        # Load private key - try multiple formats
        private_key = None
        
        # Option 1: Check if it's a file path
        if private_key_raw and os.path.isfile(private_key_raw):
            logger.info("Loading private key from file path")
            with open(private_key_raw, "r") as f:
                private_key = f.read()
        
        # Option 2: Check if it's base64 encoded
        elif private_key_raw and "BEGIN" not in private_key_raw:
            try:
                decoded = base64.b64decode(private_key_raw).decode('utf-8')
                if "BEGIN" in decoded:
                    logger.info("Loaded private key from base64")
                    private_key = decoded
            except Exception as e:
                logger.debug(f"Not base64 encoded: {e}")
        
        # Option 3: Direct key content (handle escaped newlines)
        if not private_key and private_key_raw:
            # Replace escaped newlines with actual newlines
            key = private_key_raw.replace("\\n", "\n")
            if "BEGIN" in key:
                logger.info("Loaded private key from direct content")
                private_key = key
        
        if not private_key:
            raise ValueError(
                "GITHUB_APP_PRIVATE_KEY must be set to either the key content, base64-encoded key, or path to .pem file. "
                f"Got value starting with: {private_key_raw[:30] if private_key_raw else 'EMPTY'}..."
            )
        
        if not app_id:
            raise ValueError("GITHUB_APP_ID environment variable must be set")
        
        # Check cache first
        now = time.time()
        if installation_id in cls._token_cache:
            cached_token, expiry = cls._token_cache[installation_id]
            if expiry > now + 300:  # Still valid for at least 5 minutes
                logger.debug(f"Using cached token for installation {installation_id}")
                return cls(token=cached_token, installation_id=installation_id)
        
        # Get new token
        logger.info(f"Getting new installation token for installation {installation_id}")
        token = get_installation_token(app_id, private_key, installation_id)
        
        # Cache for 55 minutes (tokens are valid for 1 hour)
        cls._token_cache[installation_id] = (token, now + 55 * 60)
        
        return cls(token=token, installation_id=installation_id)
    
    def _parse_repo_url(self, repo_url: str) -> tuple[str, str]:
        """Parse owner and repo name from various URL formats.
        
        Supports:
            - owner/repo
            - https://github.com/owner/repo
            - https://github.com/owner/repo.git
            - git@github.com:owner/repo.git
        
        Returns:
            Tuple of (owner, repo)
        """
        # Direct format: owner/repo
        if "/" in repo_url and "github.com" not in repo_url and ":" not in repo_url:
            parts = repo_url.strip("/").split("/")
            if len(parts) >= 2:
                return parts[0], parts[1].replace(".git", "")
        
        # HTTPS URL
        if "github.com" in repo_url:
            # Remove .git suffix if present
            repo_url = repo_url.replace(".git", "")
            
            # Handle https://github.com/owner/repo format
            if "://" in repo_url:
                parsed = urlparse(repo_url)
                path_parts = parsed.path.strip("/").split("/")
                if len(path_parts) >= 2:
                    return path_parts[0], path_parts[1]
            
            # Handle git@github.com:owner/repo format
            if ":" in repo_url:
                match = re.search(r"github\.com[:/]([^/]+)/([^/]+)", repo_url)
                if match:
                    return match.group(1), match.group(2)
        
        raise ValueError(f"Could not parse repository URL: {repo_url}")
    
    def _api_get(self, endpoint: str) -> Dict[str, Any]:
        """Make a GET request to GitHub API."""
        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        logger.debug(f"GET {url}")
        
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()
    
    def _api_post(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Make a POST request to GitHub API."""
        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        logger.debug(f"POST {url}")
        
        response = self.session.post(url, json=data)
        response.raise_for_status()
        return response.json()
    
    def _api_put(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Make a PUT request to GitHub API."""
        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        logger.debug(f"PUT {url}")
        
        response = self.session.put(url, json=data)
        response.raise_for_status()
        return response.json()
    
    def clone_repo(
        self,
        repo_url: str,
        branch: Optional[str] = None,
        dest_path: Optional[Path] = None
    ) -> Path:
        """Clone a repository to local filesystem.
        
        Args:
            repo_url: Repository URL or owner/repo format
            branch: Specific branch to clone (defaults to default branch)
            dest_path: Destination path (creates temp dir if not provided)
            
        Returns:
            Path to the cloned repository
        """
        import subprocess
        
        owner, repo = self._parse_repo_url(repo_url)
        clone_url = f"https://github.com/{owner}/{repo}.git"
        
        if dest_path is None:
            dest_path = Path(tempfile.mkdtemp(prefix=f"github_{repo}_"))
            self._temp_dirs.append(dest_path)
        
        logger.info(f"Cloning {owner}/{repo} to {dest_path}")
        
        cmd = ["git", "clone", "--depth", "1"]
        if branch:
            cmd.extend(["--branch", branch])
        cmd.extend([clone_url, str(dest_path)])
        
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            logger.info(f"Successfully cloned {owner}/{repo}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to clone repository: {e.stderr}")
            raise RuntimeError(f"Failed to clone repository: {e.stderr}")
        
        return dest_path
    
    def download_repo_archive(
        self,
        repo_url: str,
        branch: Optional[str] = None,
        dest_path: Optional[Path] = None
    ) -> Path:
        """Download repository as ZIP archive (no git required).
        
        Args:
            repo_url: Repository URL or owner/repo format
            branch: Specific branch (defaults to default branch)
            dest_path: Destination path (creates temp dir if not provided)
            
        Returns:
            Path to the extracted repository
        """
        import zipfile
        import io
        
        owner, repo = self._parse_repo_url(repo_url)
        
        # Get default branch if not specified
        if not branch:
            repo_info = self._api_get(f"repos/{owner}/{repo}")
            branch = repo_info.get("default_branch", "main")
        
        # Download ZIP
        zip_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.zip"
        logger.info(f"Downloading {owner}/{repo} archive...")
        
        response = self.session.get(zip_url)
        response.raise_for_status()
        
        if dest_path is None:
            dest_path = Path(tempfile.mkdtemp(prefix=f"github_{repo}_"))
            self._temp_dirs.append(dest_path)
        
        # Extract ZIP
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            zf.extractall(dest_path)
        
        # The extracted folder is usually named repo-branch
        extracted_folder = dest_path / f"{repo}-{branch}"
        if extracted_folder.exists():
            # Move contents up one level
            for item in extracted_folder.iterdir():
                shutil.move(str(item), str(dest_path / item.name))
            extracted_folder.rmdir()
        
        logger.info(f"Successfully downloaded and extracted {owner}/{repo}")
        return dest_path
    
    def get_repo_files(
        self,
        repo_url: str,
        path: str = "",
        branch: Optional[str] = None,
        extensions: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Get list of files in a repository.
        
        Args:
            repo_url: Repository URL or owner/repo format
            path: Path within the repository
            branch: Branch name (defaults to default branch)
            extensions: Filter by file extensions (e.g., ['.py', '.js'])
            
        Returns:
            List of file info dicts with 'path', 'type', 'size', etc.
        """
        owner, repo = self._parse_repo_url(repo_url)
        
        endpoint = f"repos/{owner}/{repo}/contents/{path}"
        if branch:
            endpoint += f"?ref={branch}"
        
        try:
            contents = self._api_get(endpoint)
        except requests.HTTPError as e:
            logger.error(f"Failed to get repo contents: {e}")
            raise
        
        if not isinstance(contents, list):
            contents = [contents]
        
        files = []
        for item in contents:
            if extensions and item["type"] == "file":
                if not any(item["name"].endswith(ext) for ext in extensions):
                    continue
            files.append({
                "path": item["path"],
                "name": item["name"],
                "type": item["type"],
                "size": item.get("size", 0),
                "sha": item["sha"],
                "download_url": item.get("download_url")
            })
        
        return files
    
    def get_file_content(
        self,
        repo_url: str,
        file_path: str,
        branch: Optional[str] = None
    ) -> str:
        """Get content of a specific file.
        
        Args:
            repo_url: Repository URL or owner/repo format
            file_path: Path to file within the repo
            branch: Branch name
            
        Returns:
            File content as string
        """
        import base64
        
        owner, repo = self._parse_repo_url(repo_url)
        
        endpoint = f"repos/{owner}/{repo}/contents/{file_path}"
        if branch:
            endpoint += f"?ref={branch}"
        
        data = self._api_get(endpoint)
        
        if data.get("encoding") == "base64":
            content = base64.b64decode(data["content"]).decode("utf-8")
        else:
            content = data.get("content", "")
        
        return content
    
    def get_pull_request(self, repo_url: str, pr_number: int) -> PullRequest:
        """Get Pull Request details including changed files.
        
        Args:
            repo_url: Repository URL or owner/repo format
            pr_number: Pull request number
            
        Returns:
            PullRequest object with full details
        """
        owner, repo = self._parse_repo_url(repo_url)
        
        # Get PR info
        pr_data = self._api_get(f"repos/{owner}/{repo}/pulls/{pr_number}")
        
        # Get PR files
        files_data = self._api_get(f"repos/{owner}/{repo}/pulls/{pr_number}/files")
        
        files = []
        for f in files_data:
            pr_file = PRFile(
                filename=f["filename"],
                status=f["status"],
                additions=f["additions"],
                deletions=f["deletions"],
                patch=f.get("patch")
            )
            files.append(pr_file)
        
        return PullRequest(
            number=pr_data["number"],
            title=pr_data["title"],
            body=pr_data.get("body", ""),
            state=pr_data["state"],
            head_sha=pr_data["head"]["sha"],
            base_sha=pr_data["base"]["sha"],
            head_branch=pr_data["head"]["ref"],
            base_branch=pr_data["base"]["ref"],
            files=files,
            author=pr_data["user"]["login"],
            url=pr_data["html_url"]
        )
    
    def get_pr_file_content(
        self,
        repo_url: str,
        pr_number: int,
        file_path: str
    ) -> str:
        """Get the full content of a file in a PR's head branch.
        
        Args:
            repo_url: Repository URL or owner/repo format
            pr_number: Pull request number
            file_path: Path to the file
            
        Returns:
            File content as string
        """
        owner, repo = self._parse_repo_url(repo_url)
        
        # Get PR to find head branch
        pr_data = self._api_get(f"repos/{owner}/{repo}/pulls/{pr_number}")
        head_sha = pr_data["head"]["sha"]
        
        return self.get_file_content(repo_url, file_path, branch=head_sha)
    
    def post_pr_comment(
        self,
        repo_url: str,
        pr_number: int,
        body: str
    ) -> Dict[str, Any]:
        """Post a general comment on a Pull Request.
        
        Args:
            repo_url: Repository URL or owner/repo format
            pr_number: Pull request number
            body: Comment text (supports Markdown)
            
        Returns:
            Created comment data
        """
        owner, repo = self._parse_repo_url(repo_url)
        
        logger.info(f"Posting comment on PR #{pr_number}")
        
        return self._api_post(
            f"repos/{owner}/{repo}/issues/{pr_number}/comments",
            {"body": body}
        )
    
    def post_review_comment(
        self,
        repo_url: str,
        pr_number: int,
        body: str,
        file_path: str,
        line: int,
        side: str = "RIGHT"
    ) -> Dict[str, Any]:
        """Post a review comment on a specific line in a PR.
        
        Args:
            repo_url: Repository URL or owner/repo format
            pr_number: Pull request number
            body: Comment text
            file_path: Path to the file
            line: Line number to comment on
            side: LEFT (base) or RIGHT (head/new code)
            
        Returns:
            Created comment data
        """
        owner, repo = self._parse_repo_url(repo_url)
        
        # Get the latest commit SHA
        pr_data = self._api_get(f"repos/{owner}/{repo}/pulls/{pr_number}")
        commit_id = pr_data["head"]["sha"]
        
        logger.info(f"Posting review comment on {file_path}:{line}")
        
        return self._api_post(
            f"repos/{owner}/{repo}/pulls/{pr_number}/comments",
            {
                "body": body,
                "commit_id": commit_id,
                "path": file_path,
                "line": line,
                "side": side
            }
        )
    
    def create_review(
        self,
        repo_url: str,
        pr_number: int,
        body: str,
        event: str = "COMMENT",
        comments: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Create a complete review on a Pull Request.
        
        Args:
            repo_url: Repository URL or owner/repo format
            pr_number: Pull request number
            body: Overall review summary
            event: APPROVE, REQUEST_CHANGES, or COMMENT
            comments: List of inline comments with path, line, body
            
        Returns:
            Created review data
        """
        owner, repo = self._parse_repo_url(repo_url)
        
        # Get the latest commit SHA
        pr_data = self._api_get(f"repos/{owner}/{repo}/pulls/{pr_number}")
        commit_id = pr_data["head"]["sha"]
        
        logger.info(f"Creating {event} review on PR #{pr_number}")
        
        review_data = {
            "commit_id": commit_id,
            "body": body,
            "event": event
        }
        
        if comments:
            review_data["comments"] = comments
        
        return self._api_post(
            f"repos/{owner}/{repo}/pulls/{pr_number}/reviews",
            review_data
        )
    
    def update_file_in_pr(
        self,
        repo_url: str,
        pr_number: int,
        file_path: str,
        new_content: str,
        commit_message: str
    ) -> Dict[str, Any]:
        """Update a file in a PR branch and commit the changes.
        
        Args:
            repo_url: Repository URL or owner/repo format
            pr_number: PR number
            file_path: Path to the file to update
            new_content: New content for the file
            commit_message: Commit message
            
        Returns:
            API response with commit info
        """
        import base64
        
        owner, repo = self._parse_repo_url(repo_url)
        
        # Get PR info to find the branch
        pr_data = self._api_get(f"repos/{owner}/{repo}/pulls/{pr_number}")
        branch = pr_data["head"]["ref"]
        
        # Get current file to get its SHA (needed for update)
        try:
            file_info = self._api_get(f"repos/{owner}/{repo}/contents/{file_path}?ref={branch}")
            file_sha = file_info["sha"]
        except Exception as e:
            logger.error(f"Failed to get file info for {file_path}: {e}")
            raise
        
        # Update the file
        encoded_content = base64.b64encode(new_content.encode()).decode()
        
        update_data = {
            "message": commit_message,
            "content": encoded_content,
            "sha": file_sha,
            "branch": branch
        }
        
        result = self._api_put(
            f"repos/{owner}/{repo}/contents/{file_path}",
            update_data
        )
        
        logger.info(f"Committed fix to {file_path} in {owner}/{repo}#{pr_number}")
        return result
    
    def update_pr_body(self, repo_url: str, pr_number: int, body: str) -> Dict[str, Any]:
        """Update the PR body/description.
        
        Args:
            repo_url: Repository URL or owner/repo format
            pr_number: Pull request number
            body: New PR description
            
        Returns:
            Updated PR data
        """
        owner, repo = self._parse_repo_url(repo_url)
        
        logger.info(f"Updating PR description for {owner}/{repo}#{pr_number}")
        
        return self._api_patch(
            f"repos/{owner}/{repo}/pulls/{pr_number}",
            {"body": body}
        )
    
    def cleanup(self) -> None:
        """Clean up temporary directories."""
        for temp_dir in self._temp_dirs:
            if temp_dir.exists():
                logger.debug(f"Cleaning up {temp_dir}")
                shutil.rmtree(temp_dir, ignore_errors=True)
        self._temp_dirs.clear()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
        return False
