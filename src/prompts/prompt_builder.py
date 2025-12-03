"""Structured prompt builder for LLM code reviews.

Constructs well-organized prompts with:
- Clear role definition
- Structured context (parsed diffs)
- Task-specific instructions
- Few-shot examples
- Output schema
"""
import json
import re
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from enum import Enum


class TaskType(Enum):
    """Types of code review tasks."""
    CODE_REVIEW = "code_review"
    BUG_DETECTION = "bug_detection"
    SECURITY_AUDIT = "security_audit"
    REFACTOR = "refactor"


class ChangeType(Enum):
    """Types of code changes in a diff."""
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    CONTEXT = "context"


@dataclass
class DiffChange:
    """Represents a single line change in a diff."""
    line_number: int
    change_type: ChangeType
    code: str
    old_line_number: Optional[int] = None  # For modified lines


@dataclass
class StructuredContext:
    """Structured context for code review."""
    file_path: str
    language: str
    changes: List[DiffChange]
    full_content: Optional[str] = None
    pr_title: Optional[str] = None
    pr_description: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "file_path": self.file_path,
            "language": self.language,
            "changes": [
                {
                    "line": c.line_number,
                    "type": c.change_type.value,
                    "code": c.code
                }
                for c in self.changes
            ],
            "total_changes": len(self.changes),
            "added_lines": sum(1 for c in self.changes if c.change_type == ChangeType.ADDED),
            "removed_lines": sum(1 for c in self.changes if c.change_type == ChangeType.REMOVED)
        }


# Language-specific instructions
LANGUAGE_INSTRUCTIONS = {
    "python": [
        "Check for missing type hints on function parameters and return values",
        "Look for bare except clauses (should catch specific exceptions)",
        "Verify f-strings don't have SQL injection vulnerabilities",
        "Check for mutable default arguments (e.g., def func(items=[]))",
        "Look for improper use of global variables",
        "Verify async/await is used correctly"
    ],
    "javascript": [
        "Check for == instead of === comparisons",
        "Look for missing null/undefined checks",
        "Verify Promises are properly handled (no floating promises)",
        "Check for potential prototype pollution",
        "Look for callback hell that should use async/await",
        "Verify event listeners are properly cleaned up"
    ],
    "typescript": [
        "Check for 'any' types that should be more specific",
        "Look for missing null checks despite strict mode",
        "Verify generic constraints are appropriate",
        "Check for type assertions that could fail at runtime",
        "Look for implicit any in function parameters"
    ],
    "java": [
        "Check for NullPointerException risks (missing null checks)",
        "Look for resource leaks (unclosed streams, connections)",
        "Verify exceptions are handled appropriately (not swallowed)",
        "Check for thread safety issues in shared state",
        "Look for SQL injection in JDBC queries"
    ],
    "go": [
        "Check for unchecked errors (err != nil)",
        "Look for goroutine leaks",
        "Verify defer is used correctly for cleanup",
        "Check for race conditions in concurrent code",
        "Look for nil pointer dereferences"
    ],
    "default": [
        "Check for logic errors in conditionals",
        "Look for off-by-one errors in loops",
        "Verify error handling is present",
        "Check for hardcoded secrets or credentials",
        "Look for potential null/undefined access"
    ]
}

# Security-specific checks by language
SECURITY_CHECKS = {
    "python": [
        "SQL injection via string formatting or f-strings",
        "Command injection via os.system, subprocess with shell=True",
        "Pickle deserialization of untrusted data",
        "Path traversal in file operations",
        "SSRF in requests/urllib calls",
        "Hardcoded secrets, API keys, passwords"
    ],
    "javascript": [
        "XSS via innerHTML, document.write",
        "SQL injection in raw queries",
        "Command injection via child_process",
        "Prototype pollution attacks",
        "Insecure deserialization",
        "CORS misconfiguration"
    ],
    "default": [
        "SQL/NoSQL injection vulnerabilities",
        "Command/code injection",
        "Hardcoded credentials or secrets",
        "Insecure data handling",
        "Authentication/authorization flaws",
        "Sensitive data exposure in logs"
    ]
}

# Output schema for consistent results
OUTPUT_SCHEMA = {
    "findings": [
        {
            "line": "number - the exact line number with the issue",
            "severity": "critical|high|medium|low",
            "category": "bug|security|performance|style|logic",
            "description": "Clear description of the issue",
            "fix_suggestion": "Specific code fix or recommendation",
            "confidence": "number 0-1 indicating confidence"
        }
    ]
}


