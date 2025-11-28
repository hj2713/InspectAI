"""Code Generation Agent for creating and modifying code."""
from typing import Any, Dict, List

from .base_agent import BaseAgent

import re


class CodeGenerationAgent(BaseAgent):
    def initialize(self) -> None:
        """Initialize LLM client using centralized factory."""
        from ..llm import get_llm_client_from_config
        
        cfg = self.config or {}
        self.client = get_llm_client_from_config(cfg)

    def process(self, specification: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate code based on provided specifications.

        Expected specification keys (best-effort):
            - code: original code string
            - suggestions: list of textual suggestions to apply
            - requirements: list of extra requirements
        """
        code = specification.get("code", "")
        suggestions = specification.get("suggestions", [])
        requirements = specification.get("requirements", [])

        system = {"role": "system", "content": "You are an expert programmer who edits and improves code according to instructions. Return only the modified code inside a markdown code fence (```python ... ```)."}
        user_lines = ["Improve the following code according to the suggestions and requirements.", "Suggestions:"]
        user_lines += [f"- {s}" for s in suggestions]
        if requirements:
            user_lines.append("Requirements:")
            user_lines += [f"- {r}" for r in requirements]
        user_lines.append("Original code:")
        user_lines.append(code)
        user = {"role": "user", "content": "\n".join(user_lines)}

        resp = self.client.chat([system, user], model=self.config.get("model"), temperature=self.config.get("temperature"), max_tokens=self.config.get("max_tokens"))

        # Extract code between triple backticks (best-effort)
        m = re.search(r"```(?:python\n)?([\s\S]*?)```", resp)
        generated_code = m.group(1).strip() if m else resp.strip()

        return {"status": "ok", "generated_code": generated_code, "raw": resp}

    def cleanup(self) -> None:
        return None