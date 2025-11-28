"""Code Analysis Agent for understanding and analyzing code.

This agent orchestrates multiple specialized sub-agents for comprehensive code review.
"""
from typing import Any, Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed

from .base_agent import BaseAgent
from .code_review.naming_reviewer import NamingReviewer
from .code_review.quality_reviewer import QualityReviewer
from .code_review.duplication_detector import DuplicationDetector
from .code_review.pep8_reviewer import PEP8Reviewer
from .filter_pipeline import create_default_pipeline, Finding


class CodeAnalysisAgent(BaseAgent):
    """Orchestrator for code review sub-agents."""
    
    def initialize(self) -> None:
        """Initialize all code review sub-agents."""
        cfg = self.config or {}
        
        # Initialize specialized sub-agents
        self.sub_agents = {
            "naming": NamingReviewer(cfg),
            "quality": QualityReviewer(cfg),
            "duplication": DuplicationDetector(cfg),
            "pep8": PEP8Reviewer(cfg)
        }
        
        # Create filter pipeline
        confidence_threshold = cfg.get("confidence_threshold", 0.5)
        self.filter_pipeline = create_default_pipeline(
            confidence_threshold=confidence_threshold,
            similarity_threshold=85,
            strict_evidence=False
        )
    
    def process(self, code: str, context: str = None) -> Dict[str, Any]:
        """Analyze code using all sub-agents in parallel.
        
        Args:
            code: Source code to analyze
            context: Optional context from vector store
            
        Returns:
            Dict containing filtered findings from all sub-agents
        """
        all_findings: List[Finding] = []
        
        # Run sub-agents in parallel
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_agent = {
                executor.submit(agent.analyze, code, context): name
                for name, agent in self.sub_agents.items()
            }
            
            for future in as_completed(future_to_agent):
                agent_name = future_to_agent[future]
                try:
                    findings = future.result()
                    print(f"{agent_name}: Found {len(findings)} findings")
                    all_findings.extend(findings)
                except Exception as e:
                    print(f"Error in {agent_name}: {e}")
        
        print(f"\nTotal findings before filtering: {len(all_findings)}")
        
        # Apply filter pipeline
        filtered_findings = self.filter_pipeline.process(all_findings)
        
        # Convert to dict format
        suggestions = []
        for finding in filtered_findings:
            suggestions.append(finding.to_dict())
        
        # Generate summary
        analysis_summary = self._generate_summary(filtered_findings)
        
        return {
            "status": "ok",
            "analysis": analysis_summary,
            "suggestions": suggestions,
            "findings_count": len(filtered_findings),
            "findings_by_category": self._group_by_category(filtered_findings),
            "findings_by_severity": self._group_by_severity(filtered_findings)
        }
    
    def _generate_summary(self, findings: List[Finding]) -> str:
        """Generate a text summary of findings."""
        if not findings:
            return "Code analysis complete. No significant issues found."
        
        summary_parts = [f"Found {len(findings)} issues:\n"]
        
        # Group by category
        by_category = self._group_by_category(findings)
        for category, count in by_category.items():
            summary_parts.append(f"- {category}: {count}")
        
        return "\n".join(summary_parts)
    
    def _group_by_category(self, findings: List[Finding]) -> Dict[str, int]:
        """Group findings by category."""
        categories = {}
        for finding in findings:
            categories[finding.category] = categories.get(finding.category, 0) + 1
        return categories
    
    def _group_by_severity(self, findings: List[Finding]) -> Dict[str, int]:
        """Group findings by severity."""
        severities = {}
        for finding in findings:
            severities[finding.severity] = severities.get(finding.severity, 0) + 1
        return severities
    
    def cleanup(self) -> None:
        """Cleanup all sub-agents."""
        for agent in self.sub_agents.values():
            agent.cleanup()