"""Example usage of LangGraph workflows for code review.

This script demonstrates how to use the LangGraph-based code review workflow.
"""
from src.langgraph_workflows import run_code_review


# Sample code with issues
sample_code = """
import os

# Bad naming - should be UPPER_CASE
apiKey = "sk-1234567890"  # Security: hardcoded secret

def calculate(x, y):  # Missing type hints
    result = x / y  # Division by zero possible
    return result

class userManager:  # Bad naming: should be PascalCase
    def get_user(self, id):
        # SQL injection vulnerability
        query = f"SELECT * FROM users WHERE id = {id}"
        return db.execute(query)
"""


def main():
    print("=" * 60)
    print("LangGraph Code Review Workflow Example")
    print("=" * 60)
    
    # Example 1: Full review
    print("\n[1] Running FULL REVIEW (all 12 agents)...")
    result = run_code_review(sample_code, task_type="full_review")
    
    print(f"\nStatus: {result.get('status')}")
    print(f"Total findings: {len(result.get('filtered_findings', []))}")
    print(f"\nSummary:\n{result.get('summary', 'N/A')}")
    
    if result.get('errors'):
        print(f"\n⚠️  Errors encountered: {result['errors']}")
    
    # Example 2: Bug detection only
    print("\n" + "=" * 60)
    print("\n[2] Running BUG FIX review (4 bug detection agents)...")
    result2 = run_code_review(sample_code, task_type="bug_fix")
    
    print(f"\nStatus: {result2.get('status')}")
    print(f"Bugs found: {len(result2.get('filtered_findings', []))}")
    
    # Show detailed findings
    print("\nDetailed findings:")
    for i, finding in enumerate(result2.get('filtered_findings', [])[:5], 1):
        print(f"\n  {i}. [{finding.get('severity')}] {finding.get('category')}")
        print(f"     {finding.get('description')}")
        print(f"     Fix: {finding.get('fix_suggestion', 'N/A')}")
        print(f"     Confidence: {finding.get('confidence', 0):.0%}")
    
    # Example 3: Security audit only
    print("\n" + "=" * 60)
    print("\n[3] Running SECURITY AUDIT (4 security agents)...")
    result3 = run_code_review(sample_code, task_type="security_audit")
    
    print(f"\nStatus: {result3.get('status')}")
    print(f"Security issues found: {len(result3.get('filtered_findings', []))}")
    
    for i, finding in enumerate(result3.get('filtered_findings', []), 1):
        print(f"\n  {i}. 🔒 [{finding.get('severity')}] {finding.get('category')}")
        print(f"     {finding.get('description')}")
    
    print("\n" + "=" * 60)
    print("✅ Workflow demonstration complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
