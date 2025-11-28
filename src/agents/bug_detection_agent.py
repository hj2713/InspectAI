"""Bug Detection Agent for identifying bugs and errors in code."""
from typing import Any, Dict, List

from .base_agent import BaseAgent


class BugDetectionAgent(BaseAgent):
    """Agent specialized in detecting bugs, errors, and potential issues in code.
    
    This is a stub implementation. Full functionality will be added later.
    """
    
    def initialize(self) -> None:
        """Initialize bug detection LLM client."""
        cfg = self.config or {}
        use_local = cfg.get("use_local", False)
        provider = cfg.get("provider", "openai")

        if use_local:
            try:
                from ..llm.local_client import LocalLLMClient as LLMClient
                self.client = LLMClient(
                    default_temperature=cfg.get("temperature", 0.1),
                    default_max_tokens=cfg.get("max_tokens", 1024)
                )
                return
            except Exception as e:
                print("Warning: failed to initialize local LLM client:", e)
                print("Falling back to cloud provider.")

        from ..llm.client import LLMClient
        self.client = LLMClient(
            default_temperature=cfg.get("temperature", 0.1),
            default_max_tokens=cfg.get("max_tokens", 1024),
            provider=provider
        )

    def process(self, code: str) -> Dict[str, Any]:
        """
        Analyze code to detect bugs, errors, and potential issues.
        
        Args:
            code: Source code to analyze for bugs
            
        Returns:
            Dict containing detected bugs, severity levels, and fix suggestions
        """
        system = {
            "role": "system",
            "content": """You are an expert bug hunter and code debugger. Your task is to:
1. Identify potential bugs, errors, and issues in the code
2. Classify each issue by severity (critical, high, medium, low)
3. Explain why each issue is problematic
4. Suggest a fix for each issue

Format your response as:
BUG 1: [severity] - [brief description]
Location: [where in the code]
Problem: [detailed explanation]
Fix: [suggested fix]

Continue for all bugs found."""
        }
        
        user = {
            "role": "user",
            "content": f"Analyze this code for bugs and issues:\n\n```\n{code}\n```"
        }

        resp = self.client.chat(
            [system, user],
            model=self.config.get("model"),
            temperature=self.config.get("temperature"),
            max_tokens=self.config.get("max_tokens")
        )

        # Parse bugs from response
        bugs = self._parse_bugs(resp)

        return {
            "status": "ok",
            "raw_analysis": resp,
            "bugs": bugs,
            "bug_count": len(bugs)
        }

    def _parse_bugs(self, response: str) -> List[Dict[str, str]]:
        """Parse bug information from LLM response."""
        bugs = []
        current_bug = {}
        
        for line in response.splitlines():
            line = line.strip()
            if not line:
                if current_bug:
                    bugs.append(current_bug)
                    current_bug = {}
                continue
                
            if line.upper().startswith("BUG"):
                if current_bug:
                    bugs.append(current_bug)
                # Parse severity and description
                parts = line.split("-", 1)
                severity = "medium"
                description = line
                if len(parts) == 2:
                    sev_part = parts[0].lower()
                    for sev in ["critical", "high", "medium", "low"]:
                        if sev in sev_part:
                            severity = sev
                            break
                    description = parts[1].strip()
                current_bug = {"severity": severity, "description": description}
            elif line.lower().startswith("location:"):
                current_bug["location"] = line.split(":", 1)[1].strip()
            elif line.lower().startswith("problem:"):
                current_bug["problem"] = line.split(":", 1)[1].strip()
            elif line.lower().startswith("fix:"):
                current_bug["fix"] = line.split(":", 1)[1].strip()
        
        if current_bug:
            bugs.append(current_bug)
            
        return bugs

    def cleanup(self) -> None:
        """Cleanup resources."""
        pass
