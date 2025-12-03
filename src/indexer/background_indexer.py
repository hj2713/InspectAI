"""Background Indexing Service - Async repository indexing.

This module handles:
- Async background indexing (non-blocking)
- Full repository indexing on first install
- Incremental updates on PR events
- Job tracking and progress reporting
"""

import os
import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

from .code_parser import CodeParserFactory, ParsedFile
from .indexer import CodebaseIndexer, get_codebase_indexer


class BackgroundIndexer:
    """Handles async background indexing of repositories."""
    
    def __init__(self, max_workers: int = 4):
        """Initialize background indexer.
        
        Args:
            max_workers: Max parallel file parsing threads
        """
        self.indexer = get_codebase_indexer()
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self._running_jobs: Dict[str, asyncio.Task] = {}
        
        logger.info(f"BackgroundIndexer initialized with {max_workers} workers")
    
    async def start_full_index(
        self,
        repo_full_name: str,
        github_client: Any,
        installation_id: int = None,
        commit_sha: str = None
    ) -> Optional[str]:
        """Start a full repository indexing job in the background.
        
        This method returns immediately - indexing happens async.
        
        Args:
            repo_full_name: Full repo name (e.g., "owner/repo")
            github_client: GitHub client for fetching files
            installation_id: GitHub App installation ID
            commit_sha: Commit SHA to index (default: HEAD)
            
        Returns:
            Job ID or None if failed to start
        """
        # Register project if not exists
        project_id = await self.indexer.register_project(
            repo_full_name=repo_full_name,
            installation_id=installation_id
        )
        
        if not project_id:
            logger.error(f"Failed to register project {repo_full_name}")
            return None
        
        # Check if already indexing
        if repo_full_name in self._running_jobs:
            existing_task = self._running_jobs[repo_full_name]
            if not existing_task.done():
                logger.info(f"Indexing already in progress for {repo_full_name}")
                return project_id
        
        # Create job record
        job_id = await self._create_job(project_id, "full", commit_sha)
        
        # Start background task
        task = asyncio.create_task(
            self._run_full_index(
                project_id=project_id,
                job_id=job_id,
                repo_full_name=repo_full_name,
                github_client=github_client,
                commit_sha=commit_sha
            )
        )
        
        self._running_jobs[repo_full_name] = task
        
        logger.info(f"Started background indexing for {repo_full_name} (job: {job_id})")
        return job_id
    
    async def start_incremental_index(
        self,
        repo_full_name: str,
        github_client: Any,
        changed_files: List[str],
        commit_sha: str = None
    ) -> Optional[str]:
        """Start incremental indexing for changed files.
        
        Args:
            repo_full_name: Full repo name
            github_client: GitHub client
            changed_files: List of file paths that changed
            commit_sha: New commit SHA
            
        Returns:
            Job ID or None
        """
        project = await self.indexer.get_project(repo_full_name)
        
        if not project:
            logger.warning(f"Project {repo_full_name} not indexed yet, starting full index")
            return await self.start_full_index(repo_full_name, github_client, commit_sha=commit_sha)
        
        project_id = project["id"]
        
        # Filter to supported files only
        supported_files = [f for f in changed_files if CodeParserFactory.is_supported(f)]
        
        if not supported_files:
            logger.debug(f"No supported files in changes for {repo_full_name}")
            return None
        
        # Create job
        job_id = await self._create_job(project_id, "incremental", commit_sha, len(supported_files))
        
        # Start background task
        task = asyncio.create_task(
            self._run_incremental_index(
                project_id=project_id,
                job_id=job_id,
                repo_full_name=repo_full_name,
                github_client=github_client,
                files=supported_files,
                commit_sha=commit_sha
            )
        )
        
        self._running_jobs[f"{repo_full_name}:incremental:{job_id}"] = task
        
        logger.info(f"Started incremental indexing for {repo_full_name}: {len(supported_files)} files")
        return job_id
    
    async def _create_job(
        self,
        project_id: str,
        job_type: str,
        commit_sha: str = None,
        total_files: int = 0
    ) -> Optional[str]:
        """Create an indexing job record."""
        if not self.indexer.client:
            return None
        
        try:
            result = self.indexer.client.table("indexing_jobs").insert({
                "project_id": project_id,
                "job_type": job_type,
                "status": "pending",
                "total_files": total_files,
                "processed_files": 0,
                "commit_sha": commit_sha,
                "triggered_by": "webhook"
            }).execute()
            
            return result.data[0]["id"] if result.data else None
            
        except Exception as e:
            logger.error(f"Error creating job: {e}")
            return None
    
    async def _update_job(
        self,
        job_id: str,
        status: str = None,
        processed_files: int = None,
        total_files: int = None,
        error_message: str = None
    ):
        """Update job progress."""
        if not self.indexer.client or not job_id:
            return
        
        try:
            update_data = {}
            
            if status:
                update_data["status"] = status
                if status == "running":
                    update_data["started_at"] = datetime.utcnow().isoformat()
                elif status in ["completed", "failed"]:
                    update_data["completed_at"] = datetime.utcnow().isoformat()
            
            if processed_files is not None:
                update_data["processed_files"] = processed_files
            
            if total_files is not None:
                update_data["total_files"] = total_files
            
            if error_message:
                update_data["error_message"] = error_message
            
            if update_data:
                self.indexer.client.table("indexing_jobs") \
                    .update(update_data) \
                    .eq("id", job_id) \
                    .execute()
                    
        except Exception as e:
            logger.error(f"Error updating job: {e}")
    
    async def _run_full_index(
        self,
        project_id: str,
        job_id: str,
        repo_full_name: str,
        github_client: Any,
        commit_sha: str = None
    ):
        """Run full repository indexing (background task)."""
        try:
            await self._update_job(job_id, status="running")
            await self.indexer.update_project_status(project_id, "indexing")
            
            # Get all files from repo
            logger.info(f"Fetching file list for {repo_full_name}...")
            all_files = await self._get_repo_files(github_client, repo_full_name)
            
            # Filter to supported files
            supported_files = [f for f in all_files if CodeParserFactory.is_supported(f)]
            
            await self._update_job(job_id, total_files=len(supported_files))
            
            logger.info(f"Found {len(supported_files)} supported files to index in {repo_full_name}")
            
            # Index files
            processed = 0
            errors = 0
            
            for file_path in supported_files:
                try:
                    # Fetch file content
                    content = await self._fetch_file_content(github_client, repo_full_name, file_path)
                    
                    if content is None:
                        continue
                    
                    # Parse file
                    parsed = CodeParserFactory.parse_file(file_path, content)
                    
                    if parsed:
                        # Index into Supabase
                        await self.indexer.index_file(project_id, parsed)
                    
                    processed += 1
                    
                    # Update progress every 10 files
                    if processed % 10 == 0:
                        await self._update_job(job_id, processed_files=processed)
                        logger.debug(f"Indexed {processed}/{len(supported_files)} files")
                        
                except Exception as e:
                    logger.error(f"Error indexing {file_path}: {e}")
                    errors += 1
            
            # Get final stats
            stats = await self.indexer.get_project_stats(project_id)
            
            # Update project status
            await self.indexer.update_project_status(
                project_id,
                "completed",
                commit_sha=commit_sha,
                stats=stats
            )
            
            await self._update_job(job_id, status="completed", processed_files=processed)
            
            logger.info(
                f"Completed indexing {repo_full_name}: "
                f"{processed} files, {stats.get('total_symbols', 0)} symbols, "
                f"{stats.get('total_calls', 0)} calls"
            )
            
        except Exception as e:
            logger.error(f"Error in full index for {repo_full_name}: {e}")
            await self._update_job(job_id, status="failed", error_message=str(e))
            await self.indexer.update_project_status(project_id, "failed")
        
        finally:
            # Clean up running job reference
            if repo_full_name in self._running_jobs:
                del self._running_jobs[repo_full_name]
    
    async def _run_incremental_index(
        self,
        project_id: str,
        job_id: str,
        repo_full_name: str,
        github_client: Any,
        files: List[str],
        commit_sha: str = None
    ):
        """Run incremental indexing for changed files."""
        try:
            await self._update_job(job_id, status="running", total_files=len(files))
            
            processed = 0
            
            for file_path in files:
                try:
                    content = await self._fetch_file_content(github_client, repo_full_name, file_path)
                    
                    if content is None:
                        # File might be deleted
                        await self._handle_deleted_file(project_id, file_path)
                        continue
                    
                    parsed = CodeParserFactory.parse_file(file_path, content)
                    
                    if parsed:
                        await self.indexer.index_file(project_id, parsed)
                    
                    processed += 1
                    
                except Exception as e:
                    logger.error(f"Error indexing {file_path}: {e}")
            
            # Update commit SHA
            await self.indexer.update_project_status(project_id, "completed", commit_sha=commit_sha)
            await self._update_job(job_id, status="completed", processed_files=processed)
            
            logger.info(f"Incremental index complete for {repo_full_name}: {processed} files updated")
            
        except Exception as e:
            logger.error(f"Error in incremental index: {e}")
            await self._update_job(job_id, status="failed", error_message=str(e))
        
        finally:
            job_key = f"{repo_full_name}:incremental:{job_id}"
            if job_key in self._running_jobs:
                del self._running_jobs[job_key]
    
    async def _handle_deleted_file(self, project_id: str, file_path: str):
        """Handle a deleted file by removing its index data."""
        if not self.indexer.client:
            return
        
        try:
            # Find file ID
            result = self.indexer.client.table("code_files") \
                .select("id") \
                .eq("project_id", project_id) \
                .eq("file_path", file_path) \
                .execute()
            
            if result.data:
                file_id = result.data[0]["id"]
                
                # Delete associated data
                self.indexer.client.table("code_calls").delete().eq("caller_file_id", file_id).execute()
                self.indexer.client.table("code_imports").delete().eq("file_id", file_id).execute()
                self.indexer.client.table("code_symbols").delete().eq("file_id", file_id).execute()
                self.indexer.client.table("code_files").delete().eq("id", file_id).execute()
                
                logger.info(f"Removed deleted file from index: {file_path}")
                
        except Exception as e:
            logger.error(f"Error handling deleted file {file_path}: {e}")
    
    async def _get_repo_files(
        self,
        github_client: Any,
        repo_full_name: str,
        path: str = ""
    ) -> List[str]:
        """Recursively get all files from repository."""
        all_files = []
        
        try:
            owner, repo = repo_full_name.split("/")
            
            # Use GitHub API to get tree
            # This is a simplified approach - in production, use recursive tree API
            contents = github_client.get_repo_contents(owner, repo, path)
            
            if not isinstance(contents, list):
                contents = [contents]
            
            for item in contents:
                if item.get("type") == "file":
                    all_files.append(item.get("path"))
                elif item.get("type") == "dir":
                    # Recursively get directory contents
                    sub_files = await self._get_repo_files(
                        github_client,
                        repo_full_name,
                        item.get("path")
                    )
                    all_files.extend(sub_files)
                    
        except Exception as e:
            logger.error(f"Error getting repo files: {e}")
        
        return all_files
    
    async def _fetch_file_content(
        self,
        github_client: Any,
        repo_full_name: str,
        file_path: str
    ) -> Optional[str]:
        """Fetch file content from GitHub."""
        try:
            owner, repo = repo_full_name.split("/")
            content = github_client.get_file_content(owner, repo, file_path)
            return content
        except Exception as e:
            logger.debug(f"Could not fetch {file_path}: {e}")
            return None
    
    def get_job_status(self, repo_full_name: str) -> str:
        """Get current indexing status for a repo.
        
        Returns:
            Status string: "idle", "indexing", "queued"
        """
        if repo_full_name in self._running_jobs:
            task = self._running_jobs[repo_full_name]
            if not task.done():
                return "indexing"
        
        return "idle"


