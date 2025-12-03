"""Dependency Vulnerability Scanner - Specialized security agent.

This agent focuses on detecting usage of known vulnerable dependencies
and insecure library usage patterns.
"""
from typing import List, Optional
from ..specialized_agent import SpecializedAgent, Finding


class DependencyScanner(SpecializedAgent):
    """Specialized agent for detecting dependency-related security issues."""
    
    def initialize(self) -> None:
        """Initialize LLM client for dependency scanning."""
        cfg = self.config or {}
        
        from ...llm import get_llm_client_from_config
        self.client = get_llm_client_from_config(cfg)
    
    def analyze(self, code: str, context: Optional[str] = None, filename: Optional[str] = None) -> List[Finding]:
        """Analyze code for insecure dependencies.
        
        Args:
            code: Source code to analyze
            context: Optional[str]: Additional context or description of the code.
            filename: Optional filename for language detection
            
        Returns:
            List of Finding objects related to dependency issues
        """
        from ...utils.language_detection import detect_language
        language = detect_language(filename)

        system_prompt = {
            "role": "system",
            "content": f"""You are a STRICT security expert analyzing {language} code for dependency vulnerabilities.

ONLY report if you SEE IN THE CODE:
1. eval()/exec() with user input: eval(user_input), exec(request.body)
2. pickle.loads() with untrusted data: pickle.loads(network_data)
3. yaml.load() without safe_load: yaml.load(file) instead of yaml.safe_load()
4. Weak crypto: md5/sha1 for passwords, DES encryption
5. Known vulnerable imports: import telnetlib, from xml.etree import ElementTree (for parsing untrusted XML)

NEVER FLAG:
- File extension checks (e.g., if filename.endswith('.xml')) - this is NOT XML parsing
- String operations that mention file types
- Import statements without seeing vulnerable USAGE
- eval/exec for internal code generation (not user input)
- Standard library imports without vulnerable usage patterns
- Type checking or file filtering by extension
- Code that determines file types for categorization

CRITICAL: A file extension string ('.xml', '.json') is NOT the same as parsing that format.
Only flag if you see ACTUAL vulnerable function calls with untrusted input.

For CONFIRMED vulnerabilities, respond with:
Category: Dependency/Library Security
Severity: [medium/high/critical]
Description: [the specific vulnerable function call you found]
Location: [line X]
Fix: [specific safer alternative]
Confidence: [0.8-1.0]

If code is safe, respond with: "No dependency issues found."
"""
        }
        
        prompt_content = f"Analyze this {language} code for dependency issues:\n\n```{language.lower()}\n{code}\n```"
        if context:
            prompt_content += f"\n\nAdditional Context:\n{context}"
            
        user_prompt = {
            "role": "user",
            "content": prompt_content
        }
        
        response = self.client.chat(
            [system_prompt, user_prompt],
            model=self.config.get("model"),
            temperature=self.config.get("temperature"),
            max_tokens=self.config.get("max_tokens")
        )
        
        # Check if no issues found
        if "no dependency issues" in response.lower() or "no issues found" in response.lower():
            return []
        
        # Parse findings from response
        findings = self._parse_llm_response(response, code)
        
        # Ensure all findings have correct category
        for finding in findings:
            finding.category = "Dependency/Library Security"
            # Dependency issues can be critical
            if finding.severity == "low":
                finding.severity = "medium"
        
        return findings
