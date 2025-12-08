import argparse

def parse_args():
    parser = argparse.ArgumentParser(description="Manually trigger InspectAI on a PR")
    parser.add_argument("--url", required=True, help="Full GitHub PR URL")
    parser.add_argument("--dry-run", action="store_true", help="Analyze but do not post comment")
    return parser.parse_args()

def main():
    args = parse_args()
    print(f"Processing {args.url} (Dry Run: {args.dry_run})")

if __name__ == "__main__":
    main()