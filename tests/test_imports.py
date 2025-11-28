import sys
import os
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent))

def test_imports():
    print("Testing imports for all agents...")
    
    try:
        print("Importing OrchestratorAgent...")
        from src.orchestrator.orchestrator import OrchestratorAgent
        print("✅ OrchestratorAgent imported")
        
        print("Importing CodeAnalysisAgent...")
        from src.agents.code_analysis_agent import CodeAnalysisAgent
        print("✅ CodeAnalysisAgent imported")
        
        print("Importing specialized Code Review agents...")
        from src.agents.code_review.naming_reviewer import NamingReviewer
        from src.agents.code_review.quality_reviewer import QualityReviewer
        from src.agents.code_review.duplication_detector import DuplicationDetector
        from src.agents.code_review.pep8_reviewer import PEP8Reviewer
        print("✅ Code Review agents imported")
        
        print("Importing BugDetectionAgent...")
        from src.agents.bug_detection_agent import BugDetectionAgent
        print("✅ BugDetectionAgent imported")
        
        print("Importing specialized Bug Detection agents...")
        from src.agents.bug_detection.logic_error_detector import LogicErrorDetector
        from src.agents.bug_detection.edge_case_analyzer import EdgeCaseAnalyzer
        from src.agents.bug_detection.type_error_detector import TypeErrorDetector
        from src.agents.bug_detection.runtime_issue_detector import RuntimeIssueDetector
        print("✅ Bug Detection agents imported")
        
        print("Importing SecurityAnalysisAgent...")
        from src.agents.security_agent import SecurityAnalysisAgent
        print("✅ SecurityAnalysisAgent imported")
        
        print("Importing specialized Security agents...")
        from src.agents.security.injection_scanner import InjectionScanner
        from src.agents.security.auth_scanner import AuthScanner
        from src.agents.security.data_exposure_scanner import DataExposureScanner
        from src.agents.security.dependency_scanner import DependencyScanner
        print("✅ Security agents imported")
        
        print("\n🎉 All agents imported successfully! No NameErrors or SyntaxErrors found.")
        
    except Exception as e:
        print(f"\n❌ Import failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_imports()
