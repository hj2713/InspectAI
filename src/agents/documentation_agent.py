"""Documentation Agent for generating and improving code documentation."""
from typing import Any, Dict, List

from .base_agent import BaseAgent


class DocumentationAgent(BaseAgent):
    """Agent specialized in generating and improving documentation.
    
    This is a stub implementation. Full functionality will be added later.
    """
    
    def initialize(self) -> None:
        """Initialize documentation LLM client."""
        cfg = self.config or {}
        use_local = cfg.get("use_local", False)
        provider = cfg.get("provider", "openai")

        if use_local:
            try:
                from ..llm.local_client import LocalLLMClient as LLMClient
                self.client = LLMClient(
                    default_temperature=cfg.get("temperature", 0.3),
                    default_max_tokens=cfg.get("max_tokens", 2048)
                )
                return
            except Exception as e:
                print("Warning: failed to initialize local LLM client:", e)
                print("Falling back to cloud provider.")

        from ..llm.client import LLMClient
        self.client = LLMClient(
            default_temperature=cfg.get("temperature", 0.3),
            default_max_tokens=cfg.get("max_tokens", 2048),
            provider=provider
        )

    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate or improve documentation for the provided code.
        
        Args:
            input_data: Dict containing:
                - code: Source code to document
                - doc_type: Type of documentation (docstring, readme, api_docs)
                - style: Documentation style (google, numpy, sphinx)
            
        Returns:
            Dict containing generated documentation
        """
        code = input_data.get("code", "")
        doc_type = input_data.get("doc_type", "docstring")
        style = input_data.get("style", "google")
        
        system = {
            "role": "system",
            "content": f"""You are a technical documentation expert. Generate {doc_type} documentation using {style} style.

Guidelines:
- Write clear, concise descriptions
- Include all parameters and return types
- Add examples where helpful
- Document exceptions/errors that can be raised
- For README: include installation, usage, and examples
- For API docs: include all endpoints, parameters, and responses

Return documentation that follows best practices for {style} style."""
        }
        
        if doc_type == "docstring":
            user_content = f"Add comprehensive docstrings to this code (return the full code with docstrings):\n\n```\n{code}\n```"
        elif doc_type == "readme":
            user_content = f"Generate a README.md for a project containing this code:\n\n```\n{code}\n```"
        elif doc_type == "api_docs":
            user_content = f"Generate API documentation for this code:\n\n```\n{code}\n```"
        else:
            user_content = f"Generate documentation for this code:\n\n```\n{code}\n```"
        
        user = {"role": "user", "content": user_content}

        resp = self.client.chat(
            [system, user],
            model=self.config.get("model"),
            temperature=self.config.get("temperature"),
            max_tokens=self.config.get("max_tokens")
        )

        # Extract code if docstring type
        documented_code = None
        if doc_type == "docstring":
            documented_code = self._extract_code(resp)

        return {
            "status": "ok",
            "raw_response": resp,
            "documentation": resp,
            "documented_code": documented_code,
            "doc_type": doc_type,
            "style": style
        }

    def _extract_code(self, response: str) -> str:
        """Extract code from markdown code blocks."""
        import re
        
        pattern = r"```(?:python)?\s*\n(.*?)```"
        matches = re.findall(pattern, response, re.DOTALL)
        
        if matches:
            return "\n\n".join(matches)
        
        return response

    def cleanup(self) -> None:
        """Cleanup resources."""
        pass
