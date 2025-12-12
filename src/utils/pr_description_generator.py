"""
PR Description Generator - Automatically generates GitHub PR descriptions.

Generates human-readable summaries of PR changes in the style of GitHub Copilot AI,
with LLM-powered analysis to explain the logical changes.

Features:
- What changed (files modified, added, removed)
- Why it changed (LLM analyzes diffs to explain logic changes)
- Key statistics (additions, deletions, files touched)
- Human-readable explanations of each file's changes
- Clear formatting similar to GitHub's PR review style
"""

from typing import List, Dict, Any, Optional
import re
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class FileChange:
    """Represents a file change in the PR."""
    filename: str
    status: str  # "added", "modified", "removed"
    additions: int
    deletions: int
    changes: int
    diff: Optional[str] = None  # The actual diff content for LLM analysis
    explanation: Optional[str] = None  # LLM-generated explanation


def analyze_diff_with_llm(filename: str, diff: str, llm_client=None) -> str:
    """
    Analyze a code diff using LLM to generate human-readable explanation.
    
    Args:
        filename: The name of the changed file
        diff: The git diff content
        llm_client: Optional LLM client (uses Gemini by default)
    
    Returns:
        Human-readable explanation of the changes
    """
    if not diff or not diff.strip():
        return "No diff available"
    
    try:
        # Import here to avoid circular imports
        from src.llm.factory import get_llm_client
        
        if llm_client is None:
            llm_client = get_llm_client()
        
        # Create prompt for diff analysis
        prompt = f"""Analyze this code diff and provide a brief, human-readable explanation (1-2 sentences max) of what changed and why.

File: {filename}

Diff:
```diff
{diff[:2000]}
```

Focus on:
- What functionality changed
- Any significant logic changes
- Why this change was likely made

Keep it concise and technical. Don't mention file stats."""
        
        # Call LLM using chat method (synchronous)
        messages = [{"role": "user", "content": prompt}]
        response = llm_client.chat(
            messages=messages,
            max_tokens=200,
            temperature=0.3
        )
        
        explanation = response.strip() if response else "Changes to this file"
        logger.info(f"[PR_DESC] LLM analysis for {filename}: {explanation[:100]}...")
        return explanation
        
    except Exception as e:
        logger.warning(f"[PR_DESC] LLM analysis failed for {filename}: {e}")
        return f"Modified {filename}"


