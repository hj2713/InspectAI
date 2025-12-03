"""Base agent class that defines the common interface for all agents."""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

class BaseAgent(ABC):
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.initialize()
    
    @abstractmethod
    def initialize(self) -> None:
        """Initialize the agent with necessary setup."""
        pass
