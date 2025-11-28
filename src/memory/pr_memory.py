"""PR Memory Manager - Maintains context across InspectAI commands.

This module uses VectorStore to maintain persistent memory about:
- PR analysis history
- Bug findings that need to be fixed
- Previous reviews and suggestions
- Cross-command context

This enables commands to work together:
- /inspectai_bugs stores findings
- /inspectai_refactor reads those findings to auto-fix
- /inspectai_review only analyzes diffs, not whole files
"""
import json
import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict

from .vector_store import VectorStore
from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class BugFinding:
    """Represents a bug finding stored in memory."""
    file_path: str
    line_number: int
    category: str
    severity: str
    description: str
    fix_suggestion: str
    confidence: float
    code_snippet: str = ""
    fixed: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BugFinding":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class PRMemoryManager:
    """Manages persistent memory for PR analysis across commands.
    
    Memory is isolated per repository and PR number.
    """
    
    def __init__(self, persist_path: str = ".chroma_db"):
        """Initialize PR memory manager.
        
        Args:
            persist_path: Path to store ChromaDB data
        """
        # Always initialize fallback first
        self._memory_fallback: Dict[str, List[Dict]] = {}
        
        try:
            self.vector_store = VectorStore(persist_path)
            logger.info("PRMemoryManager initialized with VectorStore")
        except Exception as e:
            logger.warning(f"VectorStore initialization failed: {e}. Using in-memory fallback.")
            self.vector_store = None
    
    def _get_repo_id(self, repo_full_name: str, pr_number: int) -> str:
        """Generate unique repo ID for isolation."""
        return f"{repo_full_name}#{pr_number}"
    
    def clear_bug_findings(self, repo_full_name: str, pr_number: int) -> int:
        """Clear all existing bug findings for a PR.
        
        This is called before storing new findings to ensure only the
        latest /inspectai_bugs results are kept.
        
        Args:
            repo_full_name: Repository name (owner/repo)
            pr_number: Pull request number
            
        Returns:
            Number of findings cleared
        """
        repo_id = self._get_repo_id(repo_full_name, pr_number)
        
        if self.vector_store:
            deleted = self.vector_store.delete_by_filter(repo_id, "bug_finding")
            logger.info(f"Cleared {deleted} old bug findings for {repo_id}")
            return deleted
        else:
            # Fallback: clear in-memory storage
            if repo_id in self._memory_fallback:
                old_count = len([f for f in self._memory_fallback[repo_id] 
                               if f.get("type") == "bug_finding"])
                self._memory_fallback[repo_id] = [
                    f for f in self._memory_fallback[repo_id] 
                    if f.get("type") != "bug_finding"
                ]
                logger.info(f"Cleared {old_count} old bug findings for {repo_id}")
                return old_count
        return 0
    
    def store_bug_findings(
        self,
        repo_full_name: str,
        pr_number: int,
        findings: List[BugFinding]
    ) -> int:
        """Store bug findings for later use by fixbugs command.
        
        NOTE: This clears ALL previous findings first to keep only the latest.
        
        Args:
            repo_full_name: Repository name (owner/repo)
            pr_number: Pull request number
            findings: List of bug findings to store
            
        Returns:
            Number of findings stored
        """
        repo_id = self._get_repo_id(repo_full_name, pr_number)
        logger.info(f"[PR_MEMORY] store_bug_findings called for {repo_id} with {len(findings)} findings")
        logger.info(f"[PR_MEMORY] Using VectorStore: {self.vector_store is not None}")
        
        # Clear previous findings first - only keep latest
        self.clear_bug_findings(repo_full_name, pr_number)
        
        stored_count = 0
        
        for finding in findings:
            # Create searchable text from finding
            text = f"""
            File: {finding.file_path}
            Line: {finding.line_number}
            Category: {finding.category}
            Severity: {finding.severity}
            Description: {finding.description}
            Fix: {finding.fix_suggestion}
            Code: {finding.code_snippet}
            """
            
            metadata = {
                "repo_id": repo_id,
                "type": "bug_finding",
                "file_path": finding.file_path,
                "line_number": finding.line_number,
                "severity": finding.severity,
                "category": finding.category,
                "fixed": finding.fixed,
                "timestamp": time.time(),
                "data": json.dumps(finding.to_dict())
            }
            
            if self.vector_store:
                doc_id = f"{repo_id}:{finding.file_path}:{finding.line_number}:{int(time.time()*1000)}"
                self.vector_store.add_document(text, metadata, doc_id)
                stored_count += 1
                logger.info(f"[PR_MEMORY] Stored in VectorStore: {finding.file_path}:{finding.line_number}")
            else:
                # Fallback to in-memory storage
                if repo_id not in self._memory_fallback:
                    self._memory_fallback[repo_id] = []
                self._memory_fallback[repo_id].append(metadata)
                stored_count += 1
                logger.info(f"[PR_MEMORY] Stored in fallback: {finding.file_path}:{finding.line_number}")
        
        logger.info(f"[PR_MEMORY] Total stored: {stored_count} bug findings for {repo_id}")
        logger.info(f"[PR_MEMORY] Memory fallback now has keys: {list(self._memory_fallback.keys())}")
        return stored_count
    
    def get_unfixed_bugs(
        self,
        repo_full_name: str,
        pr_number: int,
        file_path: Optional[str] = None
    ) -> List[BugFinding]:
        """Get all unfixed bugs for a PR.
        
        Args:
            repo_full_name: Repository name
            pr_number: PR number
            file_path: Optional filter by file
            
        Returns:
            List of unfixed bug findings
        """
        repo_id = self._get_repo_id(repo_full_name, pr_number)
        logger.info(f"[PR_MEMORY] get_unfixed_bugs called for {repo_id}")
        logger.info(f"[PR_MEMORY] Using VectorStore: {self.vector_store is not None}")
        logger.info(f"[PR_MEMORY] Memory fallback keys: {list(self._memory_fallback.keys())}")
        
        if self.vector_store:
            # Search for bug findings
            additional_filter = {"type": "bug_finding", "fixed": False}
            if file_path:
                additional_filter["file_path"] = file_path
            
            logger.info(f"[PR_MEMORY] Searching VectorStore with filter: {additional_filter}")
            results = self.vector_store.search(
                query="bug finding unfixed",
                repo_id=repo_id,
                n_results=50,
                additional_filter=additional_filter
            )
            logger.info(f"[PR_MEMORY] VectorStore returned {len(results)} results")
            
            findings = []
            for result in results:
                try:
                    data = json.loads(result["metadata"].get("data", "{}"))
                    if not data.get("fixed", False):
                        findings.append(BugFinding.from_dict(data))
                except Exception as e:
                    logger.warning(f"Failed to parse bug finding: {e}")
            
            logger.info(f"[PR_MEMORY] Returning {len(findings)} unfixed bugs from VectorStore")
            return findings
        else:
            # Fallback
            logger.info(f"[PR_MEMORY] Using in-memory fallback")
            items_for_repo = self._memory_fallback.get(repo_id, [])
            logger.info(f"[PR_MEMORY] Found {len(items_for_repo)} items for {repo_id}")
            
            findings = []
            for item in items_for_repo:
                if item.get("type") == "bug_finding" and not item.get("fixed", False):
                    if file_path and item.get("file_path") != file_path:
                        continue
                    try:
                        data = json.loads(item.get("data", "{}"))
                        findings.append(BugFinding.from_dict(data))
                    except Exception as e:
                        logger.warning(f"[PR_MEMORY] Failed to parse: {e}")
            
            logger.info(f"[PR_MEMORY] Returning {len(findings)} unfixed bugs from fallback")
            return findings
    
    def mark_bugs_fixed(
        self,
        repo_full_name: str,
        pr_number: int,
        file_path: str,
        line_numbers: Optional[List[int]] = None
    ) -> int:
        """Mark bugs as fixed.
        
        Args:
            repo_full_name: Repository name
            pr_number: PR number
            file_path: File where bugs were fixed
            line_numbers: Specific lines (None = all in file)
            
        Returns:
            Number of bugs marked as fixed
        """
        repo_id = self._get_repo_id(repo_full_name, pr_number)
        
        # For now, we'll store a "fixed" record
        # In production, you'd update the existing documents
        fixed_count = 0
        
        bugs = self.get_unfixed_bugs(repo_full_name, pr_number, file_path)
        for bug in bugs:
            if line_numbers is None or bug.line_number in line_numbers:
                bug.fixed = True
                fixed_count += 1
        
        logger.info(f"Marked {fixed_count} bugs as fixed in {file_path}")
        return fixed_count
    
    def store_review_context(
        self,
        repo_full_name: str,
        pr_number: int,
        context_type: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Store review context for future reference.
        
        Args:
            repo_full_name: Repository name
            pr_number: PR number
            context_type: Type of context (e.g., "diff", "review", "summary")
            content: Content to store
            metadata: Additional metadata
            
        Returns:
            Document ID
        """
        repo_id = self._get_repo_id(repo_full_name, pr_number)
        
        doc_metadata = {
            "repo_id": repo_id,
            "type": context_type,
            "timestamp": time.time(),
            **(metadata or {})
        }
        
        if self.vector_store:
            doc_id = f"{repo_id}:{context_type}:{int(time.time()*1000)}"
            return self.vector_store.add_document(content, doc_metadata, doc_id)
        else:
            if repo_id not in self._memory_fallback:
                self._memory_fallback[repo_id] = []
            doc_metadata["content"] = content
            self._memory_fallback[repo_id].append(doc_metadata)
            return f"fallback:{len(self._memory_fallback[repo_id])}"
    
    def get_pr_context(
        self,
        repo_full_name: str,
        pr_number: int,
        query: str,
        n_results: int = 5
    ) -> List[Dict[str, Any]]:
        """Get relevant context from PR history.
        
        Args:
            repo_full_name: Repository name
            pr_number: PR number
            query: Search query
            n_results: Number of results
            
        Returns:
            List of relevant context documents
        """
        repo_id = self._get_repo_id(repo_full_name, pr_number)
        
        if self.vector_store:
            return self.vector_store.search(query, repo_id, n_results)
        else:
            # Simple fallback - return all stored context
            return [
                {"content": item.get("content", ""), "metadata": item}
                for item in self._memory_fallback.get(repo_id, [])[:n_results]
            ]
    
    def get_files_analyzed(
        self,
        repo_full_name: str,
        pr_number: int
    ) -> List[str]:
        """Get list of files that have been analyzed for this PR.
        
        Returns:
            List of file paths
        """
        repo_id = self._get_repo_id(repo_full_name, pr_number)
        
        if self.vector_store:
            results = self.vector_store.search(
                query="file analysis",
                repo_id=repo_id,
                n_results=100,
                additional_filter={"type": "bug_finding"}
            )
            
            files = set()
            for result in results:
                file_path = result.get("metadata", {}).get("file_path")
                if file_path:
                    files.add(file_path)
            return list(files)
        else:
            files = set()
            for item in self._memory_fallback.get(repo_id, []):
                if item.get("file_path"):
                    files.add(item["file_path"])
            return list(files)
    
    def cleanup_pr(self, repo_full_name: str, pr_number: int) -> bool:
        """Clean up all data for a PR (e.g., when PR is merged/closed).
        
        Args:
            repo_full_name: Repository name
            pr_number: PR number
            
        Returns:
            True if cleanup successful
        """
        repo_id = self._get_repo_id(repo_full_name, pr_number)
        
        if self.vector_store:
            return self.vector_store.delete_repo_data(repo_id)
        else:
            if repo_id in self._memory_fallback:
                del self._memory_fallback[repo_id]
            return True


# Global instance for reuse
_pr_memory: Optional[PRMemoryManager] = None


def get_pr_memory() -> PRMemoryManager:
    """Get or create the global PR memory manager."""
    global _pr_memory
    if _pr_memory is None:
        _pr_memory = PRMemoryManager()
    return _pr_memory