# Singleton instance
_background_indexer: Optional[BackgroundIndexer] = None


def get_background_indexer() -> BackgroundIndexer:
    """Get or create the singleton BackgroundIndexer instance."""
    global _background_indexer
    
    if _background_indexer is None:
        _background_indexer = BackgroundIndexer()
    
    return _background_indexer


async def trigger_repo_indexing(
    repo_full_name: str,
    github_client: Any,
    installation_id: int = None,
    changed_files: List[str] = None,
    commit_sha: str = None
) -> Optional[str]:
    """Convenience function to trigger repository indexing.
    
    Automatically chooses full vs incremental based on context.
    
    Args:
        repo_full_name: Full repo name
        github_client: GitHub client
        installation_id: GitHub App installation ID
        changed_files: Optional list of changed files (for incremental)
        commit_sha: Current commit SHA
        
    Returns:
        Job ID or None
    """
    indexer = get_background_indexer()
    
    if changed_files:
        return await indexer.start_incremental_index(
            repo_full_name=repo_full_name,
            github_client=github_client,
            changed_files=changed_files,
            commit_sha=commit_sha
        )
    else:
        return await indexer.start_full_index(
            repo_full_name=repo_full_name,
            github_client=github_client,
            installation_id=installation_id,
            commit_sha=commit_sha
        )


