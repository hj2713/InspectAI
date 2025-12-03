"""Unified Vector Store using Supabase pgvector.

This module migrates from ChromaDB to Supabase pgvector for:
1. Unified storage with feedback system
2. Better scalability and persistence
3. Reduced dependencies

Maintains the same API as the original VectorStore for backward compatibility.
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
    import openai
    SUPABASE_AVAILABLE = True
except ImportError:
    logger.warning("supabase-py not installed - using in-memory fallback for vector store")
    SUPABASE_AVAILABLE = False


class SupabaseVectorStore:
    """Multi-tenant vector store using Supabase pgvector.
    
    This is a drop-in replacement for the ChromaDB-based VectorStore,
    using Supabase's pgvector extension for similarity search.
    """
    
    # Table name for vector documents (separate from review_comments)
    TABLE_NAME = "vector_documents"
    
    def __init__(self):
        """Initialize Supabase client."""
        self.client: Optional[Client] = None
        self.enabled = False
        self._memory_store: Dict[str, Dict] = {}  # Fallback storage
        
        if not SUPABASE_AVAILABLE:
            logger.info("SupabaseVectorStore using in-memory fallback")
            return
        
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")
        
        if not supabase_url or not supabase_key:
            logger.warning("Supabase credentials not found. Using in-memory fallback.")
            return
        
        try:
            self.client = create_client(supabase_url, supabase_key)
            self.enabled = True
            openai.api_key = os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY")
            logger.info("SupabaseVectorStore initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
            self.client = None
    
    def _get_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding for text using OpenAI.
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats (embedding vector) or None on error
        """
        if not os.getenv("OPENAI_API_KEY"):
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
        
        # Use in-memory fallback if Supabase not available
        if not self.enabled:
            self._memory_store[doc_id] = {
                "text": text,
                "metadata": metadata,
                "created_at": datetime.utcnow().isoformat()
            }
            logger.debug(f"Added document {doc_id} to in-memory store")
            return doc_id
        
        try:
            # Generate embedding
            embedding = self._get_embedding(text)
            
            # Prepare metadata as JSON
            metadata_json = json.dumps(metadata)
            
            # Insert into Supabase
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
            logger.debug(f"Added document {doc_id} to Supabase vector store")
            return doc_id
            
        except Exception as e:
            logger.error(f"Failed to add document to vector store: {e}")
            # Fallback to memory
            self._memory_store[doc_id] = {
                "text": text,
                "metadata": metadata
            }
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
        
        # Use in-memory fallback if Supabase not available
        if not self.enabled:
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
        
        try:
            # Generate query embedding
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
                        "distance": 0.5  # Arbitrary distance for text search
                    })
                return formatted_results
                
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []

    def delete_repo_data(self, repo_id: str) -> bool:
        """Delete all data for a repository.
        
        Args:
            repo_id: Repository ID to delete
            
        Returns:
            True if successful
        """
        # In-memory fallback
        if not self.enabled:
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
            result = self.client.table(self.TABLE_NAME) \
                .delete() \
                .eq("repo_id", repo_id) \
                .execute()
            
            logger.info(f"Deleted documents for {repo_id} from Supabase")
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
        if not self.enabled:
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
            result = self.client.table(self.TABLE_NAME) \
                .delete() \
                .eq("repo_id", repo_id) \
                .eq("doc_type", type_filter) \
                .execute()
            
            deleted = len(result.data) if result.data else 0
            logger.info(f"Deleted {deleted} {type_filter} documents for {repo_id}")
            return deleted
        except Exception as e:
            logger.error(f"Failed to delete by filter: {e}")
            return 0

    def cleanup_inactive_repos(self, retention_hours: int = 24) -> int:
        """Delete data for repositories inactive for retention_hours.
        
        Args:
            retention_hours: Hours of inactivity before deletion
            
        Returns:
            Number of repositories cleaned up
        """
        if not self.enabled:
            return 0
        
        try:
            cutoff_time = (datetime.utcnow() - timedelta(hours=retention_hours)).isoformat()
            
            # Delete old documents
            result = self.client.table(self.TABLE_NAME) \
                .delete() \
                .lt("created_at", cutoff_time) \
                .execute()
            
            deleted = len(result.data) if result.data else 0
            logger.info(f"Cleaned up {deleted} old documents (older than {retention_hours}h)")
            return deleted
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
            return 0


# Singleton instance
_vector_store = None


def get_vector_store() -> SupabaseVectorStore:
    """Get or create singleton vector store instance."""
    global _vector_store
    if _vector_store is None:
        _vector_store = SupabaseVectorStore()
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
