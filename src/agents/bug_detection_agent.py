"""Bug Detection Agent for identifying bugs and errors in code.

This agent orchestrates multiple specialized sub-agents for comprehensive bug detection.
"""
from typing import Any, Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

from .base_agent import BaseAgent
from .bug_detection.logic_error_detector import LogicErrorDetector
from .bug_detection.edge_case_analyzer import EdgeCaseAnalyzer
from .bug_detection.type_error_detector import TypeErrorDetector
from .bug_detection.runtime_issue_detector import RuntimeIssueDetector
from .filter_pipeline import create_default_pipeline, Finding

# Set up logger
logger = logging.getLogger(__name__)


class BugDetectionAgent(BaseAgent):
    """Orchestrator for bug detection sub-agents."""
    
    def initialize(self) -> None:
        """Initialize all bug detection sub-agents."""
        cfg = self.config or {}
        
        logger.info(f"[BugDetectionAgent] Initializing with config: {cfg}")
        
        # Initialize specialized sub-agents
        self.sub_agents = {
            "logic_errors": LogicErrorDetector(cfg),
            "edge_cases": EdgeCaseAnalyzer(cfg),
            "type_errors": TypeErrorDetector(cfg),
            "runtime_issues": RuntimeIssueDetector(cfg)
        }
        
        logger.info(f"[BugDetectionAgent] Initialized {len(self.sub_agents)} sub-agents: {list(self.sub_agents.keys())}")
        
        # Create filter pipeline with higher confidence threshold for bugs
        confidence_threshold = cfg.get("confidence_threshold", 0.6)
        self.filter_pipeline = create_default_pipeline(
            confidence_threshold=confidence_threshold,
            similarity_threshold=85,
            strict_evidence=False
        )
        logger.info(f"[BugDetectionAgent] Filter pipeline created with confidence_threshold={confidence_threshold}")
    
    def process(self, code: str) -> Dict[str, Any]:
        """Analyze code using all bug detection sub-agents in parallel.
        
        Args:
            code: Source code to analyze
            
        Returns:
            Dict containing filtered bug findings from all sub-agents
        """
        logger.info(f"[BugDetectionAgent] Processing code, length={len(code)}")
        logger.info(f"[BugDetectionAgent] Code preview (first 500 chars):\n{code[:500]}")
        
        all_findings: List[Finding] = []
        
        # Run sub-agents in parallel
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_agent = {
                executor.submit(agent.analyze, code): name
                for name, agent in self.sub_agents.items()
            }
            
            for future in as_completed(future_to_agent):
                agent_name = future_to_agent[future]
                try:
                    findings = future.result()
                    logger.info(f"[BugDetectionAgent] {agent_name}: Found {len(findings)} bugs")
                    for i, finding in enumerate(findings):
                        logger.debug(f"[BugDetectionAgent] {agent_name} finding {i}: {finding.to_dict()}")
                    all_findings.extend(findings)
                except Exception as e:
                    logger.error(f"[BugDetectionAgent] Error in {agent_name}: {e}", exc_info=True)
        
        logger.info(f"[BugDetectionAgent] Total bugs before filtering: {len(all_findings)}")
        
        # Apply filter pipeline
        filtered_findings = self.filter_pipeline.process(all_findings)
        logger.info(f"[BugDetectionAgent] Total bugs after filtering: {len(filtered_findings)}")
        
        # Convert to structured bug format
        bugs = []
        for finding in filtered_findings:
            bug = finding.to_dict()
            bugs.append(bug)
        
        # Generate analysis summary
        analysis_summary = self._generate_summary(filtered_findings)
        
        result = {
            "status": "ok",
            "raw_analysis": analysis_summary,
            "bugs": bugs,
            "bug_count": len(filtered_findings),
            "bugs_by_severity": self._group_by_severity(filtered_findings),
            "bugs_by_category": self._group_by_category(filtered_findings)
        }
        
        logger.info(f"[BugDetectionAgent] Returning result with {result['bug_count']} bugs")
        return result
    
    def _generate_summary(self, findings: List[Finding]) -> str:
        """Generate a text summary of bug findings."""
        if not findings:
            return "Bug detection complete. No significant bugs found."
        
        summary_parts = [f"Detected {len(findings)} potential bugs:\n"]
        
        # Group by severity
        by_severity = self._group_by_severity(findings)
        for severity in ["critical", "high", "medium", "low"]:
            if severity in by_severity:
                count = by_severity[severity]
                summary_parts.append(f"- {severity.capitalize()}: {count}")
        
        return "\n".join(summary_parts)
    
    def _group_by_severity(self, findings: List[Finding]) -> Dict[str, int]:
        """Group findings by severity."""
        severities = {}
        for finding in findings:
            severities[finding.severity] = severities.get(finding.severity, 0) + 1
        return severities
    
    def _group_by_category(self, findings: List[Finding]) -> Dict[str, int]:
        """Group findings by category."""
        categories = {}
        for finding in findings:
            categories[finding.category] = categories.get(finding.category, 0) + 1
        return categories
    
    def cleanup(self) -> None:
        """Cleanup all sub-agents."""
        for agent in self.sub_agents.values():
            agent.cleanup()
