"""Test Generation Agent for automatically creating test cases."""
from typing import Any, Dict, List

from .base_agent import BaseAgent


class TestGenerationAgent(BaseAgent):
    """Agent specialized in generating test cases for code.
    
    Generates tests ONLY for changed/added code in PRs, not the entire file.
    """
    
    def initialize(self) -> None:
        """Initialize LLM client using centralized factory."""
        from ..llm import get_llm_client_from_config
        
        cfg = self.config or {}
        self.client = get_llm_client_from_config(cfg)

    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate test cases for the changed code only.
        
        Args:
            input_data: Dict containing:
                - code: Full source code (for context)
                - diff_patch: The diff showing what changed
                - framework: Test framework to use (pytest, unittest, etc.)
                - coverage_focus: Areas to focus on (edge_cases, happy_path, etc.)
            
        Returns:
            Dict containing generated test code and test descriptions
        """
        code = input_data.get("code", "")
        diff_patch = input_data.get("diff_context", "") or input_data.get("diff_patch", "")
        framework = input_data.get("framework", "pytest")
        coverage_focus = input_data.get("coverage_focus", ["happy_path", "edge_cases", "error_handling"])
        
        if isinstance(coverage_focus, list):
            coverage_focus = ", ".join(coverage_focus)
        
        # Extract only added/modified lines from diff
        changed_code = self._extract_changed_code(diff_patch) if diff_patch else code
        
        # If no meaningful changes, use a smaller context
        if not changed_code.strip():
            changed_code = code[:2000]  # Limit context if no diff
        
        system = {
            "role": "system",
            "content": f"""You are an expert test engineer. Generate comprehensive test cases using {framework}.

**IMPORTANT**: Generate tests ONLY for the changed/added code shown below. Do NOT generate tests for unchanged code.

Focus on:
- {coverage_focus}
- Testing the NEW or MODIFIED functions/methods only
- Testing boundary conditions for the changes
- Testing error cases for the changes

Provide:
1. Complete, runnable test code
2. Comments explaining what each test verifies
3. Good test naming conventions
4. Necessary imports and fixtures

Return the tests wrapped in ```python``` code blocks."""
        }
        
        # Build prompt based on whether we have diff or full code
        if diff_patch:
            user_content = f"""Generate tests for ONLY the changed code in this diff:

## Diff (lines starting with + are additions):
```diff
{diff_patch[:8000]}
```

## Full file context (for imports and understanding):
```python
{code[:4000]}
```

Generate tests ONLY for the added/modified code (+ lines in diff)."""
        else:
            user_content = f"Generate tests for this code:\n\n```python\n{changed_code[:6000]}\n```"
        
        user = {
            "role": "user",
            "content": user_content
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
    
    def _extract_changed_code(self, diff_patch: str) -> str:
        """Extract only added/modified lines from a diff patch.
        
        Args:
            diff_patch: Git diff patch string
            
        Returns:
            String containing only the added lines (without + prefix)
        """
        added_lines = []
        for line in diff_patch.splitlines():
            # Lines starting with + (but not ++) are additions
            if line.startswith('+') and not line.startswith('+++'):
                added_lines.append(line[1:])  # Remove the + prefix
        
        return '\n'.join(added_lines)

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
