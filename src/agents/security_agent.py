"""Security Analysis Agent for identifying vulnerabilities in code."""
from typing import Any, Dict, List

from .base_agent import BaseAgent


class SecurityAnalysisAgent(BaseAgent):
    """Agent specialized in security vulnerability detection.
    
    This is a stub implementation. Full functionality will be added later.
    """
    
    VULNERABILITY_CATEGORIES = [
        "SQL Injection",
        "XSS (Cross-Site Scripting)",
        "CSRF (Cross-Site Request Forgery)",
        "Path Traversal",
        "Command Injection",
        "Insecure Deserialization",
        "Hardcoded Credentials",
        "Sensitive Data Exposure",
        "Authentication Issues",
        "Authorization Issues",
        "Cryptographic Weaknesses",
        "Input Validation",
    ]
    
    def initialize(self) -> None:
        """Initialize security analysis LLM client."""
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
        Analyze code for security vulnerabilities.
        
        Args:
            code: Source code to analyze for security issues
            
        Returns:
            Dict containing vulnerabilities, risk levels, and remediation suggestions
        """
        categories_str = "\n".join(f"- {cat}" for cat in self.VULNERABILITY_CATEGORIES)
        
        system = {
            "role": "system",
            "content": f"""You are a security expert specialized in code security analysis. 
Analyze code for security vulnerabilities including but not limited to:
{categories_str}

For each vulnerability found, provide:
1. Category (from the list above or "Other")
2. Severity: Critical, High, Medium, Low
3. Location in the code
4. Description of the vulnerability
5. Remediation steps

Format each finding as:
VULNERABILITY: [Category]
Severity: [level]
Location: [line/function]
Description: [explanation]
Remediation: [how to fix]
"""
        }
        
        user = {
            "role": "user",
            "content": f"Perform a security audit on this code:\n\n```\n{code}\n```"
        }

        resp = self.client.chat(
            [system, user],
            model=self.config.get("model"),
            temperature=self.config.get("temperature"),
            max_tokens=self.config.get("max_tokens")
        )

        vulnerabilities = self._parse_vulnerabilities(resp)

        return {
            "status": "ok",
            "raw_analysis": resp,
            "vulnerabilities": vulnerabilities,
            "vulnerability_count": len(vulnerabilities),
            "risk_score": self._calculate_risk_score(vulnerabilities)
        }

    def _parse_vulnerabilities(self, response: str) -> List[Dict[str, str]]:
        """Parse vulnerability information from LLM response."""
        vulnerabilities = []
        current_vuln = {}
        
        for line in response.splitlines():
            line = line.strip()
            if not line:
                if current_vuln:
                    vulnerabilities.append(current_vuln)
                    current_vuln = {}
                continue
                
            if line.upper().startswith("VULNERABILITY"):
                if current_vuln:
                    vulnerabilities.append(current_vuln)
                category = line.split(":", 1)[1].strip() if ":" in line else "Unknown"
                current_vuln = {"category": category}
            elif line.lower().startswith("severity:"):
                current_vuln["severity"] = line.split(":", 1)[1].strip().lower()
            elif line.lower().startswith("location:"):
                current_vuln["location"] = line.split(":", 1)[1].strip()
            elif line.lower().startswith("description:"):
                current_vuln["description"] = line.split(":", 1)[1].strip()
            elif line.lower().startswith("remediation:"):
                current_vuln["remediation"] = line.split(":", 1)[1].strip()
        
        if current_vuln:
            vulnerabilities.append(current_vuln)
            
        return vulnerabilities

    def _calculate_risk_score(self, vulnerabilities: List[Dict[str, str]]) -> float:
        """Calculate overall risk score based on vulnerabilities found."""
        if not vulnerabilities:
            return 0.0
            
        severity_weights = {
            "critical": 10.0,
            "high": 7.0,
            "medium": 4.0,
            "low": 1.0
        }
        
        total_score = sum(
            severity_weights.get(v.get("severity", "low"), 1.0)
            for v in vulnerabilities
        )
        
        # Normalize to 0-10 scale
        max_score = len(vulnerabilities) * 10
        return min(10.0, (total_score / max_score) * 10) if max_score > 0 else 0.0

    def cleanup(self) -> None:
        """Cleanup resources."""
        pass
