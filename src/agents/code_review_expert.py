"""Expert Code Reviewer Agent - Reviews code like a senior software developer.

This agent provides comprehensive code review with:
- Structured prompts with clear instructions and examples
- Language-specific checks
- Few-shot learning from curated examples
- Consistent JSON output format
"""
from typing import List, Optional, Dict, Any
import re
import json


class CodeReviewExpert:
    """Expert code reviewer that acts like a senior software developer."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the expert reviewer.
        
        Args:
            config: Configuration dictionary containing model settings
        """
        self.config = config or {}
        self.client = None
        self.prompt_builder = None
        self._initialize_client()
        self._initialize_prompt_builder()
    
    def _initialize_client(self) -> None:
        """Initialize LLM client using centralized factory."""
        from ..llm import get_llm_client_from_config
        self.client = get_llm_client_from_config(self.config)
    
    def _initialize_prompt_builder(self) -> None:
        """Initialize the structured prompt builder."""
        from ..prompts import PromptBuilder
        self.prompt_builder = PromptBuilder()
    
    def review(self, file_path: str, diff_patch: str, full_content: str) -> List[Dict[str, Any]]:
        """Review code changes like a senior developer.
        
        Uses structured prompts with:
        - Clear role definition and instructions
        - Parsed diff context in JSON format
        - Few-shot examples for the file's language
        - Consistent output schema
        
        Args:
            file_path: Path to the file being reviewed
            diff_patch: Git diff showing what changed (+ for additions, - for removals)
            full_content: Complete file content after changes
            
        Returns:
            List of review findings with line numbers, descriptions, and fixes
        """
        from ..prompts.prompt_builder import parse_diff_to_structured, TaskType
        
        # Parse diff into structured context
        context = parse_diff_to_structured(file_path, diff_patch, full_content)
        
        # Build structured prompt with examples
        structured_prompt = self.prompt_builder.build_review_prompt(
            context=context,
            task_type=TaskType.CODE_REVIEW,
            include_examples=True,
            max_examples=2
        )
        
        # Create messages for LLM
        messages = [
            {
                "role": "system",
                "content": "You are a code review assistant. Follow the instructions exactly and return only valid JSON."
            },
            {
                "role": "user",
                "content": structured_prompt
            }
        ]
        
        response = self.client.chat(
            messages,
            model=self.config.get("model"),
            temperature=0.2,  # Lower temperature for more focused reviews
            max_tokens=self.config.get("max_tokens", 10000)
        )
        
        # Parse the JSON response
        findings = self._parse_json_response(response, file_path)
        
        # Fallback to old parsing if JSON parsing fails
        if not findings and response and "LGTM" not in response:
            findings = self._parse_review_response(response, file_path)
        
        return findings
    
    def review_for_bugs(self, file_path: str, diff_patch: str, full_content: str) -> List[Dict[str, Any]]:
        """Deep bug scan focused on finding bugs and edge cases.
        
        Args:
            file_path: Path to the file being reviewed
            diff_patch: Git diff showing what changed
            full_content: Complete file content
            
        Returns:
            List of bug findings
        """
        from ..prompts.prompt_builder import parse_diff_to_structured, TaskType
        
        context = parse_diff_to_structured(file_path, diff_patch, full_content)
        
        structured_prompt = self.prompt_builder.build_review_prompt(
            context=context,
            task_type=TaskType.BUG_DETECTION,
            include_examples=True,
            max_examples=2
        )
        
        messages = [
            {
                "role": "system",
                "content": "You are a bug detection specialist. Find bugs and edge cases. Return only valid JSON."
            },
            {
                "role": "user",
                "content": structured_prompt
            }
        ]
        
        response = self.client.chat(
            messages,
            model=self.config.get("model"),
            temperature=0.1,  # Very low for precise bug detection
            max_tokens=self.config.get("max_tokens", 10000)
        )
        
        return self._parse_json_response(response, file_path)
    
    def review_for_security(self, file_path: str, diff_patch: str, full_content: str) -> List[Dict[str, Any]]:
        """Security audit focused on vulnerabilities.
        
        Args:
            file_path: Path to the file being reviewed
            diff_patch: Git diff showing what changed
            full_content: Complete file content
            
        Returns:
            List of security findings
        """
        from ..prompts.prompt_builder import parse_diff_to_structured, TaskType
        
        context = parse_diff_to_structured(file_path, diff_patch, full_content)
        
        structured_prompt = self.prompt_builder.build_review_prompt(
            context=context,
            task_type=TaskType.SECURITY_AUDIT,
            include_examples=True,
            max_examples=2
        )
        
        messages = [
            {
                "role": "system",
                "content": "You are a security engineer. Find vulnerabilities. Return only valid JSON."
            },
            {
                "role": "user",
                "content": structured_prompt
            }
        ]
        
        response = self.client.chat(
            messages,
            model=self.config.get("model"),
            temperature=0.1,
            max_tokens=self.config.get("max_tokens", 10000)
        )
        
        return self._parse_json_response(response, file_path)
    
    def _parse_json_response(self, response: str, file_path: str) -> List[Dict[str, Any]]:
        """Parse JSON response from LLM.
        
        Args:
            response: Raw LLM response
            file_path: File path for adding to findings
            
        Returns:
            List of parsed findings
        """
        if not response:
            return []
        
        # Try to extract JSON from response
        try:
            # Try direct JSON parse
            data = json.loads(response)
            findings = data.get("findings", [])
        except json.JSONDecodeError:
            # Try to find JSON block in response
            json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
            if json_match:
                try:
                    data = json.loads(json_match.group(1))
                    findings = data.get("findings", [])
                except json.JSONDecodeError:
                    return []
            else:
                # Try to find raw JSON object
                json_match = re.search(r'\{[\s\S]*"findings"[\s\S]*\}', response)
                if json_match:
                    try:
                        data = json.loads(json_match.group(0))
                        findings = data.get("findings", [])
                    except json.JSONDecodeError:
                        return []
                else:
                    return []
        
        # Normalize findings
        normalized = []
        for finding in findings:
            if isinstance(finding, dict):
                normalized.append({
                    "file": file_path,
                    "line_number": finding.get("line", 1),
                    "severity": finding.get("severity", "medium"),
                    "category": finding.get("category", "review"),
                    "description": finding.get("description", ""),
                    "fix_suggestion": finding.get("fix_suggestion", ""),
                    "confidence": finding.get("confidence", 0.5),
                    "location": f"line {finding.get('line', 1)}"
                })
        
        return normalized
    
    def _detect_language(self, file_ext: str) -> str:
        """Detect programming language from file extension (legacy method)."""
        lang_map = {
            'py': 'Python',
            'js': 'JavaScript',
            'ts': 'TypeScript',
            'jsx': 'React/JSX',
            'tsx': 'TypeScript/React',
            'java': 'Java',
            'cpp': 'C++',
            'c': 'C',
            'go': 'Go',
            'rb': 'Ruby',
            'php': 'PHP',
            'cs': 'C#',
            'swift': 'Swift',
            'kt': 'Kotlin',
            'rs': 'Rust',
            'scala': 'Scala',
            'sql': 'SQL',
            'sh': 'Shell',
            'yml': 'YAML',
            'yaml': 'YAML',
            'json': 'JSON',
            'xml': 'XML',
            'html': 'HTML',
            'css': 'CSS',
            'scss': 'SCSS',
        }
        return lang_map.get(file_ext.lower(), 'code')
    
    def _parse_review_response(self, response: str, file_path: str) -> List[Dict[str, Any]]:
        """Parse legacy text response into structured findings (fallback method)."""
        findings = []
        
        # Check if no issues found
        if "LGTM" in response or "no issues" in response.lower():
            return []
        
        # Split by separator
        issues = response.split('---')
        
        for issue_text in issues:
            issue_text = issue_text.strip()
            if not issue_text or len(issue_text) < 20:
                continue
            
            # Extract fields using regex
            line_match = re.search(r'LINE:\s*(\d+)', issue_text, re.IGNORECASE)
            severity_match = re.search(r'SEVERITY:\s*(critical|high|medium|low)', issue_text, re.IGNORECASE)
            issue_match = re.search(r'ISSUE:\s*(.+?)(?:\n|CONTEXT:|DESCRIPTION:|$)', issue_text, re.IGNORECASE | re.DOTALL)
            context_match = re.search(r'CONTEXT:\s*(.+?)(?:\n|DESCRIPTION:|FIX:|$)', issue_text, re.IGNORECASE | re.DOTALL)
            desc_match = re.search(r'DESCRIPTION:\s*(.+?)(?:\n|FIX:|$)', issue_text, re.IGNORECASE | re.DOTALL)
            fix_match = re.search(r'FIX:\s*(.+?)(?:\n---|\n\n|$)', issue_text, re.IGNORECASE | re.DOTALL)
            
            if line_match and desc_match:
                finding = {
                    "file": file_path,
                    "line_number": int(line_match.group(1)),
                    "severity": severity_match.group(1).lower() if severity_match else "medium",
                    "category": issue_match.group(1).strip() if issue_match else "Code Review",
                    "context": context_match.group(1).strip() if context_match else "",
                    "description": desc_match.group(1).strip(),
                    "fix_suggestion": fix_match.group(1).strip() if fix_match else "",
                    "location": f"line {line_match.group(1)}"
                }
                findings.append(finding)
        
        return findings
