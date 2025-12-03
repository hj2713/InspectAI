"""Unified Vector Store using Supabase pgvector with ChromaDB fallback.

This module provides a unified vector store that:
1. Tries Supabase pgvector first (cloud-native, scalable)
2. Falls back to ChromaDB if Supabase unavailable (local, no external deps)
3. Uses in-memory store as last resort

Maintains the same API for backward compatibility.
"""
import os
import uuid
import json
import hashlib
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

from ..utils.logger import get_logger

logger = get_logger(__name__)

# Try to import supabase
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    logger.info("supabase-py not installed - will try ChromaDB fallback")
    SUPABASE_AVAILABLE = False
    Client = None

# Try to import openai for embeddings
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    logger.info("openai not installed - Supabase vector search will be limited")
    OPENAI_AVAILABLE = False
    openai = None

# Try to import ChromaDB as fallback
try:
    import chromadb
    from chromadb.utils import embedding_functions
    CHROMADB_AVAILABLE = True
except ImportError:
    logger.info("chromadb not installed - will use in-memory fallback if Supabase unavailable")
    CHROMADB_AVAILABLE = False
    chromadb = None
    embedding_functions = None


class SupabaseVectorStore:
    """Multi-tenant vector store using Supabase pgvector with ChromaDB fallback.
    
    Priority order:
    1. Supabase pgvector (if credentials available)
    2. ChromaDB (if installed and Supabase unavailable)
    3. In-memory store (last resort)
    """
    
    # Table name for vector documents
    TABLE_NAME = "vector_documents"
    
    def __init__(self, persist_path: str = ".chroma_db"):
        """Initialize vector store with Supabase primary, ChromaDB fallback.
        
        Args:
            persist_path: Path for ChromaDB persistence (used if falling back)
        """
        self.client: Optional[Client] = None
        self.supabase_enabled = False
        self.chromadb_enabled = False
        self._memory_store: Dict[str, Dict] = {}  # Last resort fallback
        self._chroma_client = None
        self._chroma_collection = None
        
        # Try Supabase first
        if SUPABASE_AVAILABLE:
            supabase_url = os.getenv("SUPABASE_URL")
            supabase_key = os.getenv("SUPABASE_KEY")
            
            if supabase_url and supabase_key:
                try:
                    self.client = create_client(supabase_url, supabase_key)
                    self.supabase_enabled = True
                    logger.info("✓ VectorStore using Supabase pgvector (primary)")
                except Exception as e:
                    logger.warning(f"Supabase init failed: {e}. Trying ChromaDB fallback...")
            else:
                logger.info("Supabase credentials not found. Trying ChromaDB fallback...")
        
        # Fall back to ChromaDB if Supabase not available
        if not self.supabase_enabled and CHROMADB_AVAILABLE:
            try:
                self._chroma_client = chromadb.PersistentClient(path=persist_path)
                self._chroma_embedding_fn = embedding_functions.DefaultEmbeddingFunction()
                self._chroma_collection = self._chroma_client.get_or_create_collection(
                    name="inspectai_memory",
                    embedding_function=self._chroma_embedding_fn
                )
                self.chromadb_enabled = True
                logger.info(f"✓ VectorStore using ChromaDB fallback at {persist_path}")
            except Exception as e:
                logger.warning(f"ChromaDB init failed: {e}. Using in-memory fallback...")
        
        # Log final state
        if not self.supabase_enabled and not self.chromadb_enabled:
            logger.warning("⚠ VectorStore using in-memory fallback (data will not persist)")
    
    @property
    def enabled(self) -> bool:
        """Check if any persistent store is enabled."""
        return self.supabase_enabled or self.chromadb_enabled
    
    def _get_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding for text using OpenAI (for Supabase only).
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats (embedding vector) or None on error
        """
        if not OPENAI_AVAILABLE or not os.getenv("OPENAI_API_KEY"):
            return None
        
        try:
            response = openai.embeddings.create(
                model="text-embedding-ada-002",
                input=text[:8000]  # Limit to 8K chars
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return None

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
        
        # Priority 1: Supabase
        if self.supabase_enabled:
            try:
                embedding = self._get_embedding(text)
                metadata_json = json.dumps(metadata)
                
                data = {
                    "id": doc_id,
                    "content": text,
                    "metadata": metadata_json,
                    "repo_id": metadata.get("repo_id", "unknown"),
                    "doc_type": metadata.get("type", "general"),
                    "embedding": embedding,
                    "created_at": datetime.utcnow().isoformat()
                }
                
                self.client.table(self.TABLE_NAME).upsert(data).execute()
                logger.debug(f"Added document {doc_id} to Supabase")
                return doc_id
            except Exception as e:
                logger.error(f"Supabase add failed: {e}. Trying ChromaDB fallback...")
        
        # Priority 2: ChromaDB fallback
        if self.chromadb_enabled and self._chroma_collection:
            try:
                self._chroma_collection.add(
                    documents=[text],
                    metadatas=[metadata],
                    ids=[doc_id]
                )
                logger.debug(f"Added document {doc_id} to ChromaDB")
                return doc_id
            except Exception as e:
                logger.error(f"ChromaDB add failed: {e}. Using in-memory fallback...")
        
        # Priority 3: In-memory fallback
        self._memory_store[doc_id] = {
            "text": text,
            "metadata": metadata,
            "created_at": datetime.utcnow().isoformat()
        }
        logger.debug(f"Added document {doc_id} to in-memory store")
        return doc_id

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
        
        # Priority 1: Supabase
        if self.supabase_enabled:
            try:
                query_embedding = self._get_embedding(query)
                
                if query_embedding:
                    # Use Supabase RPC function for similarity search
                    result = self.client.rpc(
                        "match_vector_documents",
                        {
                            "query_embedding": query_embedding,
                            "match_threshold": 0.7,
                            "match_count": n_results,
                            "repo_filter": repo_id
                        }
                    ).execute()
                    
                    formatted_results = []
                    for row in result.data or []:
                        metadata = json.loads(row.get("metadata", "{}"))
                        formatted_results.append({
                            "id": row.get("id"),
                            "content": row.get("content"),
                            "metadata": metadata,
                            "distance": 1 - row.get("similarity", 0)
                        })
                    return formatted_results
                else:
                    # Fall back to text search if no embedding
                    result = self.client.table(self.TABLE_NAME) \
                        .select("*") \
                        .eq("repo_id", repo_id) \
                        .ilike("content", f"%{query}%") \
                        .limit(n_results) \
                        .execute()
                    
                    formatted_results = []
                    for row in result.data or []:
                        metadata = json.loads(row.get("metadata", "{}"))
                        formatted_results.append({
                            "id": row.get("id"),
                            "content": row.get("content"),
                            "metadata": metadata,
                            "distance": 0.5
                        })
                    return formatted_results
            except Exception as e:
                logger.error(f"Supabase search failed: {e}. Trying ChromaDB fallback...")
        
        # Priority 2: ChromaDB fallback
        if self.chromadb_enabled and self._chroma_collection:
            try:
                # Build where filter
                where_filter = {"repo_id": repo_id}
                if additional_filter:
                    where_filter.update(additional_filter)
                
                results = self._chroma_collection.query(
                    query_texts=[query],
                    n_results=n_results,
                    where=where_filter
                )
                
                formatted_results = []
                if results and results.get("documents"):
                    for i, doc in enumerate(results["documents"][0]):
                        formatted_results.append({
                            "id": results["ids"][0][i] if results.get("ids") else str(i),
                            "content": doc,
                            "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
                            "distance": results["distances"][0][i] if results.get("distances") else 0.0
                        })
                return formatted_results
            except Exception as e:
                logger.error(f"ChromaDB search failed: {e}. Using in-memory fallback...")
        
        # Priority 3: In-memory fallback
        results = []
        for doc_id, doc in self._memory_store.items():
            if doc["metadata"].get("repo_id") == repo_id:
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

    def delete_repo_data(self, repo_id: str) -> bool:
        """Delete all data for a repository.
        
        Args:
            repo_id: Repository ID to delete
            
        Returns:
            True if successful
        """
        success = False
        
        # Try Supabase
        if self.supabase_enabled:
            try:
                self.client.table(self.TABLE_NAME) \
                    .delete() \
                    .eq("repo_id", repo_id) \
                    .execute()
                logger.info(f"Deleted documents for {repo_id} from Supabase")
                success = True
            except Exception as e:
                logger.error(f"Supabase delete failed: {e}")
        
        # Try ChromaDB
        if self.chromadb_enabled and self._chroma_collection:
            try:
                self._chroma_collection.delete(where={"repo_id": repo_id})
                logger.info(f"Deleted documents for {repo_id} from ChromaDB")
                success = True
            except Exception as e:
                logger.error(f"ChromaDB delete failed: {e}")
        
        # In-memory cleanup
        deleted = 0
        to_delete = [
            doc_id for doc_id, doc in self._memory_store.items()
            if doc["metadata"].get("repo_id") == repo_id
        ]
        for doc_id in to_delete:
            del self._memory_store[doc_id]
            deleted += 1
        if deleted > 0:
            logger.info(f"Deleted {deleted} documents for {repo_id} (in-memory)")
        
        return success or deleted > 0

    def delete_by_filter(self, repo_id: str, type_filter: str) -> int:
        """Delete documents matching type filter within a repo.
        
        Args:
            repo_id: Repository ID
            type_filter: Type of documents to delete (e.g., 'bug_finding')
            
        Returns:
            Number of documents deleted
        """
        total_deleted = 0
        
        # Try Supabase
        if self.supabase_enabled:
            try:
                result = self.client.table(self.TABLE_NAME) \
                    .delete() \
                    .eq("repo_id", repo_id) \
                    .eq("doc_type", type_filter) \
                    .execute()
                deleted = len(result.data) if result.data else 0
                total_deleted += deleted
                logger.info(f"Deleted {deleted} {type_filter} docs for {repo_id} from Supabase")
            except Exception as e:
                logger.error(f"Supabase delete_by_filter failed: {e}")
        
        # Try ChromaDB
        if self.chromadb_enabled and self._chroma_collection:
            try:
                self._chroma_collection.delete(
                    where={"$and": [{"repo_id": repo_id}, {"type": type_filter}]}
                )
                logger.info(f"Deleted {type_filter} docs for {repo_id} from ChromaDB")
                total_deleted += 1  # ChromaDB doesn't return count
            except Exception as e:
                logger.error(f"ChromaDB delete_by_filter failed: {e}")
        
        # In-memory cleanup
        to_delete = [
            doc_id for doc_id, doc in self._memory_store.items()
            if doc["metadata"].get("repo_id") == repo_id 
            and doc["metadata"].get("type") == type_filter
        ]
        for doc_id in to_delete:
            del self._memory_store[doc_id]
            total_deleted += 1
        
        return total_deleted

    def cleanup_inactive_repos(self, retention_hours: int = 24) -> int:
        """Delete data for repositories inactive for retention_hours.
        
        Args:
            retention_hours: Hours of inactivity before deletion
            
        Returns:
            Number of documents cleaned up
        """
        total_deleted = 0
        cutoff_time = (datetime.utcnow() - timedelta(hours=retention_hours)).isoformat()
        
        # Supabase cleanup
        if self.supabase_enabled:
            try:
                result = self.client.table(self.TABLE_NAME) \
                    .delete() \
                    .lt("created_at", cutoff_time) \
                    .execute()
                deleted = len(result.data) if result.data else 0
                total_deleted += deleted
                logger.info(f"Cleaned up {deleted} old documents from Supabase")
            except Exception as e:
                logger.error(f"Supabase cleanup failed: {e}")
        
        # Note: ChromaDB doesn't have built-in TTL, would need custom tracking
        # In-memory cleanup based on created_at
        to_delete = [
            doc_id for doc_id, doc in self._memory_store.items()
            if doc.get("created_at", "") < cutoff_time
        ]
        for doc_id in to_delete:
            del self._memory_store[doc_id]
            total_deleted += 1
        
        return total_deleted


# Singleton instance
_vector_store = None


def get_vector_store(persist_path: str = ".chroma_db") -> SupabaseVectorStore:
    """Get or create singleton vector store instance.
    
    Args:
        persist_path: Path for ChromaDB persistence (used if falling back)
        
    Returns:
        SupabaseVectorStore instance (with Supabase or ChromaDB backend)
    """
    global _vector_store
    if _vector_store is None:
        _vector_store = SupabaseVectorStore(persist_path=persist_path)
    return _vector_store


# SQL to add to Supabase schema for this module:
"""
-- Table for vector documents (add to supabase_schema.sql)
CREATE TABLE IF NOT EXISTS vector_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    repo_id TEXT NOT NULL,
    doc_type TEXT DEFAULT 'general',
    embedding VECTOR(1536),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_vector_documents_repo ON vector_documents (repo_id);
CREATE INDEX IF NOT EXISTS idx_vector_documents_type ON vector_documents (doc_type);
CREATE INDEX IF NOT EXISTS idx_vector_documents_created ON vector_documents (created_at DESC);

-- Vector similarity index
CREATE INDEX IF NOT EXISTS idx_vector_documents_embedding ON vector_documents 
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Function for similarity search
CREATE OR REPLACE FUNCTION match_vector_documents(
    query_embedding VECTOR(1536),
    match_threshold FLOAT DEFAULT 0.7,
    match_count INT DEFAULT 5,
    repo_filter TEXT DEFAULT NULL
)
RETURNS TABLE (
    id UUID,
    content TEXT,
    metadata JSONB,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        vd.id,
        vd.content,
        vd.metadata,
        1 - (vd.embedding <=> query_embedding) AS similarity
    FROM vector_documents vd
    WHERE 
        (repo_filter IS NULL OR vd.repo_id = repo_filter)
        AND vd.embedding IS NOT NULL
        AND 1 - (vd.embedding <=> query_embedding) > match_threshold
    ORDER BY vd.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
"""
