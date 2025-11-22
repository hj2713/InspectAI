"""Research Agent for gathering and analyzing information."""
from typing import Any, Dict, List

from .base_agent import BaseAgent

class ResearchAgent(BaseAgent):
    def initialize(self) -> None:
        """Initialize research tools and LLM client."""
        cfg = self.config or {}
        use_local = cfg.get("use_local", False)
        if use_local:
            try:
                from ..llm.local_client import LocalLLMClient as LLMClient

                self.client = LLMClient(default_temperature=cfg.get("temperature", 0.7), default_max_tokens=cfg.get("max_tokens", 1024))
                return
            except Exception as e:
                print("Warning: failed to initialize local LLM client:", e)
                print("Falling back to OpenAI client. If you want only local, disable fallback in config.")

        # fallback to OpenAI client
        from ..llm.client import LLMClient
        self.client = LLMClient(default_temperature=cfg.get("temperature", 0.7), default_max_tokens=cfg.get("max_tokens", 1024))

    def process(self, query: str) -> Dict[str, Any]:
        """
        Process a research query and return a concise summary and sources.
        """
        system = {
            "role": "system",
            "content": "You are a research assistant. Give concise, factual summaries and list possible sources/URLs when available."
        }
        user = {
            "role": "user",
            "content": f"Research the following topic and provide: (1) a short summary (3-6 sentences); (2) 5 key points; (3) any reliable sources or URLs if available. Topic: {query}"
        }

        resp = self.client.chat([system, user], model=self.config.get("model"), temperature=self.config.get("temperature"), max_tokens=self.config.get("max_tokens"))
        return {"status": "ok", "query": query, "result": resp}

    def cleanup(self) -> None:
        """Cleanup resources if needed."""
        return None