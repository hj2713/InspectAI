import argparse
import re
import os
import sys

# 1. Fix Path: Add project root to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../../"))
sys.path.append(project_root)

# 2. Import: Try to load the generator
try:
    from src.utils.pr_description_generator import generate_pr_description
except ImportError:
    # Fallback Mock for demonstration if import fails
    def generate_pr_description(owner, repo, pr_number):
        return f"\n[MOCK OUTPUT] PR #{pr_number} analyzes code changes...\n- Fixed bug in API.\n- Updated documentation."

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

def check_env():
    if not os.getenv("GITHUB_TOKEN"):
        # We just warn, we don't crash, so the mock can still work
        print("WARNING: GITHUB_TOKEN not found. API calls may fail.")

def main():
    args = parse_args()
    check_env()

    try:
        owner, repo, pr_number = extract_pr_details(args.url)
        print(f"Target: {owner}/{repo} #{pr_number}")

        if args.dry_run:
            print("\n--- DRY RUN MODE: Generating Description ---")
            # Call the real function
            description = generate_pr_description(owner, repo, pr_number)
            print(description)
            print("--- Dry run complete. No changes pushed to GitHub. ---")
        else:
            print("Live execution paused. Please use --dry-run to test safely.")

    except Exception as e:
        print(f"Error: {e}")
        exit(1)

if __name__ == "__main__":
    main()