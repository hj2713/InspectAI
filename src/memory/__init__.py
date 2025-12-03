# Memory package
from .agent_memory import AgentMemory, SharedMemory, Message, TaskContext
from .pr_memory import PRMemoryManager, BugFinding, get_pr_memory
from .vector_store import VectorStore  # Legacy ChromaDB-only store
from .supabase_vector_store import SupabaseVectorStore, get_vector_store  # Unified store (recommended)

__all__ = [
    "AgentMemory", 
    "SharedMemory", 
    "Message", 
    "TaskContext",
    "PRMemoryManager",
    "BugFinding",
    "get_pr_memory",
    "VectorStore",  # Legacy - use get_vector_store() instead
    "SupabaseVectorStore",  # Unified store with Supabase + ChromaDB fallback
    "get_vector_store"  # Recommended: returns unified store instance
]
