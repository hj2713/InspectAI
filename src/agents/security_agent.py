"""Security Analysis Agent for identifying vulnerabilities in code.

This agent orchestrates multiple specialized sub-agents for comprehensive security analysis.
"""
from typing import Any, Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed

from .base_agent import BaseAgent
from .security.injection_scanner import InjectionScanner
from .security.auth_scanner import AuthScanner
from .security.data_exposure_scanner import DataExposureScanner
from .security.dependency_scanner import DependencyScanner
from .filter_pipeline import create_default_pipeline, Finding


class SecurityAnalysisAgent(BaseAgent):
    """Orchestrator for security analysis sub-agents."""
    
    def initialize(self) -> None:
        """Initialize all security sub-agents."""
        cfg = self.config or {}
        
        # Initialize specialized sub-agents
        self.sub_agents = {
            "injection": InjectionScanner(cfg),
            "auth": AuthScanner(cfg),
            "data_exposure": DataExposureScanner(cfg),
            "dependencies": DependencyScanner(cfg)
        }
        
        # Create filter pipeline with high confidence threshold for security
        confidence_threshold = cfg.get("confidence_threshold", 0.65)
        self.filter_pipeline = create_default_pipeline(
            confidence_threshold=confidence_threshold,
            similarity_threshold=85,
            strict_evidence=False
        )
    
    def process(self, code: str) -> Dict[str, Any]:
        """Analyze code using all security sub-agents in parallel.
        
        Args:
            code: Source code to analyze
            
        Returns:
            Dict containing filtered security findings from all sub-agents
        """
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
                    print(f"{agent_name}: Found {len(findings)} vulnerabilities")
                    all_findings.extend(findings)
                except Exception as e:
                    print(f"Error in {agent_name}: {e}")
        
        print(f"\nTotal vulnerabilities before filtering: {len(all_findings)}")
        
        # Apply filter pipeline
        filtered_findings = self.filter_pipeline.process(all_findings)
        
        # Convert to structured vulnerability format
        vulnerabilities = []
        for finding in filtered_findings:
            vuln = finding.to_dict()
            vulnerabilities.append(vuln)
        
        # Generate analysis summary
        analysis_summary = self._generate_summary(filtered_findings)
        
        # Calculate risk score
        risk_score = self._calculate_risk_score(filtered_findings)
        
        return {
            "status": "ok",
            "raw_analysis": analysis_summary,
            "vulnerabilities": vulnerabilities,
            "vulnerability_count": len(filtered_findings),
            "risk_score": risk_score,
            "vulnerabilities_by_severity": self._group_by_severity(filtered_findings),
            "vulnerabilities_by_category": self._group_by_category(filtered_findings)
        }
    
    def _generate_summary(self, findings: List[Finding]) -> str:
        """Generate a text summary of security findings."""
        if not findings:
            return "Security analysis complete. No significant vulnerabilities found."
        
        summary_parts = [f"Detected {len(findings)} security vulnerabilities:\n"]
        
        # Group by severity
        by_severity = self._group_by_severity(findings)
        for severity in ["critical", "high", "medium", "low"]:
            if severity in by_severity:
                count = by_severity[severity]
                summary_parts.append(f"- {severity.capitalize()}: {count}")
        
        return "\n".join(summary_parts)
    
    def _calculate_risk_score(self, findings: List[Finding]) -> float:
        """Calculate overall risk score based on vulnerabilities found."""
        if not findings:
            return 0.0
            
        severity_weights = {
            "critical": 10.0,
            "high": 7.0,
            "medium": 4.0,
            "low": 1.0
        }
        
        total_score = sum(
            severity_weights.get(f.severity, 1.0) * f.confidence
            for f in findings
        )
        
        # Normalize to 0-10 scale
        max_score = len(findings) * 10
        return min(10.0, (total_score / max_score) * 10) if max_score > 0 else 0.0
    
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
