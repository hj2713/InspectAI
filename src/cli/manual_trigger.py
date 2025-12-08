import argparse
import re
import os

def parse_args():
    parser = argparse.ArgumentParser(description="Manually trigger InspectAI on a PR")
    parser.add_argument("--url", required=True, help="Full GitHub PR URL")
    parser.add_argument("--dry-run", action="store_true", help="Analyze but do not post comment")
    return parser.parse_args()

def extract_pr_details(url):
    # Regex to parse https://github.com/owner/repo/pull/123
    pattern = r"github\.com/([^/]+)/([^/]+)/pull/(\d+)"
    match = re.search(pattern, url)
    if match:
        return match.group(1), match.group(2), int(match.group(3))
    raise ValueError("Invalid GitHub PR URL provided")

def check_env():
    """Ensure the GITHUB_TOKEN is set."""
    if not os.getenv("GITHUB_TOKEN"):
        print("WARNING: GITHUB_TOKEN not found in environment variables.")
        print("       API calls to GitHub may fail or be rate-limited.")
        return False
    return True

def main():
    args = parse_args()

    # Security check
    check_env()

    try:
        owner, repo, pr_number = extract_pr_details(args.url)
        print(f"Target: {owner}/{repo} #{pr_number}")
    except ValueError as e:
        print(f"Error: {e}")
        exit(1)

if __name__ == "__main__":
    main()