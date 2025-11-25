"""Code Analysis Agent for understanding and analyzing code."""
from typing import Any, Dict, List

from .base_agent import BaseAgent


class CodeAnalysisAgent(BaseAgent):
    def initialize(self) -> None:
        """Initialize code analysis LLM client."""
        cfg = self.config or {}
        use_local = cfg.get("use_local", False)
        provider = cfg.get("provider", "openai")

        if use_local:
            try:
                from ..llm.local_client import LocalLLMClient as LLMClient

                self.client = LLMClient(default_temperature=cfg.get("temperature", 0.2), default_max_tokens=cfg.get("max_tokens", 1024))
                return
            except Exception as e:
                print("Warning: failed to initialize local LLM client:", e)
                print("Falling back to OpenAI client.")

        # fallback to OpenAI or configured provider
        from ..llm.client import LLMClient
        self.client = LLMClient(default_temperature=cfg.get("temperature", 0.2), default_max_tokens=cfg.get("max_tokens", 1024), provider=provider)

    def process(self, code: str) -> Dict[str, Any]:
        """
        Analyze provided code and return insights and suggestions.
        """
        system = {"role": "system", "content": "You are a senior software engineer and code reviewer. Provide clear, actionable suggestions for improving the code (readability, types, docs, edge-cases, bugs)."}
        user = {"role": "user", "content": f"Analyze the following code and return: (1) a short summary, (2) a numbered list of suggestions (each 1-2 sentences). Use plain text. Code:\n\n{code}"}

        resp = self.client.chat([system, user], model=self.config.get("model"), temperature=self.config.get("temperature"), max_tokens=self.config.get("max_tokens"))

        # Try to extract suggestions lines for easy consumption (best-effort)
        suggestions = []
        for line in resp.splitlines():
            line = line.strip()
            if not line:
                continue
            # Lines that start with '-' or a digit are likely suggestions
            if line.startswith("-") or line[0].isdigit():
                # Remove leading bullet/number
                cleaned = line.lstrip("- ").lstrip("0123456789. ")
                suggestions.append(cleaned)

        return {"status": "ok", "analysis": resp, "suggestions": suggestions}

    def cleanup(self) -> None:
        return None