# ============================================
# Scheduled Reindexing (Weekly Job)
# ============================================

class ScheduledReindexer:
    """Handles scheduled weekly reindexing of all repositories.
    
    This ensures the codebase index stays up-to-date even if
    incremental indexing misses some changes.
    """
    
    def __init__(self):
        self._scheduler_task: Optional[asyncio.Task] = None
        self._is_running = False
        self._last_run: Optional[datetime] = None
        self._reindex_interval_days = int(os.getenv("REINDEX_INTERVAL_DAYS", "7"))
        
        logger.info(f"ScheduledReindexer initialized (interval: {self._reindex_interval_days} days)")
    
    async def start_scheduler(self):
        """Start the background scheduler for weekly reindexing."""
        if self._scheduler_task and not self._scheduler_task.done():
            logger.info("Scheduler already running")
            return
        
        self._is_running = True
        self._scheduler_task = asyncio.create_task(self._run_scheduler())
        logger.info("Started scheduled reindexing scheduler")
    
    async def stop_scheduler(self):
        """Stop the background scheduler."""
        self._is_running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        logger.info("Stopped scheduled reindexing scheduler")
    
    async def _run_scheduler(self):
        """Main scheduler loop - checks every hour if reindex is needed."""
        while self._is_running:
            try:
                # Check if it's time to reindex (every week by default)
                if await self._should_reindex():
                    logger.info("Starting scheduled weekly reindexing...")
                    await self.reindex_all_repositories()
                    self._last_run = datetime.utcnow()
                
                # Sleep for 1 hour before checking again
                await asyncio.sleep(3600)  # 1 hour
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
                await asyncio.sleep(3600)  # Wait an hour before retrying
    
    async def _should_reindex(self) -> bool:
        """Check if enough time has passed since last reindex."""
        if self._last_run is None:
            # Check Supabase for last reindex time
            try:
                from .indexer import get_codebase_indexer
                indexer = get_codebase_indexer()
                if indexer.client:
                    # Get the oldest last_indexed_at from all projects
                    result = indexer.client.table("indexed_projects") \
                        .select("last_indexed_at") \
                        .order("last_indexed_at", desc=False) \
                        .limit(1) \
                        .execute()
                    
                    if result.data and result.data[0].get("last_indexed_at"):
                        oldest = datetime.fromisoformat(
                            result.data[0]["last_indexed_at"].replace("Z", "+00:00")
                        )
                        days_since = (datetime.utcnow().replace(tzinfo=oldest.tzinfo) - oldest).days
                        return days_since >= self._reindex_interval_days
            except Exception as e:
                logger.warning(f"Could not check last reindex time: {e}")
            
            # Default: reindex if we've never run before
            return True
        
        days_since_last_run = (datetime.utcnow() - self._last_run).days
        return days_since_last_run >= self._reindex_interval_days
    
    async def reindex_all_repositories(self) -> Dict[str, Any]:
        """Reindex all registered repositories.
        
        This is the main method for scheduled reindexing.
        Can also be called manually via the /inspectai_reindex command.
        
        Returns:
            Summary dict with success/failure counts
        """
        from .indexer import get_codebase_indexer
        from ..github.client import GitHubClient
        
        indexer = get_codebase_indexer()
        if not indexer.client:
            logger.warning("Supabase not configured - cannot reindex")
            return {"status": "error", "message": "Supabase not configured"}
        
        # Get all registered projects
        try:
            result = indexer.client.table("indexed_projects") \
                .select("repo_full_name, installation_id, last_indexed_at") \
                .execute()
            
            projects = result.data or []
            logger.info(f"Found {len(projects)} repositories to reindex")
            
        except Exception as e:
            logger.error(f"Failed to fetch projects for reindexing: {e}")
            return {"status": "error", "message": str(e)}
        
        # Reindex each repository
        results = {
            "total": len(projects),
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "details": []
        }
        
        background_indexer = get_background_indexer()
        
        for project in projects:
            repo_full_name = project.get("repo_full_name")
            installation_id = project.get("installation_id")
            
            if not repo_full_name or not installation_id:
                results["skipped"] += 1
                results["details"].append({
                    "repo": repo_full_name,
                    "status": "skipped",
                    "reason": "Missing installation_id"
                })
                continue
            
            try:
                # Create GitHub client for this installation
                github_client = GitHubClient.from_installation(installation_id)
                
                # Start full reindex
                job_id = await background_indexer.start_full_index(
                    repo_full_name=repo_full_name,
                    github_client=github_client,
                    installation_id=installation_id
                )
                
                if job_id:
                    results["success"] += 1
                    results["details"].append({
                        "repo": repo_full_name,
                        "status": "started",
                        "job_id": job_id
                    })
                else:
                    results["failed"] += 1
                    results["details"].append({
                        "repo": repo_full_name,
                        "status": "failed",
                        "reason": "Could not start indexing job"
                    })
                    
            except Exception as e:
                results["failed"] += 1
                results["details"].append({
                    "repo": repo_full_name,
                    "status": "failed",
                    "reason": str(e)
                })
                logger.error(f"Failed to reindex {repo_full_name}: {e}")
            
            # Small delay between repos to avoid overwhelming the system
            await asyncio.sleep(2)
        
        logger.info(
            f"Scheduled reindex completed: {results['success']} success, "
            f"{results['failed']} failed, {results['skipped']} skipped"
        )
        
        return results
    
    async def reindex_single_repository(
        self,
        repo_full_name: str,
        installation_id: int
    ) -> Dict[str, Any]:
        """Reindex a single repository on demand.
        
        This is used by the /inspectai_reindex command.
        
        Args:
            repo_full_name: Full repository name
            installation_id: GitHub App installation ID
            
        Returns:
            Result dict with status and job_id
        """
        from ..github.client import GitHubClient
        
        try:
            github_client = GitHubClient.from_installation(installation_id)
            background_indexer = get_background_indexer()
            
            job_id = await background_indexer.start_full_index(
                repo_full_name=repo_full_name,
                github_client=github_client,
                installation_id=installation_id
            )
            
            if job_id:
                return {
                    "status": "started",
                    "repo": repo_full_name,
                    "job_id": job_id,
                    "message": f"Reindexing started for {repo_full_name}"
                }
            else:
                return {
                    "status": "failed",
                    "repo": repo_full_name,
                    "message": "Could not start reindexing job"
                }
                
        except Exception as e:
            logger.error(f"Failed to reindex {repo_full_name}: {e}")
            return {
                "status": "error",
                "repo": repo_full_name,
                "message": str(e)
            }
    
    def get_status(self) -> Dict[str, Any]:
        """Get current scheduler status."""
        return {
            "is_running": self._is_running,
            "last_run": self._last_run.isoformat() if self._last_run else None,
            "interval_days": self._reindex_interval_days,
            "scheduler_active": self._scheduler_task is not None and not self._scheduler_task.done()
        }


# Singleton instance for scheduled reindexer
_scheduled_reindexer: Optional[ScheduledReindexer] = None


def get_scheduled_reindexer() -> ScheduledReindexer:
    """Get or create the singleton ScheduledReindexer instance."""
    global _scheduled_reindexer
    
    if _scheduled_reindexer is None:
        _scheduled_reindexer = ScheduledReindexer()
    
    return _scheduled_reindexer


async def start_scheduled_reindexing():
    """Start the scheduled weekly reindexing.
    
    Call this on application startup to enable automatic reindexing.
    """
    reindexer = get_scheduled_reindexer()
    await reindexer.start_scheduler()


async def stop_scheduled_reindexing():
    """Stop the scheduled reindexing.
    
    Call this on application shutdown.
    """
    reindexer = get_scheduled_reindexer()
    await reindexer.stop_scheduler()

