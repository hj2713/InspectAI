"""Test Generation Agent for automatically creating test cases."""
from typing import Any, Dict, List

from .base_agent import BaseAgent


class TestGenerationAgent(BaseAgent):
    """Agent specialized in generating test cases for code.
    
    This is a stub implementation. Full functionality will be added later.
    """
    
    def initialize(self) -> None:
        """Initialize LLM client using centralized factory."""
        from ..llm import get_llm_client_from_config
        
        cfg = self.config or {}
        self.client = get_llm_client_from_config(cfg)

    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        if isinstance(coverage_focus, list):
            coverage_focus = ", ".join(coverage_focus)
        
        system = {
            "role": "system",
            "content": f"""You are an expert test engineer. Generate comprehensive test cases using {framework}.

Focus on:
- {coverage_focus}
- Testing all public functions/methods
- Testing boundary conditions
- Testing error cases

Provide:
1. Complete, runnable test code
2. Comments explaining what each test verifies
3. Good test naming conventions

Return the tests wrapped in ```python``` code blocks."""
        }
        
        user = {
            "role": "user",
            "content": f"Generate comprehensive tests for this code:\n\n```\n{code}\n```"
        }

        resp = self.client.chat(
            [system, user],
            model=self.config.get("model"),
            temperature=self.config.get("temperature"),
            max_tokens=self.config.get("max_tokens")
        )

        # Extract code from response
        test_code = self._extract_code(resp)
        test_descriptions = self._extract_test_descriptions(resp)

        return {
            "status": "ok",
            "raw_response": resp,
            "test_code": test_code,
            "test_descriptions": test_descriptions,
            "framework": framework
        }

    def _extract_code(self, response: str) -> str:
        """Extract code from markdown code blocks."""
        import re
        
        # Try to find python code blocks
        pattern = r"```(?:python)?\s*\n(.*?)```"
        matches = re.findall(pattern, response, re.DOTALL)
        
        if matches:
            return "\n\n".join(matches)
        
        # If no code blocks, return the whole response
        return response

    def _extract_test_descriptions(self, response: str) -> List[str]:
        """Extract test descriptions from response."""
        descriptions = []
        
        for line in response.splitlines():
            line = line.strip()
            # Look for test function definitions
            if line.startswith("def test_"):
                # Extract function name
                func_name = line.split("(")[0].replace("def ", "")
                descriptions.append(func_name)
            # Look for comment descriptions
            elif line.startswith("# Test:") or line.startswith("# Test "):
                descriptions.append(line.replace("# ", ""))
        
        return descriptions

    def cleanup(self) -> None:
        """Cleanup resources."""
        pass
