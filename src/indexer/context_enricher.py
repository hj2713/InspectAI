"""Context Enrichment - Add codebase context to PR reviews.

This module:
- Queries the codebase index for relevant context
- Extracts changed lines from diffs
- Builds enriched context for the AI reviewer
"""

import re
import logging
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger(__name__)

from .indexer import get_codebase_indexer


class ContextEnricher:
    """Enriches PR review context with codebase knowledge."""
    
    def __init__(self):
        """Initialize the context enricher."""
        self.indexer = get_codebase_indexer()
    
    async def enrich_file_context(
        self,
        repo_full_name: str,
        file_path: str,
        diff_patch: str
    ) -> Dict[str, Any]:
        """Enrich context for a file being reviewed.
        
        Args:
            repo_full_name: Full repo name
            file_path: Path to the file
            diff_patch: Git diff patch for the file
            
        Returns:
            Enriched context dict with:
            - impacted_symbols: Symbols changed and their impact
            - callers: Functions that call changed code
            - dependents: Files that import this file
            - risk_level: HIGH/MEDIUM/LOW
        """
        # Get project
        project = await self.indexer.get_project(repo_full_name)
        
        if not project:
            logger.debug(f"Project {repo_full_name} not indexed yet")
            return self._empty_context()
        
        project_id = project["id"]
        
        # Extract changed lines from diff
        changed_lines = self._extract_changed_lines(diff_patch)
        
        if not changed_lines:
            return self._empty_context()
        
        # Get impact analysis
        impact = await self.indexer.get_change_impact(
            project_id=project_id,
            file_path=file_path,
            changed_lines=changed_lines
        )
        
        # Get file dependents
        dependents = await self.indexer.get_file_dependents(
            project_id=project_id,
            file_path=file_path
        )
        
        # Collect all callers for changed symbols
        all_callers = []
        for symbol in impact:
            callers = await self.indexer.get_symbol_callers(
                project_id=project_id,
                symbol_name=symbol["symbol_name"]
            )
            for caller in callers:
                caller["called_symbol"] = symbol["symbol_name"]
                all_callers.append(caller)
        
        # Calculate overall risk level
        risk_level = self._calculate_risk_level(impact, all_callers, dependents)
        
        return {
            "impacted_symbols": impact,
            "callers": all_callers,
            "dependents": dependents,
            "risk_level": risk_level,
            "changed_lines": changed_lines,
            "total_impact_count": len(all_callers) + len(dependents)
        }
    
    def _extract_changed_lines(self, diff_patch: str) -> List[int]:
        """Extract line numbers that were changed from a diff patch.
        
        Args:
            diff_patch: Git diff in unified format
            
        Returns:
            List of line numbers that were added/modified
        """
        if not diff_patch:
            return []
        
        changed_lines = []
        current_line = 0
        
        for line in diff_patch.split('\n'):
            # Parse hunk header: @@ -old_start,old_count +new_start,new_count @@
            hunk_match = re.match(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@', line)
            
            if hunk_match:
                current_line = int(hunk_match.group(1))
                continue
            
            if line.startswith('+') and not line.startswith('+++'):
                # Added line
                changed_lines.append(current_line)
                current_line += 1
            elif line.startswith('-') and not line.startswith('---'):
                # Deleted line - don't increment (line doesn't exist in new file)
                pass
            else:
                # Context line or unchanged
                if not line.startswith('\\'):  # Not "\ No newline at end of file"
                    current_line += 1
        
        return changed_lines
    
    def _calculate_risk_level(
        self,
        impacted_symbols: List[Dict],
        callers: List[Dict],
        dependents: List[Dict]
    ) -> str:
        """Calculate overall risk level for changes.
        
        Args:
            impacted_symbols: Symbols that were changed
            callers: Functions that call changed symbols
            dependents: Files that depend on changed file
            
        Returns:
            "HIGH", "MEDIUM", or "LOW"
        """
        # Count high-impact symbols
        high_impact_count = sum(
            1 for s in impacted_symbols 
            if s.get("impact_level") == "HIGH"
        )
        
        total_callers = len(callers)
        total_dependents = len(dependents)
        
        # Risk calculation
        if high_impact_count > 0 or total_callers > 10:
            return "HIGH"
        elif total_callers > 3 or total_dependents > 5:
            return "MEDIUM"
        else:
            return "LOW"
    
    def _empty_context(self) -> Dict[str, Any]:
        """Return empty context structure."""
        return {
            "impacted_symbols": [],
            "callers": [],
            "dependents": [],
            "risk_level": "UNKNOWN",
            "changed_lines": [],
            "total_impact_count": 0
        }
    
    def format_context_for_prompt(self, context: Dict[str, Any]) -> str:
        """Format enriched context as text for the AI prompt.
        
        Args:
            context: Enriched context dict from enrich_file_context
            
        Returns:
            Formatted string to add to the review prompt
        """
        if context["total_impact_count"] == 0:
            return ""
        
        lines = []
        lines.append("\n## CODEBASE CONTEXT (Impact Analysis)")
        lines.append(f"**Risk Level: {context['risk_level']}**\n")
        
        # Impacted symbols
        if context["impacted_symbols"]:
            lines.append("### Changed Symbols:")
            for symbol in context["impacted_symbols"][:10]:  # Limit to 10
                caller_count = symbol.get("caller_count", 0)
                impact = symbol.get("impact_level", "UNKNOWN")
                lines.append(
                    f"- `{symbol['symbol_name']}` ({symbol['symbol_type']}) "
                    f"- **{caller_count} callers** [{impact} impact]"
                )
        
        # Callers
        if context["callers"]:
            lines.append("\n### Functions That Call This Code:")
            # Group by file
            by_file: Dict[str, List] = {}
            for caller in context["callers"]:
                file = caller.get("caller_file", "unknown")
                if file not in by_file:
                    by_file[file] = []
                by_file[file].append(caller)
            
            for file, callers in list(by_file.items())[:5]:  # Limit to 5 files
                lines.append(f"- **{file}**:")
                for caller in callers[:3]:  # Limit to 3 per file
                    func = caller.get("caller_function") or "module level"
                    line = caller.get("call_line", "?")
                    called = caller.get("called_symbol", "?")
                    lines.append(f"  - `{func}` calls `{called}` (line {line})")
        
        # Dependents
        if context["dependents"]:
            lines.append("\n### Files That Import This File:")
            for dep in context["dependents"][:5]:  # Limit to 5
                lines.append(f"- `{dep.get('dependent_file', 'unknown')}`")
        
        # Warning for high risk
        if context["risk_level"] == "HIGH":
            lines.append("\n⚠️ **HIGH RISK CHANGE**: This code has many dependents. "
                        "Breaking changes could affect multiple parts of the codebase.")
        
        return "\n".join(lines)
    
    async def enrich_pr_context(
        self,
        repo_full_name: str,
        changed_files: List[str],
        diff_content: str
    ) -> Dict[str, Any]:
        """Enrich context for an entire PR with multiple files.
        
        This is a convenience method for PR reviews that aggregates
        context across all changed files.
        
        Args:
            repo_full_name: Full repo name (owner/repo)
            changed_files: List of file paths that changed
            diff_content: Combined diff content
            
        Returns:
            Dict with:
            - file_contexts: Per-file context dicts
            - context_summary: List of summary strings
            - overall_risk: HIGH/MEDIUM/LOW
        """
        # Check if indexing is available for this project
        project = await self.indexer.get_project(repo_full_name)
        
        if not project:
            # Project not indexed - return empty context gracefully
            logger.debug(f"No index available for {repo_full_name}, skipping context enrichment")
            return {
                "file_contexts": {},
                "context_summary": [],
                "overall_risk": "UNKNOWN"
            }
        
        file_contexts = {}
        context_summary = []
        max_risk = "LOW"
        
        for file_path in changed_files:
            try:
                # Get per-file context
                file_ctx = await self.enrich_file_context(
                    repo_full_name=repo_full_name,
                    file_path=file_path,
                    diff_patch=diff_content  # Note: ideally should extract per-file diff
                )
                
                if file_ctx.get("total_impact_count", 0) > 0:
                    file_contexts[file_path] = {
                        "callers": {
                            s["symbol_name"]: [c["caller_function"] for c in file_ctx.get("callers", []) 
                                              if c.get("called_symbol") == s["symbol_name"]][:5]
                            for s in file_ctx.get("impacted_symbols", [])
                        },
                        "dependencies": {},  # Simplified for now
                        "impact_score": file_ctx.get("total_impact_count", 0)
                    }
                    
                    # Update max risk
                    risk = file_ctx.get("risk_level", "LOW")
                    if risk == "HIGH":
                        max_risk = "HIGH"
                    elif risk == "MEDIUM" and max_risk != "HIGH":
                        max_risk = "MEDIUM"
                    
                    # Add to summary
                    for symbol in file_ctx.get("impacted_symbols", [])[:3]:
                        caller_count = symbol.get("caller_count", 0)
                        if caller_count > 0:
                            context_summary.append(
                                f"`{symbol['symbol_name']}` has {caller_count} callers"
                            )
                            
            except Exception as e:
                logger.debug(f"Could not enrich context for {file_path}: {e}")
                continue
        
        return {
            "file_contexts": file_contexts,
            "context_summary": context_summary,
            "overall_risk": max_risk
        }


# Singleton instance
_enricher_instance: Optional[ContextEnricher] = None


def get_context_enricher() -> ContextEnricher:
    """Get or create the singleton ContextEnricher instance."""
    global _enricher_instance
    
    if _enricher_instance is None:
        _enricher_instance = ContextEnricher()
    
    return _enricher_instance


async def get_enriched_context(
    repo_full_name: str,
    file_path: str,
    diff_patch: str
) -> str:
    """Convenience function to get formatted context for a file.
    
    Args:
        repo_full_name: Full repo name
        file_path: Path to the file
        diff_patch: Git diff patch
        
    Returns:
        Formatted context string (or empty string if no context)
    """
    enricher = get_context_enricher()
    context = await enricher.enrich_file_context(repo_full_name, file_path, diff_patch)
    return enricher.format_context_for_prompt(context)