class PromptBuilder:
    """Builds structured prompts for LLM code reviews."""
    
    def __init__(self):
        self.example_selector = None  # Will be set when needed
    
    def build_review_prompt(
        self,
        context: StructuredContext,
        task_type: TaskType = TaskType.CODE_REVIEW,
        include_examples: bool = True,
        max_examples: int = 2
    ) -> str:
        """Build a structured prompt for code review.
        
        Args:
            context: Structured context with file info and changes
            task_type: Type of review task
            include_examples: Whether to include few-shot examples
            max_examples: Maximum number of examples to include
            
        Returns:
            Structured prompt string
        """
        sections = []
        
        # 1. Role Definition
        sections.append(self._build_role_section(task_type))
        
        # 2. Task Instructions
        sections.append(self._build_instructions_section(task_type, context.language))
        
        # 3. Structured Context
        sections.append(self._build_context_section(context))
        
        # 4. Few-shot Examples (if enabled)
        if include_examples:
            examples_section = self._build_examples_section(
                context.language, 
                task_type,
                max_examples
            )
            if examples_section:
                sections.append(examples_section)
        
        # 5. Output Schema
        sections.append(self._build_output_section())
        
        # 6. Final Instructions
        sections.append(self._build_final_instructions(task_type))
        
        return "\n\n".join(sections)
    
    def _build_role_section(self, task_type: TaskType) -> str:
        """Build the role definition section."""
        roles = {
            TaskType.CODE_REVIEW: (
                "You are a **Senior Software Engineer** with 10+ years of experience "
                "conducting thorough code reviews. You focus on finding real issues that "
                "could cause bugs, security vulnerabilities, or maintenance problems. "
                "You are practical, not pedantic - you don't nitpick style preferences."
            ),
            TaskType.BUG_DETECTION: (
                "You are a **Bug Detection Specialist** expert at finding logic errors, "
                "edge cases, type mismatches, and runtime issues. You think like a QA "
                "engineer trying to break the code."
            ),
            TaskType.SECURITY_AUDIT: (
                "You are a **Security Engineer** specialized in application security. "
                "You identify vulnerabilities like injection attacks, authentication flaws, "
                "and data exposure risks. You follow OWASP guidelines."
            ),
            TaskType.REFACTOR: (
                "You are a **Software Architect** focused on code quality and maintainability. "
                "You suggest improvements for readability, performance, and design patterns "
                "without changing functionality."
            )
        }
        return f"## Role\n\n{roles.get(task_type, roles[TaskType.CODE_REVIEW])}"
    
    def _build_instructions_section(self, task_type: TaskType, language: str) -> str:
        """Build the task-specific instructions section."""
        base_instructions = {
            TaskType.CODE_REVIEW: [
                "Review ONLY the changed lines (marked as 'added' or 'modified')",
                "Do NOT comment on removed lines or unchanged context",
                "Focus on issues that could cause real problems, not style preferences",
                "Each finding MUST include the exact line number"
            ],
            TaskType.BUG_DETECTION: [
                "Scan for bugs that could cause runtime errors or incorrect behavior",
                "Check edge cases: null/None values, empty arrays, boundary conditions",
                "Look for logic errors in conditionals and loops",
                "Identify type mismatches and conversion errors"
            ],
            TaskType.SECURITY_AUDIT: [
                "Focus on security vulnerabilities that could be exploited",
                "Check for injection attacks (SQL, command, XSS)",
                "Look for authentication and authorization flaws",
                "Identify hardcoded secrets and sensitive data exposure"
            ],
            TaskType.REFACTOR: [
                "Suggest improvements that enhance readability and maintainability",
                "Identify duplicate code that could be extracted",
                "Recommend better design patterns where applicable",
                "Focus on the changed code, not the entire file"
            ]
        }
        
        # Get language-specific instructions
        lang_key = language.lower() if language.lower() in LANGUAGE_INSTRUCTIONS else "default"
        lang_instructions = LANGUAGE_INSTRUCTIONS[lang_key]
        
        # Get security checks if security audit
        security_instructions = []
        if task_type == TaskType.SECURITY_AUDIT:
            sec_key = language.lower() if language.lower() in SECURITY_CHECKS else "default"
            security_instructions = SECURITY_CHECKS[sec_key]
        
        # Combine instructions
        all_instructions = base_instructions.get(task_type, base_instructions[TaskType.CODE_REVIEW])
        
        instruction_text = "## Instructions\n\n"
        instruction_text += "**General:**\n"
        for i, inst in enumerate(all_instructions, 1):
            instruction_text += f"{i}. {inst}\n"
        
        instruction_text += f"\n**{language.capitalize()}-Specific Checks:**\n"
        for i, inst in enumerate(lang_instructions[:4], 1):  # Limit to 4
            instruction_text += f"{i}. {inst}\n"
        
        if security_instructions:
            instruction_text += "\n**Security Checks:**\n"
            for i, inst in enumerate(security_instructions[:4], 1):
                instruction_text += f"{i}. {inst}\n"
        
        return instruction_text
    
    def _build_context_section(self, context: StructuredContext) -> str:
        """Build the structured context section."""
        context_dict = context.to_dict()
        
        section = "## Code Context\n\n"
        section += f"**File:** `{context.file_path}`\n"
        section += f"**Language:** {context.language}\n"
        section += f"**Changes:** {context_dict['added_lines']} added, {context_dict['removed_lines']} removed\n\n"
        
        # Format changes as structured data
        section += "### Changes (JSON Format)\n\n```json\n"
        section += json.dumps(context_dict["changes"], indent=2)
        section += "\n```\n"
        
        # Include full file if provided (truncated)
        if context.full_content:
            lines = context.full_content.split('\n')
            if len(lines) > 100:
                section += "\n### Full File Context (truncated)\n\n```" + context.language + "\n"
                section += '\n'.join(lines[:100])
                section += f"\n... ({len(lines) - 100} more lines)\n```\n"
            else:
                section += "\n### Full File Context\n\n```" + context.language + "\n"
                section += context.full_content
                section += "\n```\n"
        
        return section
    
    def _build_examples_section(
        self, 
        language: str, 
        task_type: TaskType,
        max_examples: int
    ) -> Optional[str]:
        """Build the few-shot examples section."""
        # Import here to avoid circular imports
        from .example_selector import ExampleSelector
        
        if self.example_selector is None:
            self.example_selector = ExampleSelector()
        
        examples = self.example_selector.get_examples(
            language=language,
            task_type=task_type.value,
            max_examples=max_examples
        )
        
        if not examples:
            return None
        
        section = "## Examples\n\n"
        section += "Here are examples of good code review findings:\n\n"
        
        for i, example in enumerate(examples, 1):
            section += f"### Example {i}\n\n"
            section += f"**Input Code:**\n```{example.get('language', language)}\n"
            section += example.get('input_code', '')
            section += "\n```\n\n"
            section += f"**Expected Finding:**\n```json\n"
            section += json.dumps(example.get('expected_output', {}), indent=2)
            section += "\n```\n\n"
        
        return section
    
    def _build_output_section(self) -> str:
        """Build the output schema section."""
        section = "## Required Output Format\n\n"
        section += "Return your findings as a JSON object with this exact schema:\n\n"
        section += "```json\n"
        section += json.dumps(OUTPUT_SCHEMA, indent=2)
        section += "\n```\n\n"
        section += "**Important:**\n"
        section += "- Return ONLY valid JSON, no markdown or explanations\n"
        section += "- Include only findings with confidence >= 0.5\n"
        section += "- If no issues found, return: `{\"findings\": []}`\n"
        section += "- Each finding MUST have all fields\n"
        
        return section
    
    def _build_final_instructions(self, task_type: TaskType) -> str:
        """Build final reminder instructions."""
        reminders = {
            TaskType.CODE_REVIEW: (
                "Remember: Focus on the CHANGED lines only. "
                "Don't suggest adding docstrings if the code intentionally removed them. "
                "Be practical - real issues only, no nitpicking."
            ),
            TaskType.BUG_DETECTION: (
                "Remember: Look for bugs that would cause actual failures. "
                "Think about edge cases the developer might have missed. "
                "Each bug should be something that could fail in production."
            ),
            TaskType.SECURITY_AUDIT: (
                "Remember: Focus on exploitable vulnerabilities. "
                "Consider how an attacker could abuse each issue. "
                "Prioritize findings that could lead to data breaches or unauthorized access."
            ),
            TaskType.REFACTOR: (
                "Remember: Suggest practical improvements that are worth the effort. "
                "Don't recommend massive rewrites for small benefits. "
                "Focus on changes that improve readability and reduce bugs."
            )
        }
        
        return f"## Final Notes\n\n{reminders.get(task_type, reminders[TaskType.CODE_REVIEW])}"


