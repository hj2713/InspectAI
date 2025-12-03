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
