"""Expert Code Reviewer Agent - Reviews code like a senior software developer.

This agent replaces the 4 sub-agents with a single comprehensive reviewer that:
- Understands diff context (what was added/removed/changed)
- Reviews any programming language
- Focuses on actual issues, not nitpicking
- Provides actionable, contextual feedback
"""
from typing import List, Optional, Dict, Any
import re


class CodeReviewExpert:
    """Expert code reviewer that acts like a senior software developer."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the expert reviewer.
        
        Args:
            config: Configuration dictionary containing model settings
        """
        self.config = config or {}
        self.client = None
        self._initialize_client()
    
    def _initialize_client(self) -> None:
        """Initialize LLM client using centralized factory."""
        from ..llm import get_llm_client_from_config
        self.client = get_llm_client_from_config(self.config)
    
    def review(self, file_path: str, diff_patch: str, full_content: str) -> List[Dict[str, Any]]:
        """Review code changes like a senior developer.
        
        Args:
            file_path: Path to the file being reviewed
            diff_patch: Git diff showing what changed (+ for additions, - for removals)
            full_content: Complete file content after changes
            
        Returns:
            List of review findings with line numbers, descriptions, and fixes
        """
        # Detect file type
        file_ext = file_path.split('.')[-1] if '.' in file_path else ''
        language = self._detect_language(file_ext)
        
        # Build expert reviewer prompt
        system_prompt = {
            "role": "system",
            "content": f"""You are a senior software engineer reviewing a pull request. You have 10+ years of experience in {language} and software development best practices.

Your review philosophy:
- Focus ONLY on issues introduced by the changes (shown in the diff)
- Be practical, not pedantic - only flag real problems
- Consider the context: if something was removed, explain the impact of that removal
- If something was added, check if it introduces bugs or violates best practices
- Ignore minor style issues unless they significantly impact readability

Review for:
1. **Logic errors** in changed code (off-by-one, wrong operators, edge cases)
2. **Bugs introduced** (null/undefined, race conditions, resource leaks)
3. **Security issues** (injection, exposure, authentication)
4. **Breaking changes** (API changes, removed functionality)
5. **Performance problems** (inefficient algorithms in new code)
6. **Missing error handling** in new code paths
7. **Documentation impact** (if important docs/comments were removed)

For EACH issue found, respond in this EXACT format:
LINE: [line number]
SEVERITY: [critical/high/medium/low]
ISSUE: [brief title of the problem]
CONTEXT: [what was changed - added/removed/modified]
DESCRIPTION: [explain the issue clearly]
FIX: [specific actionable fix]
---

If the changes look good, respond with: "LGTM - No issues found in the changes."

Remember: You're reviewing the CHANGES, not the entire codebase. Be diff-aware!
"""
        }
        
        user_prompt = {
            "role": "user",
            "content": f"""Review this pull request change:

**File:** {file_path}

**Diff (what changed):**
```diff
{diff_patch}
```

**Full file content (for context):**
```{language}
{full_content}
```

Please review the changes and provide feedback following the format specified.
"""
        }
        
        response = self.client.chat(
            [system_prompt, user_prompt],
            model=self.config.get("model"),
            temperature=0.2,  # Lower temperature for more focused reviews
            max_tokens=self.config.get("max_tokens", 10000)
        )
        
        # Parse the response
        return self._parse_review_response(response, file_path)
    
    def _detect_language(self, file_ext: str) -> str:
        """Detect programming language from file extension."""
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
        """Parse LLM response into structured findings."""
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
