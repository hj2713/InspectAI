"""Filter Pipeline for processing and refining agent findings.

This module provides a filtering pipeline that processes findings from multiple
agents to remove low-confidence results, deduplicate similar findings, and
validate evidence to reduce hallucinations.
"""
from typing import List, Dict, Any, Callable
from abc import ABC, abstractmethod
from fuzzywuzzy import fuzz
from .specialized_agent import Finding


class BaseFilter(ABC):
    """Base class for all filters in the pipeline."""
    
    @abstractmethod
    def filter(self, findings: List[Finding]) -> List[Finding]:
        """Filter the list of findings.
        
        Args:
            findings: List of findings to filter
            
        Returns:
            Filtered list of findings
        """
        pass
    
    def __call__(self, findings: List[Finding]) -> List[Finding]:
        """Allow filter to be called as a function."""
        return self.filter(findings)


class ConfidenceFilter(BaseFilter):
    """Filter out findings below a confidence threshold."""
    
    def __init__(self, threshold: float = 0.5):
        """Initialize confidence filter.
        
        Args:
            threshold: Minimum confidence score (0.0-1.0)
        """
        self.threshold = max(0.0, min(1.0, threshold))
    
    def filter(self, findings: List[Finding]) -> List[Finding]:
        """Filter findings by confidence threshold.
        
        Args:
            findings: List of findings to filter
            
        Returns:
            Findings with confidence >= threshold
        """
        filtered = [f for f in findings if f.confidence >= self.threshold]
        
        # Log filtered count for debugging
        if len(filtered) < len(findings):
            removed = len(findings) - len(filtered)
            print(f"ConfidenceFilter: Removed {removed} findings below threshold {self.threshold}")
        
        return filtered


class DeduplicationFilter(BaseFilter):
    """Remove duplicate or very similar findings."""
    
    def __init__(self, similarity_threshold: int = 85):
        """Initialize deduplication filter.
        
        Args:
            similarity_threshold: Fuzzy match threshold (0-100)
        """
        self.similarity_threshold = similarity_threshold
    
    def filter(self, findings: List[Finding]) -> List[Finding]:
        """Remove duplicate findings using fuzzy matching.
        
        Args:
            findings: List of findings to deduplicate
            
        Returns:
            Deduplicated list of findings
        """
        if not findings:
            return []
        
        unique_findings = []
        
        for finding in findings:
            is_duplicate = False
            
            for existing in unique_findings:
                # Check if descriptions are similar
                similarity = fuzz.token_set_ratio(
                    finding.description.lower(),
                    existing.description.lower()
                )
                
                # Also check category and location
                same_category = finding.category == existing.category
                same_location = finding.location == existing.location
                
                if similarity >= self.similarity_threshold and same_category:
                    is_duplicate = True
                    # Keep the one with higher confidence
                    if finding.confidence > existing.confidence:
                        unique_findings.remove(existing)
                        unique_findings.append(finding)
                    break
            
            if not is_duplicate:
                unique_findings.append(finding)
        
        removed = len(findings) - len(unique_findings)
        if removed > 0:
            print(f"DeduplicationFilter: Removed {removed} duplicate findings")
        
        return unique_findings


class HallucinationFilter(BaseFilter):
    """Verify that findings have valid evidence in the code."""
    
    def __init__(self, strict: bool = False):
        """Initialize hallucination filter.
        
        Args:
            strict: If True, require evidence for all findings
        """
        self.strict = strict
    
    def filter(self, findings: List[Finding]) -> List[Finding]:
        """Filter findings without valid evidence.
        
        Args:
            findings: List of findings to validate
            
        Returns:
            Findings with validated evidence
        """
        filtered = []
        
        for finding in findings:
            has_evidence = False
            
            # Check if evidence exists
            if finding.evidence:
                # Check for code snippet
                if finding.evidence.get("code_snippet"):
                    has_evidence = True
                # Check for line number
                elif finding.evidence.get("line_number"):
                    has_evidence = True
            
            # Check if location is specified (alternative to evidence)
            if finding.location and not has_evidence:
                has_evidence = True
            
            # Keep finding if it has evidence, or if not strict mode
            if has_evidence or not self.strict:
                filtered.append(finding)
            else:
                # Lower confidence for findings without evidence
                finding.confidence *= 0.5
                if finding.confidence >= 0.3:  # Still include if confidence decent
                    filtered.append(finding)
        
        removed = len(findings) - len(filtered)
        if removed > 0:
            print(f"HallucinationFilter: Removed {removed} findings without evidence")
        
        return filtered


class SeverityFilter(BaseFilter):
    """Filter findings by severity level."""
    
    def __init__(self, min_severity: str = "low"):
        """Initialize severity filter.
        
        Args:
            min_severity: Minimum severity level (low, medium, high, critical)
        """
        self.severity_order = ["low", "medium", "high", "critical"]
        self.min_severity = min_severity.lower()
        
        if self.min_severity not in self.severity_order:
            self.min_severity = "low"
        
        self.min_index = self.severity_order.index(self.min_severity)
    
    def filter(self, findings: List[Finding]) -> List[Finding]:
        """Filter findings by minimum severity.
        
        Args:
            findings: List of findings to filter
            
        Returns:
            Findings with severity >= min_severity
        """
        filtered = []
        
        for finding in findings:
            severity = finding.severity.lower()
            if severity in self.severity_order:
                severity_index = self.severity_order.index(severity)
                if severity_index >= self.min_index:
                    filtered.append(finding)
        
        removed = len(findings) - len(filtered)
        if removed > 0:
            print(f"SeverityFilter: Removed {removed} findings below {self.min_severity}")
        
        return filtered


class FilterPipeline:
    """Pipeline that runs multiple filters in sequence."""
    
    def __init__(self, filters: List[BaseFilter] = None):
        """Initialize filter pipeline.
        
        Args:
            filters: List of filters to apply in order
        """
        self.filters = filters or []
    
    def add_filter(self, filter_instance: BaseFilter) -> 'FilterPipeline':
        """Add a filter to the pipeline.
        
        Args:
            filter_instance: Filter to add
            
        Returns:
            Self for chaining
        """
        self.filters.append(filter_instance)
        return self
    
    def process(self, findings: List[Finding]) -> List[Finding]:
        """Process findings through all filters.
        
        Args:
            findings: List of findings to process
            
        Returns:
            Filtered findings
        """
        result = findings
        
        print(f"\nFilterPipeline: Starting with {len(result)} findings")
        
        for filter_instance in self.filters:
            result = filter_instance.filter(result)
        
        print(f"FilterPipeline: Ended with {len(result)} findings\n")
        
        return result
    
    def __call__(self, findings: List[Finding]) -> List[Finding]:
        """Allow pipeline to be called as a function."""
        return self.process(findings)


def create_default_pipeline(confidence_threshold: float = 0.5,
                           similarity_threshold: int = 85,
                           strict_evidence: bool = False) -> FilterPipeline:
    """Create a default filter pipeline with common filters.
    
    Args:
        confidence_threshold: Minimum confidence score
        similarity_threshold: Fuzzy match threshold for deduplication
        strict_evidence: Whether to require evidence for all findings
        
    Returns:
        Configured FilterPipeline
    """
    pipeline = FilterPipeline()
    pipeline.add_filter(DeduplicationFilter(similarity_threshold))
    pipeline.add_filter(HallucinationFilter(strict_evidence))
    pipeline.add_filter(ConfidenceFilter(confidence_threshold))
    
    return pipeline
