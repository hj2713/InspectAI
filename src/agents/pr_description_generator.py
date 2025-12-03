"""Dynamic PR Description Generator

Analyzes code changes and generates appropriate PR descriptions:
- Bug Fix: Root cause analysis + Fix explanation
- Enhancement/Optimization: Per-file changes description

NO hardcoded titles - generates based on actual code analysis.
"""
from typing import Dict, Any, List, Tuple
from .base_agent import BaseAgent
from ..llm.factory import get_llm_client
from ..utils.logger import get_logger

logger = get_logger(__name__)


class PRDescriptionGenerator(BaseAgent):
    """Dynamically generates PR descriptions based on code changes."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the PR description generator.
        
        Args:
            config: Configuration dict with LLM settings
        """
        super().__init__(config)
        self.llm_client = get_llm_client(provider=config.get("provider", "gemini"))
    
    def initialize(self) -> None:
        """Initialize the agent."""
        logger.info("Initializing PR Description Generator")
    
    def cleanup(self) -> None:
        """Cleanup resources."""
        logger.info("Cleaning up PR Description Generator")
    
    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate PR description by analyzing code changes.
        
        Args:
            input_data: Dict containing:
                - code_changes: List of changed files with diffs
                - bugs: Detected bugs from analysis
                - security: Security findings
                - analysis: Code analysis results
                
        Returns:
            Dict with:
                - pr_type: "bug_fix", "enhancement", "optimization", or "mixed"
                - description: Generated PR description
                - title: Auto-generated one-line PR title
                - status: "success" or "error"
        """
        try:
            code_changes = input_data.get("code_changes", [])
            bugs = input_data.get("bugs", {})
            security = input_data.get("security", {})
            analysis = input_data.get("analysis", {})
            
            # Step 1: Analyze code changes to detect PR type
            pr_type, confidence = self._analyze_pr_type(
                code_changes, bugs, analysis, security
            )
            logger.info(f"PR Type detected: {pr_type} (confidence: {confidence})")
            
            # Step 2: Generate title based on actual changes
            title = self._generate_title(pr_type, code_changes, bugs, analysis)
            logger.info(f"Generated title: {title}")
            
            # Step 3: Generate description based on PR type
            if pr_type == "bug_fix":
                description = self._generate_bug_fix_description(
                    code_changes, bugs, analysis
                )
            else:  # enhancement, optimization, or mixed
                description = self._generate_enhancement_description(
                    code_changes, analysis, bugs
                )
            
            return {
                "status": "success",
                "pr_type": pr_type,
                "title": title,
                "description": description,
                "confidence": confidence
            }
        
        except Exception as e:
            logger.error(f"Error generating PR description: {e}")
            return {
                "status": "error",
                "error": str(e),
                "description": ""
            }
    
    def _analyze_pr_type(
        self, 
        code_changes: List[Dict], 
        bugs: Dict,
        analysis: Dict,
        security: Dict
    ) -> Tuple[str, float]:
        """Analyze code changes to determine PR type.
        
        Returns: (pr_type, confidence_score)
        - "bug_fix": Contains bug fixes
        - "enhancement": New functionality
        - "optimization": Code improvements
        - "mixed": Contains both bug fixes and enhancements
        """
        bug_count = bugs.get("bug_count", 0)
        bug_severity = bugs.get("bugs", [])
        
        # Analyze file patterns
        files_added = sum(1 for c in code_changes if c.get("status") == "added")
        files_modified = sum(1 for c in code_changes if c.get("status") == "modified")
        files_deleted = sum(1 for c in code_changes if c.get("status") == "deleted")
        
        # Calculate code metrics
        total_additions = sum(c.get("additions", 0) for c in code_changes)
        total_deletions = sum(c.get("deletions", 0) for c in code_changes)
        
        # Detect patterns
        has_bugs = bug_count > 0
        has_security_issues = security.get("vulnerability_count", 0) > 0
        
        # Check for new files (feature indicator)
        has_new_files = files_added > 0
        
        # Check for refactoring (more deletions = cleanup/optimization)
        is_refactoring = total_deletions > total_additions and total_deletions > 20
        
        # Check analysis for keywords
        suggestions = analysis.get("suggestions", [])
        suggestion_text = " ".join(suggestions).lower()
        
        refactor_keywords = ["refactor", "optimize", "improve", "clean", "performance"]
        is_optimization_suggested = any(kw in suggestion_text for kw in refactor_keywords)
        
        # Decision logic
        if has_bugs and not has_new_files:
            # Clear bug fix
            confidence = 0.95 if bug_severity else 0.80
            return "bug_fix", confidence
        
        elif has_bugs and has_new_files:
            # Both bug fixes and new features
            confidence = 0.75
            return "mixed", confidence
        
        elif has_new_files and not is_refactoring:
            # New functionality
            confidence = 0.90
            return "enhancement", confidence
        
        elif is_refactoring or is_optimization_suggested:
            # Code cleanup/optimization
            confidence = 0.85
            return "optimization", confidence
        
        else:
            # Default to enhancement if any changes
            confidence = 0.60
            return "enhancement", confidence
    
    def _generate_title(
        self,
        pr_type: str,
        code_changes: List[Dict],
        bugs: Dict,
        analysis: Dict
    ) -> str:
        """Generate a one-line PR title based on actual changes.
        
        Title format: [Action] description
        Examples:
        - "Fix race condition in token validation"
        - "Add multi-language support for error messages"
        - "Improve database query performance"
        """
        try:
            # Build context from actual changes
            file_context = self._get_file_context(code_changes)
            bug_context = self._get_bug_context(bugs) if bugs.get("bug_count", 0) > 0 else ""
            analysis_context = self._get_analysis_context(analysis)
            
            # Create prompt with actual data
            prompt = f"""Generate a ONE-LINE PR title (max 60 chars) based on these ACTUAL code changes:

Files Changed: {file_context}
{f'Bugs: {bug_context}' if bug_context else ''}
{f'Analysis: {analysis_context}' if analysis_context else ''}
Type: {pr_type}

Rules:
- Start with action verb: Fix, Add, Update, Improve, Refactor, etc
- Be specific about WHAT changed
- Max 60 characters
- NO quotes, NO explanation, ONLY the title

Generate ONLY the title:"""
            
            response = self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=50
            )
            
            title = response.strip().strip('"\'')
            
            # Validate
            if not title or len(title) < 5:
                title = f"Update {pr_type.replace('_', ' ')}"
            
            return title[:60]
        
        except Exception as e:
            logger.warning(f"Failed to generate title: {e}")
            return f"Update code ({pr_type})"
    
    def _generate_bug_fix_description(
        self,
        code_changes: List[Dict],
        bugs: Dict,
        analysis: Dict
    ) -> str:
        """Generate description for bug fix PR.
        
        Format:
        ## One-line fix summary
        
        ### Root Cause Analysis
        - [HIGH] Bug description
        
        ### Fix
        - What was changed
        - How files were modified
        """
        parts = []
        
        bug_list = bugs.get("bugs", [])
        bug_descriptions = [b.get("description", "") for b in bug_list]
        
        # 1. Summary from bug descriptions
        summary = self._generate_bug_summary(bug_descriptions, code_changes)
        parts.append(f"## {summary}\n")
        
        # 2. Root Cause Analysis
        parts.append("### Root Cause Analysis\n")
        for bug in bug_list[:3]:  # Top 3 bugs
            severity = bug.get("severity", "INFO")
            description = bug.get("description", "")
            parts.append(f"**[{severity}]** {description}")
        parts.append("")
        
        # 3. Fix details from actual code changes
        parts.append("### Fix\n")
        fix_details = self._analyze_code_changes(code_changes)
        parts.append(fix_details)
        parts.append("")
        
        # 4. Files modified
        parts.append("### Modified Files\n")
        files_info = self._describe_modified_files(code_changes)
        parts.append(files_info)
        
        return "\n".join(parts)
    
    def _generate_enhancement_description(
        self,
        code_changes: List[Dict],
        analysis: Dict,
        bugs: Dict
    ) -> str:
        """Generate description for enhancement/optimization PR.
        
        Format:
        ## One-line summary
        
        ### Changes by File
        - File 1: What changed
        - File 2: What changed
        """
        parts = []
        
        # 1. Summary
        summary = self._generate_enhancement_summary(code_changes, analysis)
        parts.append(f"## {summary}\n")
        
        # 2. Description
        parts.append("### Changes by File\n")
        file_changes = self._describe_all_file_changes(code_changes)
        parts.append(file_changes)
        parts.append("")
        
        # 3. Impact/Benefits
        parts.append("### Impact\n")
        impact = self._describe_impact(code_changes, analysis)
        parts.append(impact)
        
        # 4. If bugs were fixed too
        if bugs.get("bug_count", 0) > 0:
            parts.append("\n### Issues Addressed\n")
            for bug in bugs.get("bugs", [])[:2]:
                severity = bug.get("severity", "")
                description = bug.get("description", "")
                parts.append(f"- [{severity}] {description}")
        
        return "\n".join(parts)
    
    def _get_file_context(self, code_changes: List[Dict]) -> str:
        """Extract file names and types from changes."""
        if not code_changes:
            return "No files"
        
        files = []
        for change in code_changes[:5]:
            filename = change.get("filename", "").split("/")[-1]  # Just filename
            status = change.get("status", "modified")
            files.append(f"{status}: {filename}")
        
        return ", ".join(files)
    
    def _get_bug_context(self, bugs: Dict) -> str:
        """Extract bug information."""
        bug_list = bugs.get("bugs", [])
        if not bug_list:
            return ""
        
        descriptions = [b.get("description", "")[:40] for b in bug_list[:2]]
        return ", ".join(descriptions)
    
    def _get_analysis_context(self, analysis: Dict) -> str:
        """Extract analysis suggestions."""
        suggestions = analysis.get("suggestions", [])
        if not suggestions:
            return ""
        
        return ", ".join(suggestions[:2])
    
    def _generate_bug_summary(self, bug_descriptions: List[str], code_changes: List[Dict]) -> str:
        """Generate one-line summary from bug descriptions."""
        if not bug_descriptions:
            return "Fix code issues"
        
        # Use first bug description
        summary = bug_descriptions[0]
        
        # Capitalize first letter
        if summary:
            summary = "Fix " + summary[0].lower() + summary[1:]
        
        # Limit length
        if len(summary) > 70:
            summary = summary[:67] + "..."
        
        return summary
    
    def _generate_enhancement_summary(self, code_changes: List[Dict], analysis: Dict) -> str:
        """Generate one-line summary for enhancement."""
        # Check for new files
        added_files = [c.get("filename", "") for c in code_changes if c.get("status") == "added"]
        
        if added_files:
            # Extract feature name from file path
            feature = added_files[0].split("/")[0]
            return f"Add {feature} functionality"
        
        # Check analysis
        suggestions = analysis.get("suggestions", [])
        if suggestions:
            return f"Update code - {suggestions[0]}"
        
        return "Update codebase"
    
    def _analyze_code_changes(self, code_changes: List[Dict]) -> str:
        """Analyze code changes to describe what was fixed."""
        details = []
        
        for change in code_changes[:3]:
            filename = change.get("filename", "")
            additions = change.get("additions", 0)
            deletions = change.get("deletions", 0)
            
            if additions > deletions:
                action = "Added logic"
            elif deletions > additions:
                action = "Removed problematic code"
            else:
                action = "Modified"
            
            details.append(f"- {action} in `{filename}` (+{additions}/-{deletions})")
        
        return "\n".join(details) if details else "Code refactored to fix issues"
    
    def _describe_modified_files(self, code_changes: List[Dict]) -> str:
        """Describe all modified files."""
        files = []
        
        for change in code_changes:
            filename = change.get("filename", "")
            status = change.get("status", "modified")
            additions = change.get("additions", 0)
            deletions = change.get("deletions", 0)
            
            files.append(f"- `{filename}` ({status}) +{additions}/-{deletions}")
        
        return "\n".join(files) if files else "No files changed"
    
    def _describe_all_file_changes(self, code_changes: List[Dict]) -> str:
        """Describe changes in each file."""
        descriptions = []
        
        for i, change in enumerate(code_changes, 1):
            filename = change.get("filename", "")
            status = change.get("status", "modified")
            additions = change.get("additions", 0)
            deletions = change.get("deletions", 0)
            
            # Determine what changed based on metrics
            if status == "added":
                what_changed = "New file with implementation"
            elif additions > deletions * 2:
                what_changed = "Added new functionality"
            elif deletions > additions:
                what_changed = "Code cleanup and refactoring"
            else:
                what_changed = "Code updates"
            
            descriptions.append(f"**{i}. `{filename}`** ({status})")
            descriptions.append(f"   - Lines: +{additions}/-{deletions}")
            descriptions.append(f"   - Changes: {what_changed}")
        
        return "\n".join(descriptions) if descriptions else "No changes"
    
    def _describe_impact(self, code_changes: List[Dict], analysis: Dict) -> str:
        """Describe impact of changes."""
        impacts = []
        
        total_additions = sum(c.get("additions", 0) for c in code_changes)
        
        if total_additions > 100:
            impacts.append("- Significant new functionality added")
        elif total_additions > 50:
            impacts.append("- Moderate improvements implemented")
        else:
            impacts.append("- Code improvements applied")
        
        suggestions = analysis.get("suggestions", [])
        if suggestions:
            for suggestion in suggestions[:2]:
                impacts.append(f"- {suggestion}")
        
        impacts.append("- No breaking changes")
        
        return "\n".join(impacts)
