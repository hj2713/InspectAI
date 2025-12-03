"""Agent Memory System for maintaining conversation history and context.

This module provides memory capabilities for agents to:
1. Store conversation history
2. Maintain context across interactions
3. Support different memory strategies

Usage:
    from src.memory.agent_memory import AgentMemory
    
    memory = AgentMemory(max_history=10)
    memory.add_message("user", "Analyze this code")
    memory.add_message("assistant", "Here's my analysis...")
    
    # Get conversation history
    history = memory.get_history()
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Message:
    """Represents a single message in conversation history."""
    role: str  # user, assistant, system
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            metadata=data.get("metadata", {})
        )


@dataclass
class TaskContext:
    """Context for a specific task/session."""
    task_id: str
    task_type: str
    started_at: datetime = field(default_factory=datetime.now)
    input_data: Dict[str, Any] = field(default_factory=dict)
    intermediate_results: Dict[str, Any] = field(default_factory=dict)

class AgentMemory:
    """Memory system for maintaining agent conversation history."""
    
    def __init__(
        self,
        max_history: int = 50,
        persist_path: Optional[Path] = None
    ):
        """Initialize agent memory.
        
        Args:
            max_history: Maximum number of messages to keep in history
            persist_path: Optional path to persist memory to disk
        """
        self.max_history = max_history
        self.persist_path = persist_path
        self._history: deque[Message] = deque(maxlen=max_history)
        self._contexts: Dict[str, TaskContext] = {}
        self._summaries: List[str] = []  # Compressed old context
        
        if persist_path and persist_path.exists():
            self._load_from_disk()
    
    def add_message(
        self,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Add a message to the conversation history.
        
        Args:
            role: Message role (user, assistant, system)
            content: Message content
            metadata: Optional metadata (agent name, task info, etc.)
        """
        message = Message(
            role=role,
            content=content,
            metadata=metadata or {}
        )
        self._history.append(message)
        logger.debug(f"Added {role} message to memory (history size: {len(self._history)})")
        
        if self.persist_path:
            self._save_to_disk()
    
    def add_user_message(self, content: str, **metadata) -> None:
        """Convenience method to add user message."""
        self.add_message("user", content, metadata)
    
    def add_assistant_message(self, content: str, agent_name: Optional[str] = None, **metadata) -> None:
        """Convenience method to add assistant message."""
        if agent_name:
            metadata["agent"] = agent_name
        self.add_message("assistant", content, metadata)
    
    def add_system_message(self, content: str, **metadata) -> None:
        """Convenience method to add system message."""
        self.add_message("system", content, metadata)
    
    def get_history(
        self,
        n: Optional[int] = None,
        roles: Optional[List[str]] = None
    ) -> List[Dict[str, str]]:
        """Get conversation history in chat format.
        
        Args:
            n: Number of recent messages (None for all)
            roles: Filter by specific roles
            
        Returns:
            List of message dicts compatible with LLM chat format
        """
        messages = list(self._history)
        
        if roles:
            messages = [m for m in messages if m.role in roles]
        
        if n is not None:
            messages = messages[-n:]
        
        return [{"role": m.role, "content": m.content} for m in messages]
    
    def get_context_string(self, max_length: int = 2000) -> str:
        """Get a condensed context string for prompts.
        
        Args:
            max_length: Maximum character length
            
        Returns:
            Condensed conversation context
        """
        history = self.get_history()
        context_parts = []
        
        for msg in reversed(history):
            part = f"{msg['role'].upper()}: {msg['content']}"
            context_parts.insert(0, part)
            
            if len("\n".join(context_parts)) > max_length:
                context_parts.pop(0)
                break
        
        return "\n".join(context_parts)
    
    def start_task(self, task_id: str, task_type: str, input_data: Dict[str, Any]) -> TaskContext:
        """Start a new task context.
        
        Args:
            task_id: Unique task identifier
            task_type: Type of task (code_improvement, bug_fix, etc.)
            input_data: Initial input for the task
            
        Returns:
            TaskContext object
        """
        context = TaskContext(
            task_id=task_id,
            task_type=task_type,
            input_data=input_data
        )
        self._contexts[task_id] = context
        logger.debug(f"Started task context: {task_id} ({task_type})")
        return context
    
    def get_task_context(self, task_id: str) -> Optional[TaskContext]:
        """Get task context by ID."""
        return self._contexts.get(task_id)
    
    def add_task_result(self, task_id: str, agent_name: str, result: Any) -> None:
        """Add an intermediate result to a task context."""
        if task_id in self._contexts:
            self._contexts[task_id].add_result(agent_name, result)
    
    def clear_history(self) -> None:
        """Clear conversation history."""
        self._history.clear()
        logger.info("Cleared memory history")
    
    def clear_contexts(self) -> None:
        """Clear all task contexts."""
        self._contexts.clear()
        logger.info("Cleared task contexts")
    
    def summarize_and_compress(self, keep_recent: int = 5) -> str:
        """Compress old history into a summary.
        
        This is useful for long conversations to maintain context
        while staying within token limits.
        
        Args:
            keep_recent: Number of recent messages to keep intact
            
        Returns:
            Summary of compressed messages
        """
        if len(self._history) <= keep_recent:
            return ""
        
        # Get messages to summarize
        to_summarize = list(self._history)[:-keep_recent]
        
        # Create a simple summary
        summary_parts = []
        for msg in to_summarize:
            if msg.role == "user":
                summary_parts.append(f"User asked: {msg.content[:100]}...")
            elif msg.role == "assistant":
                agent = msg.metadata.get("agent", "Agent")
                summary_parts.append(f"{agent} responded: {msg.content[:100]}...")
        
        summary = "Previous conversation summary:\n" + "\n".join(summary_parts)
        self._summaries.append(summary)
        
        # Keep only recent messages
        recent = list(self._history)[-keep_recent:]
        self._history.clear()
        for msg in recent:
            self._history.append(msg)
        
        logger.info(f"Compressed {len(to_summarize)} messages into summary")
        return summary
    
    def _save_to_disk(self) -> None:
        """Persist memory to disk."""
        if not self.persist_path:
            return
        
        data = {
            "history": [m.to_dict() for m in self._history],
            "summaries": self._summaries
        }
        
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.persist_path, "w") as f:
            json.dump(data, f, indent=2)
    
    def _load_from_disk(self) -> None:
        """Load memory from disk."""
        if not self.persist_path or not self.persist_path.exists():
            return
        
        try:
            with open(self.persist_path, "r") as f:
                data = json.load(f)
            
            self._history.clear()
            for msg_data in data.get("history", []):
                self._history.append(Message.from_dict(msg_data))
            
            self._summaries = data.get("summaries", [])
            logger.info(f"Loaded {len(self._history)} messages from disk")
        except Exception as e:
            logger.error(f"Failed to load memory from disk: {e}")


class SharedMemory:
    """Shared memory for communication between agents."""
    
    def __init__(self):
        self._data: Dict[str, Any] = {}
        self._subscribers: Dict[str, List[callable]] = {}
    
    def set(self, key: str, value: Any) -> None:
        """Set a value in shared memory."""
        self._data[key] = value
        
        # Notify subscribers
        if key in self._subscribers:
            for callback in self._subscribers[key]:
                try:
                    callback(key, value)
                except Exception as e:
                    logger.error(f"Subscriber callback error: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from shared memory."""
        return self._data.get(key, default)
    
    def subscribe(self, key: str, callback: callable) -> None:
        """Subscribe to changes on a key."""
        if key not in self._subscribers:
            self._subscribers[key] = []
        self._subscribers[key].append(callback)
    
    def clear(self) -> None:
        """Clear all shared memory."""
        self._data.clear()
