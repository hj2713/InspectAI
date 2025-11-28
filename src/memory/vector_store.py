"""Vector Store implementation using ChromaDB for multi-tenant memory.

This module provides a wrapper around ChromaDB to store and retrieve
embeddings with strict metadata filtering for multi-tenancy.

ChromaDB is optional - if not installed, a simple in-memory fallback is used.
"""
import os
import uuid
from typing import Any, Dict, List, Optional
from pathlib import Path

from ..utils.logger import get_logger

logger = get_logger(__name__)

# Try to import chromadb - it's optional
try:
    import chromadb
    from chromadb.utils import embedding_functions
    CHROMADB_AVAILABLE = True
except ImportError:
    logger.warning("chromadb not installed - using in-memory fallback for vector store")
    CHROMADB_AVAILABLE = False
    chromadb = None
    embedding_functions = None


class VectorStore:
    """Multi-tenant vector store using ChromaDB (with in-memory fallback)."""
    
    def __init__(self, persist_path: str = ".chroma_db"):
        """Initialize vector store.
        
        Args:
            persist_path: Path to store ChromaDB data
        """
        self.persist_path = persist_path
        self.client = None
        self.collection = None
        self._memory_store: Dict[str, Dict] = {}  # Fallback storage
        
        if not CHROMADB_AVAILABLE:
            logger.info("VectorStore using in-memory fallback (chromadb not available)")
            return
        
        # Initialize ChromaDB client
        try:
            self.client = chromadb.PersistentClient(path=persist_path)
            
            # Use default embedding function (all-MiniLM-L6-v2)
            # In production, you might want to use OpenAI embeddings
            self.embedding_fn = embedding_functions.DefaultEmbeddingFunction()
            
            # Get or create collection
            self.collection = self.client.get_or_create_collection(
                name="inspectai_memory",
                embedding_function=self.embedding_fn
            )
            logger.info(f"VectorStore initialized at {persist_path}")
            
        except Exception as e:
            logger.error(f"Failed to initialize VectorStore: {e}")
            raise

    def add_document(
        self,
        text: str,
        metadata: Dict[str, Any],
        doc_id: Optional[str] = None
    ) -> str:
        """Add a document to the store.
        
        Args:
            text: Text content to embed
            metadata: Metadata for filtering (MUST include repo_id)
            doc_id: Optional unique ID
            
        Returns:
            Document ID
        """
        if not text:
            return ""
            
        if "repo_id" not in metadata:
            logger.warning("Adding document without repo_id metadata! This breaks isolation.")
        
        doc_id = doc_id or str(uuid.uuid4())
        
        # Use in-memory fallback if chromadb not available
        if not self.collection:
            self._memory_store[doc_id] = {
                "text": text,
                "metadata": metadata
            }
            logger.debug(f"Added document {doc_id} to in-memory store")
            return doc_id
        
        try:
            self.collection.add(
                documents=[text],
                metadatas=[metadata],
                ids=[doc_id]
            )
            self._update_activity(metadata.get("repo_id", "unknown"))
            logger.debug(f"Added document {doc_id} to vector store")
            return doc_id
            
        except Exception as e:
            logger.error(f"Failed to add document to vector store: {e}")
            return ""

    def search(
        self,
        query: str,
        repo_id: str,
        n_results: int = 5,
        additional_filter: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Search for relevant documents with STRICT isolation.
        
        Args:
            query: Search query
            repo_id: Repository ID to restrict search to
            n_results: Number of results to return
            additional_filter: Optional extra metadata filters
            
        Returns:
            List of result dicts with 'content', 'metadata', 'distance'
        """
        if not query:
            return []
        
        # Use in-memory fallback if chromadb not available
        if not self.collection:
            results = []
            for doc_id, doc in self._memory_store.items():
                if doc["metadata"].get("repo_id") == repo_id:
                    # Check additional filters
                    if additional_filter:
                        match = all(
                            doc["metadata"].get(k) == v 
                            for k, v in additional_filter.items()
                        )
                        if not match:
                            continue
                    results.append({
                        "id": doc_id,
                        "content": doc["text"],
                        "metadata": doc["metadata"],
                        "distance": 0.0
                    })
            return results[:n_results]
            
        self._update_activity(repo_id)
            
        # Construct filter: MUST match repo_id
        where_filter = {"repo_id": repo_id}
        
        if additional_filter:
            # Combine filters
            where_filter = {
                "$and": [
                    {"repo_id": repo_id},
                    additional_filter
                ]
            }
            
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where_filter
            )
            
            # Format results
            formatted_results = []
            if results["ids"]:
                for i in range(len(results["ids"][0])):
                    formatted_results.append({
                        "id": results["ids"][0][i],
                        "content": results["documents"][0][i],
                        "metadata": results["metadatas"][0][i],
                        "distance": results["distances"][0][i] if results["distances"] else 0.0
                    })
            
            return formatted_results
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []

    def _update_activity(self, repo_id: str) -> None:
        """Update last accessed timestamp for a repository."""
        import json
        import time
        
        activity_file = Path(self.persist_path) / "repo_activity.json"
        
        try:
            # Load existing activity
            activity = {}
            if activity_file.exists():
                with open(activity_file, "r") as f:
                    activity = json.load(f)
            
            # Update timestamp
            activity[repo_id] = time.time()
            
            # Save back
            with open(activity_file, "w") as f:
                json.dump(activity, f)
                
        except Exception as e:
            logger.warning(f"Failed to update repo activity: {e}")

    def cleanup_inactive_repos(self, retention_hours: int = 24) -> int:
        """Delete data for repositories inactive for retention_hours.
        
        Args:
            retention_hours: Hours of inactivity before deletion
            
        Returns:
            Number of repositories cleaned up
        """
        import json
        import time
        
        activity_file = Path(self.persist_path) / "repo_activity.json"
        if not activity_file.exists():
            return 0
            
        cleaned_count = 0
        current_time = time.time()
        retention_seconds = retention_hours * 3600
        
        try:
            with open(activity_file, "r") as f:
                activity = json.load(f)
            
            repos_to_delete = []
            for repo_id, last_active in activity.items():
                if current_time - last_active > retention_seconds:
                    repos_to_delete.append(repo_id)
            
            for repo_id in repos_to_delete:
                logger.info(f"Cleaning up inactive repo: {repo_id}")
                if self.delete_repo_data(repo_id):
                    del activity[repo_id]
                    cleaned_count += 1
            
            # Save updated activity
            with open(activity_file, "w") as f:
                json.dump(activity, f)
                
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
            return 0

    def delete_repo_data(self, repo_id: str) -> bool:
        """Delete all data for a repository.
        
        Args:
            repo_id: Repository ID to delete
            
        Returns:
            True if successful
        """
        # In-memory fallback
        if not self.collection:
            deleted = 0
            to_delete = [
                doc_id for doc_id, doc in self._memory_store.items()
                if doc["metadata"].get("repo_id") == repo_id
            ]
            for doc_id in to_delete:
                del self._memory_store[doc_id]
                deleted += 1
            logger.info(f"Deleted {deleted} documents for {repo_id} (in-memory)")
            return True
        
        try:
            # Get all document IDs for this repo
            results = self.collection.get(
                where={"repo_id": repo_id}
            )
            
            if results["ids"]:
                self.collection.delete(ids=results["ids"])
                logger.info(f"Deleted {len(results['ids'])} documents for {repo_id}")
            
            return True
        except Exception as e:
            logger.error(f"Failed to delete repo data: {e}")
            return False

    def delete_by_filter(self, repo_id: str, type_filter: str) -> int:
        """Delete documents matching type filter within a repo.
        
        Args:
            repo_id: Repository ID
            type_filter: Type of documents to delete (e.g., 'bug_finding')
            
        Returns:
            Number of documents deleted
        """
        # In-memory fallback
        if not self.collection:
            deleted = 0
            to_delete = [
                doc_id for doc_id, doc in self._memory_store.items()
                if doc["metadata"].get("repo_id") == repo_id 
                and doc["metadata"].get("type") == type_filter
            ]
            for doc_id in to_delete:
                del self._memory_store[doc_id]
                deleted += 1
            logger.info(f"Deleted {deleted} {type_filter} documents for {repo_id} (in-memory)")
            return deleted
        
        try:
            # Get matching documents
            results = self.collection.get(
                where={
                    "$and": [
                        {"repo_id": repo_id},
                        {"type": type_filter}
                    ]
                }
            )
            
            if results["ids"]:
                self.collection.delete(ids=results["ids"])
                logger.info(f"Deleted {len(results['ids'])} {type_filter} documents for {repo_id}")
                return len(results["ids"])
            
            return 0
        except Exception as e:
            logger.error(f"Failed to delete by filter: {e}")
            return 0