def parse_diff_to_structured(
    file_path: str,
    patch: str,
    full_content: Optional[str] = None
) -> StructuredContext:
    """Parse a git diff patch into structured context.
    
    Args:
        file_path: Path to the file
        patch: Git diff patch string
        full_content: Optional full file content
        
    Returns:
        StructuredContext object
    """
    # Detect language from file extension
    ext_to_lang = {
        '.py': 'python',
        '.js': 'javascript',
        '.ts': 'typescript',
        '.tsx': 'typescript',
        '.jsx': 'javascript',
        '.java': 'java',
        '.go': 'go',
        '.rb': 'ruby',
        '.php': 'php',
        '.rs': 'rust',
        '.cpp': 'cpp',
        '.c': 'c',
        '.cs': 'csharp',
        '.swift': 'swift',
        '.kt': 'kotlin'
    }
    
    ext = '.' + file_path.split('.')[-1] if '.' in file_path else ''
    language = ext_to_lang.get(ext.lower(), 'unknown')
    
    # Parse the patch
    changes = []
    current_line = 0
    
    if patch:
        for line in patch.split('\n'):
            # Parse hunk header: @@ -start,count +start,count @@
            hunk_match = re.match(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@', line)
            if hunk_match:
                current_line = int(hunk_match.group(1))
                continue
            
            if line.startswith('+') and not line.startswith('+++'):
                changes.append(DiffChange(
                    line_number=current_line,
                    change_type=ChangeType.ADDED,
                    code=line[1:]  # Remove the + prefix
                ))
                current_line += 1
            elif line.startswith('-') and not line.startswith('---'):
                changes.append(DiffChange(
                    line_number=current_line,
                    change_type=ChangeType.REMOVED,
                    code=line[1:]  # Remove the - prefix
                ))
                # Don't increment line for removed lines
            elif not line.startswith('\\'):  # Ignore "\ No newline at end of file"
                current_line += 1
    
    return StructuredContext(
        file_path=file_path,
        language=language,
        changes=changes,
        full_content=full_content
    )
