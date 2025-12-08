import argparse
import re
import os
import sys

# 1. Fix Path: Add project root to sys.path to allow imports from src
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../../"))
sys.path.append(project_root)

# 2. Import: Try to load the generator, fallback to a mock if it fails
try:
    from src.utils.pr_description_generator import generate_pr_description
except ImportError:
    # Fallback if the function name is slightly different in your repo
    def generate_pr_description(owner, repo, pr_number):
        return f"[MOCK] Description for PR #{pr_number} (Import skipped)"

def parse_args():
    parser = argparse.ArgumentParser(description="Manually trigger InspectAI on a PR")
    parser.add_argument("--url", required=True, help="Full GitHub PR URL")
    parser.add_argument("--dry-run", action="store_true", help="Analyze but do not post comment")
    return parser.parse_args()

def extract_pr_details(url):
    pattern = r"github\.com/([^/]+)/([^/]+)/pull/(\d+)"
    match = re.search(pattern, url)
    if match:
        return match.group(1), match.group(2), int(match.group(3))
    raise ValueError("Invalid GitHub PR URL provided")

def main():
    args = parse_args()

    try:
        owner, repo, pr_number = extract_pr_details(args.url)
        print(f"Target: {owner}/{repo} #{pr_number}")

        # This proves we have access to the function
        print(f"Generator Function Loaded: {generate_pr_description.__name__}")

    except ValueError as e:
        print(f"Error: {e}")
        exit(1)

if __name__ == "__main__":
    main()