class PRDescriptionGenerator:
    """Generates GitHub PR descriptions in Copilot AI style."""

    def __init__(self):
        """Initialize the PR description generator."""
        self.file_categories = {
            "tests": [".test.py", ".spec.py", "test_", "_test.py", "tests/"],
            "docs": [".md", ".rst", ".txt", "docs/", "README", "CHANGELOG"],
            "config": ["config/", ".yml", ".yaml", ".json", ".toml", ".cfg", "setup.py", "package.json"],
            "ci": [".github/", ".gitlab-ci.yml", "Jenkinsfile", ".circleci"],
            "types": [".pyi", "py.typed"],
        }

    def categorize_file(self, filename: str) -> str:
        """Categorize a file by type."""
        filename_lower = filename.lower()
        
        for category, patterns in self.file_categories.items():
            if any(pattern in filename_lower for pattern in patterns):
                return category
        
        # Determine by extension
        if filename.endswith(".py"):
            return "python"
        elif filename.endswith((".js", ".ts", ".jsx", ".tsx")):
            return "javascript"
        elif filename.endswith((".java", ".kt")):
            return "java"
        elif filename.endswith((".go",)):
            return "go"
        elif filename.endswith((".rb",)):
            return "ruby"
        else:
            return "other"

    def extract_key_functions(self, files_changed: List[FileChange], limit: int = 3) -> List[str]:
        """Extract key changed files (modified/removed, not tests/docs)."""
        main_files = [
            f.filename for f in files_changed
            if f.status in ["modified", "removed"] and self.categorize_file(f.filename) not in ["tests", "docs", "config"]
        ]
        return main_files[:limit]

    def generate_description(
        self,
        pr_title: str,
        pr_body: Optional[str],
        files_changed: List[FileChange],
        commit_messages: Optional[List[str]] = None,
    ) -> str:
        """
        Generate a PR description in Copilot AI style.

        Args:
            pr_title: The PR title
            pr_body: Existing PR body/description (optional)
            files_changed: List of FileChange objects
            commit_messages: List of commit messages for context

        Returns:
            Formatted PR description string
        """
        parts = []

        # 1. Pull request overview with main files
        key_files = self.extract_key_functions(files_changed)
        
        overview = self._generate_overview(pr_title, key_files, files_changed)
        parts.append(overview)

        # 2. Key Changes section
        key_changes = self._generate_key_changes(files_changed)
        if key_changes:
            parts.append("\n## Key Changes\n")
            parts.append(key_changes)

        # 3. File Summary (breakdown by type)
        file_summary = self._generate_file_summary(files_changed)
        if file_summary:
            parts.append("\n## Files Changed\n")
            parts.append(file_summary)

        # 4. Statistics
        stats = self._generate_statistics(files_changed)
        parts.append("\n## Statistics\n")
        parts.append(stats)

        # 5. Testing considerations (if tests were modified)
        if any(f.status == "added" and "test" in f.filename.lower() for f in files_changed):
            parts.append("\n## Testing\n")
            parts.append("Tests have been added to verify the changes.\n")

        return "".join(parts)

    def _generate_overview(
        self,
        pr_title: str,
        key_files: List[str],
        files_changed: List[FileChange],
    ) -> str:
        """Generate the overview section."""
        total_files = len(files_changed)
        added_files = sum(1 for f in files_changed if f.status == "added")
        modified_files = sum(1 for f in files_changed if f.status == "modified")
        removed_files = sum(1 for f in files_changed if f.status == "removed")

        overview = f"# {pr_title}\n\n"
        overview += "## Pull request overview\n"

        # Main description
        if key_files:
            file_list = ", ".join([f"`{f}`" for f in key_files])
            overview += f"This PR updates {file_list}"
        else:
            overview += "This PR makes updates to the codebase"

        # Summary stats
        changes = []
        if modified_files > 0:
            changes.append(f"modifying {modified_files} file{'s' if modified_files != 1 else ''}")
        if added_files > 0:
            changes.append(f"adding {added_files} new file{'s' if added_files != 1 else ''}")
        if removed_files > 0:
            changes.append(f"removing {removed_files} file{'s' if removed_files != 1 else ''}")

        if changes:
            overview += ", " + ", ".join(changes) + "."
        else:
            overview += "."

        overview += f"\n\n"

        return overview

    def _generate_key_changes(self, files_changed: List[FileChange]) -> str:
        """Generate the Key Changes section with LLM explanations."""
        # Group changes by type
        added = [f for f in files_changed if f.status == "added"]
        modified = [f for f in files_changed if f.status == "modified"]
        removed = [f for f in files_changed if f.status == "removed"]

        changes_lines = []

        if modified:
            changes_lines.append("**Modified files:**")
            for f in modified[:5]:  # Show top 5
                explanation = f.explanation or f"Modified `{f.filename}`"
                changes_lines.append(f"- `{f.filename}` (+{f.additions}/-{f.deletions})")
                changes_lines.append(f"  - {explanation}")
            if len(modified) > 5:
                changes_lines.append(f"- ...and {len(modified) - 5} more modified files")

        if added:
            if changes_lines:
                changes_lines.append("")
            changes_lines.append("**Added files:**")
            for f in added[:5]:
                explanation = f.explanation or f"New file with {f.additions} lines"
                changes_lines.append(f"- `{f.filename}` ({f.additions} lines)")
                if explanation and "new" not in explanation.lower():
                    changes_lines.append(f"  - {explanation}")
            if len(added) > 5:
                changes_lines.append(f"- ...and {len(added) - 5} more new files")

        if removed:
            if changes_lines:
                changes_lines.append("")
            changes_lines.append("**Removed files:**")
            for f in removed[:5]:
                changes_lines.append(f"- `{f.filename}`")
            if len(removed) > 5:
                changes_lines.append(f"- ...and {len(removed) - 5} more removed files")

        return "\n".join(changes_lines) if changes_lines else ""

    def _generate_file_summary(self, files_changed: List[FileChange]) -> str:
        """Generate file category summary."""
        categories = {}
        for f in files_changed:
            cat = self.categorize_file(f.filename)
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(f)

        summary_lines = []

        for category in ["python", "javascript", "java", "go", "ruby", "tests", "docs", "config", "ci", "other"]:
            if category in categories:
                files = categories[category]
                count = len(files)
                
                # Calculate totals for this category
                total_add = sum(f.additions for f in files)
                total_del = sum(f.deletions for f in files)
                
                cat_name = category.capitalize()
                if category == "tests":
                    cat_name = "Tests"
                elif category == "docs":
                    cat_name = "Documentation"
                elif category == "config":
                    cat_name = "Configuration"
                elif category == "ci":
                    cat_name = "CI/CD"
                elif category == "javascript":
                    cat_name = "JavaScript/TypeScript"

                summary_lines.append(f"- **{cat_name}**: {count} file{'s' if count != 1 else ''} (+{total_add}/-{total_del})")

        return "\n".join(summary_lines) if summary_lines else ""

    def _generate_statistics(self, files_changed: List[FileChange]) -> str:
        """Generate statistics section."""
        total_files = len(files_changed)
        total_additions = sum(f.additions for f in files_changed)
        total_deletions = sum(f.deletions for f in files_changed)
        
        added_files = sum(1 for f in files_changed if f.status == "added")
        modified_files = sum(1 for f in files_changed if f.status == "modified")
        removed_files = sum(1 for f in files_changed if f.status == "removed")

        stats = f"""| Metric | Value |
|--------|-------|
| **Files changed** | {total_files} |
| **Files added** | {added_files} |
| **Files modified** | {modified_files} |
| **Files removed** | {removed_files} |
| **Total additions** | +{total_additions} |
| **Total deletions** | -{total_deletions} |
| **Net change** | +{total_additions - total_deletions} |
"""
        return stats

    def generate_changelog_description(
        self,
        files_changed: List[FileChange],
        pr_title: Optional[str] = None,
    ) -> str:
        """
        Generate a changelog-style PR description with LLM explanations.

        Suitable for automatically generated descriptions that focus on:
        - What files were modified/added/removed
        - Line statistics
        - Human-readable explanations of what changed logically
        - Clean summary suitable for release notes

        Args:
            files_changed: List of FileChange objects
            pr_title: Optional PR title to include

        Returns:
            Changelog-style description with LLM explanations
        """
        parts = []

        if pr_title:
            parts.append(f"## {pr_title}\n")

        parts.append("### Modified\n")
        modified = [f for f in files_changed if f.status == "modified"]
        if modified:
            for f in modified:
                parts.append(f"- `{f.filename}` (+{f.additions}/-{f.deletions})\n")
                if f.explanation:
                    parts.append(f"  > {f.explanation}\n")
        else:
            parts.append("_No files modified_\n")

        parts.append("\n### Added\n")
        added = [f for f in files_changed if f.status == "added"]
        if added:
            for f in added:
                parts.append(f"- `{f.filename}` ({f.additions} lines)\n")
                if f.explanation:
                    parts.append(f"  > {f.explanation}\n")
        else:
            parts.append("_No new files_\n")

        parts.append("\n### Removed\n")
        removed = [f for f in files_changed if f.status == "removed"]
        if removed:
            for f in removed:
                parts.append(f"- `{f.filename}`\n")
        else:
            parts.append("_No files removed_\n")

        # Summary
        total_add = sum(f.additions for f in files_changed)
        total_del = sum(f.deletions for f in files_changed)
        total_files = len(files_changed)

        parts.append(f"\n### Summary\n")
        parts.append(f"- **{total_files}** files changed\n")
        parts.append(f"- **+{total_add}** additions\n")
        parts.append(f"- **-{total_del}** deletions\n")

        return "".join(parts)


def format_file_change(
    filename: str,
    status: str,
    additions: int = 0,
    deletions: int = 0,
) -> FileChange:
    """Helper to create FileChange objects."""
    return FileChange(
        filename=filename,
        status=status,
        additions=additions,
        deletions=deletions,
        changes=additions + deletions,
    )
